"""Feature engineering over the whole database (vectorised pandas / DuckDB).

Nothing in this module reads ground-truth tables (labels_*): features are computed from transactions and
network observations only. `tests/test_ml.py` checks that no label column leaks into a feature matrix.
"""
import math
from dataclasses import dataclass

import networkx as nx
import numpy as np
import pandas as pd

from beans.api.geo import CENTROIDS

RISKY_ASN = {"TOR_EXIT", "VPN", "BULLETPROOF"}


@dataclass
class Frames:
    tx: pd.DataFrame     # one row per txid (first-seen observation)
    tin: pd.DataFrame    # txid, ts, address, amount
    tout: pd.DataFrame   # txid, ts, idx, address, amount
    spy: pd.DataFrame    # first-spy per txid


def load_frames(conn) -> Frames:
    tx = conn.execute("SELECT txid, timestamp AS ts, fee, script_type FROM transactions").df()
    tin = conn.execute("""SELECT txid, timestamp AS ts, unnest(input_addresses) AS address,
                          unnest(input_amounts) AS amount FROM transactions""").df()
    tout = conn.execute("""SELECT txid, timestamp AS ts, generate_subscripts(output_addresses, 1) AS idx,
                           unnest(output_addresses) AS address, unnest(output_amounts) AS amount
                           FROM transactions""").df()
    spy = conn.execute("""
        WITH o AS (SELECT *, row_number() OVER (PARTITION BY txid ORDER BY timestamp) AS rn,
                          count(*) OVER (PARTITION BY txid) AS n FROM net_observations)
        SELECT a.txid, a.src_ip AS spy_ip, a.src_port AS spy_port, a.geo_country AS spy_country,
               a.asn AS spy_asn, a.asn_type AS spy_asn_type, a.n AS n_obs,
               (epoch_ms(b.timestamp) - epoch_ms(a.timestamp)) / 1000.0 AS spy_delta
        FROM o a LEFT JOIN o b ON a.txid = b.txid AND b.rn = 2 WHERE a.rn = 1""").df()
    return Frames(tx, tin, tout, spy)


def tx_features(f: Frames) -> pd.DataFrame:
    tx = f.tx.set_index("txid")
    out_g = f.tout.groupby("txid")["amount"]
    in_g = f.tin.groupby("txid")["amount"]
    X = pd.DataFrame(index=tx.index)
    X["n_in"] = in_g.size().reindex(X.index).fillna(0)
    X["n_out"] = out_g.size().reindex(X.index).fillna(0)
    X["total_out"] = out_g.sum().reindex(X.index).fillna(0)
    X["log_total_out"] = np.log1p(X["total_out"])
    X["is_coinbase"] = (X["n_in"] == 0).astype(float)
    vbytes = 11 + 68 * X["n_in"].clip(lower=1) + 31 * X["n_out"]
    X["fee_rate"] = tx["fee"].fillna(0) * 1e8 / vbytes
    eq = f.tout.assign(r=f.tout["amount"].round(8)).groupby(["txid", "r"]).size().groupby("txid").max()
    X["max_equal_outputs"] = eq.reindex(X.index).fillna(0)
    X["equal_output_share"] = (X["max_equal_outputs"] / X["n_out"].clip(lower=1)).where(X["n_out"] > 1, 0)
    # normalised Shannon entropy of the output values (vectorised)
    o = f.tout[f.tout["amount"] > 0][["txid", "amount"]].copy()
    o["p"] = o["amount"] / o.groupby("txid")["amount"].transform("sum")
    ent = (-(o["p"] * np.log2(o["p"]))).groupby(o["txid"]).sum()
    n = X["n_out"].where(X["n_out"] > 1)
    X["output_entropy"] = (ent.reindex(X.index) / np.log2(n)).fillna(0)
    mn, mx = out_g.min().reindex(X.index), out_g.max().reindex(X.index)
    X["min_out_share"] = (mn / X["total_out"].replace(0, np.nan)).fillna(1)
    X["log_max_min_ratio"] = np.log10((mx / mn.clip(lower=1e-8)).fillna(1))
    X["dust_outputs"] = f.tout[f.tout["amount"] < 1e-5].groupby("txid").size().reindex(X.index).fillna(0)
    rnd = f.tout.assign(r=(np.abs(f.tout["amount"] * 1e4 - np.round(f.tout["amount"] * 1e4)) < 1e-6).astype(float))
    X["round_output_share"] = rnd.groupby("txid")["r"].mean().reindex(X.index).fillna(0)
    X["hour_utc"] = pd.to_datetime(tx["ts"]).dt.hour
    X.attrs["ts"] = pd.to_datetime(tx["ts"])
    for st in ("P2WSH", "P2TR", "P2PKH", "P2SH"):
        X[f"script_{st}"] = (tx["script_type"] == st).astype(float)

    # --- spend timing: when do the outputs get spent, how old are the inputs
    tout = f.tout.sort_values("ts")
    tin = f.tin.sort_values("ts")
    spent = pd.merge_asof(tout, tin[["ts", "address", "txid"]].rename(columns={"txid": "spend_txid", "ts": "spend_ts"}),
                          left_on="ts", right_on="spend_ts", by="address", direction="forward", allow_exact_matches=False)
    spent["respend_min"] = (spent["spend_ts"] - spent["ts"]).dt.total_seconds() / 60
    rg = spent.groupby("txid")["respend_min"]
    X["min_respend_min"] = rg.min().reindex(X.index).fillna(1e5).clip(upper=1e5)
    X["share_spent_1h"] = spent.assign(q=spent["respend_min"] < 60).groupby("txid")["q"].mean().reindex(X.index).fillna(0)
    created = pd.merge_asof(tin, tout[["ts", "address"]].rename(columns={"ts": "created_ts"}), left_on="ts",
                            right_on="created_ts", by="address", direction="backward", allow_exact_matches=False)
    created["age_h"] = (created["ts"] - created["created_ts"]).dt.total_seconds() / 3600
    X["mean_input_age_h"] = created.groupby("txid")["age_h"].mean().reindex(X.index).fillna(-1)

    # --- peel chains: peel-shaped tx whose big output is spent by another peel-shaped tx
    X["peel_shape"] = ((X["n_in"] <= 2) & (X["n_out"] == 2) & (X["min_out_share"] < 0.1)).astype(float)
    big = spent.sort_values("amount").groupby("txid").tail(1)[["txid", "spend_txid"]].dropna()
    peel_ids = set(X.index[X["peel_shape"] == 1])
    g = nx.Graph()
    g.add_nodes_from(peel_ids)
    g.add_edges_from((a, b) for a, b in zip(big["txid"], big["spend_txid"]) if a in peel_ids and b in peel_ids)
    chain_len, chain_id = {}, {}
    for comp in nx.connected_components(g):
        cid = min(comp)[:12]
        for t in comp:
            chain_len[t], chain_id[t] = len(comp), cid
    X["peel_chain_len"] = pd.Series(chain_len).reindex(X.index).fillna(0)
    X.attrs["peel_chain_id"] = chain_id

    # --- round trip: value comes back to one of the input addresses within 3 hops
    spenders = f.tin.groupby("address")["txid"].apply(list).to_dict()
    outs = f.tout.groupby("txid")["address"].apply(list).to_dict()
    ins = f.tin.groupby("txid")["address"].apply(set).to_dict()
    cyc = {}
    for t in X.index[(X["n_in"].between(1, 2)) & (X["n_out"] <= 2)]:
        targets, frontier, hit = ins.get(t, set()), [t], 0.0
        for _ in range(3):
            nxt = []
            for tt in frontier:
                for a in outs.get(tt, []):
                    if a in targets and tt != t:
                        hit = 1.0
                    nxt.extend(spenders.get(a, [])[:5])
            if hit or not nxt:
                break
            frontier = nxt[:50]
        cyc[t] = hit
    X["returns_to_input"] = pd.Series(cyc).reindex(X.index).fillna(0)

    # --- network layer (first-spy of this tx)
    spy = f.spy.set_index("txid").reindex(X.index)
    X["spy_risky_asn"] = spy["spy_asn_type"].isin(RISKY_ASN).astype(float)
    X["spy_tor"] = (spy["spy_asn_type"] == "TOR_EXIT").astype(float)
    X["spy_datacenter"] = (spy["spy_asn_type"] == "DATACENTER").astype(float)
    X["spy_residential"] = (spy["spy_asn_type"] == "RESIDENTIAL").astype(float)
    X["spy_confidence"] = 1 - np.exp(-spy["spy_delta"].fillna(0.3) / 1.5)
    X["n_obs"] = spy["n_obs"].fillna(0)
    X["spy_nonstd_port"] = (spy["spy_port"] != 8333).astype(float)
    return X


TX_NETWORK_COLS = ["spy_risky_asn", "spy_tor", "spy_datacenter", "spy_residential", "spy_confidence", "n_obs",
                   "spy_nonstd_port"]


def _velocity(group: pd.DataFrame) -> float:
    """Max km/h between consecutive broadcasts of this wallet's spends (country centroids)."""
    g = group.sort_values("ts")
    best, prev = 0.0, None
    for ts, c in zip(g["ts"], g["spy_country"]):
        loc = CENTROIDS.get(c)
        if loc and prev and prev[1] != loc:
            p1, p2 = math.radians(prev[1][0]), math.radians(loc[0])
            dl = math.radians(loc[1] - prev[1][1])
            km = 6371 * 2 * math.asin(math.sqrt(math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2))
            best = max(best, km / max((ts - prev[0]).total_seconds() / 3600, 1 / 60))
        if loc:
            prev = (ts, loc)
    return best


def wallet_features(f: Frames, X_tx: pd.DataFrame) -> pd.DataFrame:
    recv = f.tout.groupby("address").agg(n_recv=("txid", "nunique"), recv_btc=("amount", "sum"),
                                          first_recv=("ts", "min"), last_recv=("ts", "max"))
    sent = f.tin.groupby("address").agg(n_spend=("txid", "nunique"), sent_btc=("amount", "sum"),
                                         first_spend=("ts", "min"), last_spend=("ts", "max"))
    W = recv.join(sent, how="outer")
    W[["n_recv", "recv_btc", "n_spend", "sent_btc"]] = W[["n_recv", "recv_btc", "n_spend", "sent_btc"]].fillna(0)
    first = W[["first_recv", "first_spend"]].min(axis=1)
    last = W[["last_recv", "last_spend"]].max(axis=1)
    W["lifetime_h"] = (last - first).dt.total_seconds() / 3600
    W["hold_h"] = ((W["first_spend"] - W["first_recv"]).dt.total_seconds() / 3600).fillna(-1)
    W["log_recv_btc"] = np.log1p(W["recv_btc"])
    W["log_sent_btc"] = np.log1p(W["sent_btc"])
    W["reused"] = (W["n_recv"] > 1).astype(float)

    # shape of the transactions the wallet takes part in
    as_in = f.tin[["txid", "address"]].drop_duplicates().join(X_tx, on="txid")
    as_out = f.tout[["txid", "address"]].drop_duplicates().join(X_tx, on="txid")
    W["spend_max_n_out"] = as_in.groupby("address")["n_out"].max().reindex(W.index).fillna(0)
    W["fund_max_n_in"] = as_out.groupby("address")["n_in"].max().reindex(W.index).fillna(0)
    W["fund_n_out"] = as_out.groupby("address")["n_out"].max().reindex(W.index).fillna(0)
    both = pd.concat([as_in, as_out])
    for c in ("peel_chain_len", "equal_output_share", "returns_to_input", "dust_outputs", "peel_shape"):
        W[f"max_{c}"] = both.groupby("address")[c].max().reindex(W.index).fillna(0)
    W["min_respend_min"] = as_out.groupby("address")["min_respend_min"].min().reindex(W.index).fillna(1e5)

    # network: who broadcast this wallet's spends
    net = f.tin[["txid", "address", "ts"]].drop_duplicates(["txid", "address"]).merge(f.spy, on="txid", how="left")
    ng = net.groupby("address")
    W["n_spend_ips"] = ng["spy_ip"].nunique().reindex(W.index).fillna(0)
    W["n_spend_countries"] = ng["spy_country"].nunique().reindex(W.index).fillna(0)
    W["share_risky_asn"] = net.assign(r=net["spy_asn_type"].isin(RISKY_ASN)).groupby("address")["r"].mean().reindex(W.index).fillna(0)
    W["share_datacenter"] = net.assign(r=net["spy_asn_type"] == "DATACENTER").groupby("address")["r"].mean().reindex(W.index).fillna(0)
    multi = net[net["address"].isin(W.index[W["n_spend"] > 1])]
    vel = multi.groupby("address")[["ts", "spy_country"]].apply(_velocity) if len(multi) else pd.Series(dtype=float)
    W["max_geo_velocity_kmh"] = vel.reindex(W.index).fillna(0).clip(upper=20000)
    W["mean_spy_confidence"] = 1 - np.exp(-net.groupby("address")["spy_delta"].mean().reindex(W.index).fillna(0.3) / 1.5)
    return W.drop(columns=["first_recv", "last_recv", "first_spend", "last_spend"])


WALLET_NETWORK_COLS = ["n_spend_ips", "n_spend_countries", "share_risky_asn", "share_datacenter",
                       "max_geo_velocity_kmh", "mean_spy_confidence"]
