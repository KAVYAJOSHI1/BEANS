"""E1: entity clustering = common-input-ownership (CIOH) + change heuristics + self-split heuristic + embedding suggestions.

CoinJoin transactions (per E3) are excluded from CIOH, otherwise unrelated participants would be merged.
Embeddings: truncated SVD of the cluster-level flow graph (+ behaviour) → HDBSCAN proposes clusters that
behave alike; these are reported as merge *suggestions*, never merged automatically.
"""
import hashlib
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import StandardScaler


SWEEP_MIN_INPUTS = 10         # a tx spending this many inputs is a service sweep (exchange / merchant / pool)
SPLIT_MIN_PARTS = 7            # self-split heuristic: at least this many near-identical parts …
SPLIT_MAX_CV = 0.05            # … differing by ≤ 5 % (coefficient of variation; one change output is allowed) …
SPLIT_MAX_SENDER_DEGREE = 6    # … sent by an address seen in at most this many transactions (not a service hub)


class _UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def _decimals(v: float) -> int:
    s = f"{v:.8f}".rstrip("0")
    return len(s.split(".")[1]) if "." in s else 0


def cluster(frames, X_tx: pd.DataFrame, coinjoin_txids: set) -> tuple[pd.Series, dict]:
    uf = _UF()
    for a in pd.concat([frames.tin["address"], frames.tout["address"]]).unique():
        uf.find(a)
    ins: dict = defaultdict(list)
    for t, a in zip(frames.tin["txid"].values, frames.tin["address"].values):
        ins[t].append(a)
    merged_cioh = merged_change = 0
    for txid, addrs in ins.items():
        if txid in coinjoin_txids or len(addrs) < 2:
            continue
        for a in addrs[1:]:
            uf.union(addrs[0], a)
        merged_cioh += 1
    # change heuristic (conservative): 2 outputs, exactly one has full 8-decimal precision → that one is change
    first_seen = frames.tout.groupby("address")["ts"].min().to_dict()
    # guards against false change picks (each one bridged an exchange into a criminal's cluster in testing):
    #  - an address later swept in a big consolidation is a service deposit address, never the sender's change
    #  - in a peel-shaped tx the tiny output is the payment; the change is the large one
    swept = set(frames.tin.loc[frames.tin["txid"].isin(set(X_tx.index[X_tx["n_in"] >= SWEEP_MIN_INPUTS])), "address"])
    # wallet-software fingerprints: the tx's own, and that of the tx that later spends each address
    from beans.features.extractors import tx_fingerprint
    fp = (tx_fingerprint(frames.tx) if "tx_version" in frames.tx else pd.Series(dtype=object)).dropna().to_dict()
    # a CoinJoin is built by its coordinator's software, so a CoinJoin spend says nothing about the owner's wallet
    own_spends = frames.tin[~frames.tin["txid"].isin(coinjoin_txids)]
    first_spend = own_spends.sort_values("ts").drop_duplicates("address").set_index("address")["txid"]
    spend_fp = first_spend.map(fp).dropna().to_dict() if fp else {}

    def fp_conflict(txid, addr) -> bool:
        """True when the tx and the later spend of `addr` were built by different wallet software."""
        a, b = fp.get(txid), spend_fp.get(addr)
        return isinstance(a, str) and isinstance(b, str) and a != b

    merged_fp = 0
    peel_shaped = set(X_tx.index[X_tx["peel_shape"] == 1])
    two = frames.tout[frames.tout["txid"].isin(set(X_tx.index[(X_tx["n_out"] == 2) & (X_tx["n_in"] >= 1)]))] \
        .sort_values(["txid", "idx"])
    T, A, V, S = two["txid"].values, two["address"].values, two["amount"].values, two["ts"].values
    for i in range(0, len(T) - 1, 2):          # rows come in pairs: exactly two outputs per tx
        txid = T[i]
        if txid in coinjoin_txids or txid not in ins:
            continue
        g_addr, g_amt = (A[i], A[i + 1]), (V[i], V[i + 1])
        g_ts = (pd.Timestamp(S[i]), pd.Timestamp(S[i + 1]))
        prec = [(_decimals(v) >= 7, a, ts) for a, v, ts in zip(g_addr, g_amt, g_ts)]
        change = [a for p, a, ts in prec if p and first_seen.get(a) == ts]
        smaller = g_addr[0] if g_amt[0] <= g_amt[1] else g_addr[1]
        if change and (change[0] in swept or (txid in peel_shaped and change[0] == smaller) or fp_conflict(txid, change[0])):
            continue
        if len(change) == 1 and sum(p for p, _, _ in prec) == 1:
            uf.union(ins[txid][0], change[0])
            merged_change += 1
        elif not change:
            # fingerprint change rule: exactly one fresh, non-swept output is later spent by the same wallet software
            # as this transaction → it is the sender's change
            same = [a for a, ts in zip(g_addr, g_ts) if first_seen.get(a) == ts and a not in swept
                    and isinstance(fp.get(txid), str) and spend_fp.get(a) == fp.get(txid)]
            other = [a for a in g_addr if isinstance(spend_fp.get(a), str) and spend_fp.get(a) != fp.get(txid)]
            if len(same) == 1 and len(other) == 1:
                uf.union(ins[txid][0], same[0])
                merged_fp += 1
    # peel-chain change heuristic: inside a peel chain (≥ 3 linked peel-shaped hops, where each hop's large output
    # is spent by the next peel-shaped hop), the large output is the sender's change. Restricting to chains avoids
    # merging a victim who pays a ransom with a small change output.
    merged_peel = 0
    peel_tx = X_tx.index[(X_tx["peel_shape"] == 1) & (X_tx["peel_chain_len"] >= 3)]
    big = frames.tout[frames.tout["txid"].isin(peel_tx)].sort_values("amount").groupby("txid").tail(1)
    for txid, addr in zip(big["txid"], big["address"]):
        if txid in coinjoin_txids or txid not in ins or fp_conflict(txid, addr):
            continue
        uf.union(ins[txid][0], addr)
        merged_peel += 1
    # self-split heuristic: one (non-hub) owner splits a balance into ≥ 3 near-identical parts on fresh addresses.
    # Launderers split loot this way before peeling / cashing out each part; payouts to many different users
    # (exchanges, pools, payroll) have varied amounts and come from hub addresses, and CoinJoins are excluded.
    merged_split = 0
    degree = pd.concat([frames.tin[["txid", "address"]], frames.tout[["txid", "address"]]]).drop_duplicates() \
        .groupby("address").size()
    def parts_cv(amounts: pd.Series) -> float:
        """CV of the outputs after setting aside the one furthest from the median (the change, if any)."""
        a = amounts.values
        if len(a) > SPLIT_MIN_PARTS:
            a = np.delete(a, np.argmax(np.abs(a - np.median(a))))
        return float(a.std() / a.mean()) if len(a) >= SPLIT_MIN_PARTS and a.mean() > 0 else 1.0
    cand = X_tx.index[(X_tx["n_out"] >= SPLIT_MIN_PARTS) & (X_tx["n_in"] >= 1)]
    cand = [t for t in cand if t not in coinjoin_txids and t in ins]
    cv = frames.tout[frames.tout["txid"].isin(cand)].groupby("txid")["amount"].apply(parts_cv)
    cand = [t for t in cand if cv.get(t, 1.0) <= SPLIT_MAX_CV]
    outs = frames.tout[frames.tout["txid"].isin(cand)].groupby("txid")
    for txid in cand:
        senders = set(ins[txid])
        if len({uf.find(a) for a in senders}) != 1 or max(degree.get(a, 0) for a in senders) > SPLIT_MAX_SENDER_DEGREE:
            continue
        g = outs.get_group(txid)
        if not all(first_seen.get(a) == ts for a, ts in zip(g["address"], g["ts"])) or g["address"].isin(senders).any():
            continue
        if sum(fp_conflict(txid, a) for a in g["address"]) > len(g) // 2:   # most parts spent by other software
            continue
        for a in g["address"]:
            uf.union(ins[txid][0], a)
        merged_split += 1
    root = {a: uf.find(a) for a in uf.p}
    members = defaultdict(list)
    for a, r in root.items():
        members[r].append(a)
    cid = {}
    for r, addrs in members.items():
        tag = hashlib.sha1(r.encode()).hexdigest()[:8].upper()
        name = f"C-{tag}" if len(addrs) > 1 else f"SOLO-{tag}"
        for a in addrs:
            cid[a] = name
    return pd.Series(cid, name="cluster_id"), {"cioh_merges": merged_cioh, "change_merges": merged_change,
                                               "peel_change_merges": merged_peel, "split_merges": merged_split,
                                               "fingerprint_change_merges": merged_fp,
                                               "clusters": len(members),
                                               "multi_address_clusters": sum(len(m) > 1 for m in members.values())}


def embedding_suggestions(frames, clusters: pd.Series, W: pd.DataFrame, max_nodes: int = 20000) -> dict:
    """Graph embeddings of the cluster flow graph → HDBSCAN groups of behaviourally similar clusters."""
    e = frames.tin[["txid", "address"]].merge(frames.tout[["txid", "address"]], on="txid", suffixes=("_s", "_d"))
    e["cs"], e["cd"] = e["address_s"].map(clusters), e["address_d"].map(clusters)
    e = e[e["cs"] != e["cd"]]
    nodes = pd.Index(pd.unique(pd.concat([e["cs"], e["cd"]])))[:max_nodes]
    if len(nodes) < 20:
        return {"groups": 0, "suggested_pairs": []}
    idx = {c: i for i, c in enumerate(nodes)}
    e = e[e["cs"].isin(idx) & e["cd"].isin(idx)]
    A = sparse.coo_matrix((np.ones(len(e)), (e["cs"].map(idx), e["cd"].map(idx))), shape=(len(nodes), len(nodes))).tocsr()
    A = A + A.T
    deg = np.asarray(A.sum(1)).ravel()
    Dm = sparse.diags(1 / np.sqrt(np.maximum(deg, 1)))
    emb = TruncatedSVD(n_components=min(16, len(nodes) - 1), random_state=42).fit_transform(Dm @ A @ Dm)
    beh = W.groupby(clusters.reindex(W.index))[["n_recv", "n_spend", "log_recv_btc", "hold_h", "spend_max_n_out"]].mean()
    Z = np.hstack([emb, StandardScaler().fit_transform(beh.reindex(nodes).fillna(0))])
    labels = HDBSCAN(min_cluster_size=4, copy=True).fit_predict(Z)
    groups = pd.Series(labels, index=nodes)
    groups = groups[groups >= 0]
    return {"groups": int(groups.nunique()), "clusters_in_groups": int(len(groups)), "group_of": groups.to_dict()}
