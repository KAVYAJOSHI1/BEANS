"""E8: same-operator candidates. Which other wallet clusters behave like this one?

Common-input clustering (E1) only joins addresses that sign together. An operator who rotates wallets leaves
unlinked clusters behind (E1 completeness for illicit actors is ~0.74). A cluster's *habits* survive the rotation:

- network: the IPs its transactions were first seen from (rare IPs weigh more, relays shared by many clusters little);
- wallet software: version / nLockTime / RBF fingerprint of the transactions it signs;
- script type of the transactions it signs;
- daily rhythm: hour-of-day histogram of its transactions (the operator's time zone);
- fee habit: median log fee rate.

Each signal gives a similarity in [0, 1] between two clusters. For categorical signals it is
Σ sqrt(share_a · share_b) · idf(category) / ln N, so matching on something rare scores high and matching on the
default (everyone uses P2WPKH) scores low. The behavioural signals are averaged over the ones both clusters have;
shared network identity is combined by noisy-OR, because sharing an IP is evidence for and not sharing is none against:

    score = 1 − (1 − 0.6 · behaviour) · (1 − 0.9 · network)

Output is a ranked lead list with the per-signal similarities and the shared IPs. It is a lead for an analyst,
never a merge: clusters are not changed and nothing here feeds the fusion model. Ground truth is read only by `evaluate`.
"""
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import sparse

from beans.features.extractors import tx_fingerprint

MIN_TX = 3              # transactions a cluster must have signed to have a fingerprint
MAX_TX = 400            # busier clusters are services (exchanges, pools, merchants), not operators
TOP_K = 5
BEHAVIOUR_WEIGHTS = {"software": 1.0, "script": 0.5, "diurnal": 1.0, "fee": 0.3}
BEHAVIOUR_CAP, NETWORK_CAP = 0.6, 0.9
HOUR_KERNEL = np.array([0.25, 0.5, 0.25])
FEE_SCALE = 0.35        # log-fee-rate distance at which fee similarity falls to 1/e


class Fingerprints:
    def __init__(self, clusters, n_tx, blocks, has, fee, ip_counts):
        self.clusters, self.n_tx, self.blocks, self.has, self.fee, self.ip_counts = clusters, n_tx, blocks, has, fee, ip_counts
        self.index = {c: i for i, c in enumerate(clusters)}

    def similarity(self, queries: List[str]) -> Dict[str, np.ndarray]:
        q = [self.index[c] for c in queries]
        out = {}
        for name in ("ip", *BEHAVIOUR_WEIGHTS):
            if name == "diurnal":
                s = self.blocks[name][q] @ self.blocks[name].T
            elif name == "fee":
                s = np.exp(-np.abs(self.fee[q][:, None] - self.fee[None, :]) / FEE_SCALE)
            else:
                s = (self.blocks[name][q] @ self.blocks[name].T).toarray()
            out[name] = np.clip(s, 0.0, 1.0) * (self.has[name][q][:, None] & self.has[name][None, :])
        return out


def _tfidf_block(d: pd.DataFrame, col: str, row_of: Dict[str, int], n: int):
    c = d.dropna(subset=[col]).groupby(["cluster", col]).size().reset_index(name="k")
    if c.empty:
        return sparse.csr_matrix((n, 1)), np.zeros(n, bool)
    cats = {v: i for i, v in enumerate(sorted(c[col].astype(str).unique()))}
    c["row"], c["col"] = c["cluster"].map(row_of), c[col].astype(str).map(cats)
    c["tf"] = c["k"] / c.groupby("row")["k"].transform("sum")
    df = c.groupby("col")["row"].nunique()
    idf = np.log((n + 1) / (df + 1)) + 1e-9
    c["v"] = np.sqrt(c["tf"]) * np.sqrt(c["col"].map(idf)) / np.sqrt(np.log(n + 1))
    M = sparse.csr_matrix((c["v"], (c["row"], c["col"])), shape=(n, len(cats)))
    has = np.zeros(n, bool)
    has[c["row"].unique()] = True
    return M, has


def build(f, clusters: pd.Series, X_tx: pd.DataFrame, known_addresses=()) -> Optional[Fingerprints]:
    tin = f.tin[["txid", "address"]].copy()
    tin["cluster"] = tin["address"].map(clusters)
    if known_addresses:
        services = set(tin.loc[tin["address"].isin(set(known_addresses)), "cluster"].dropna())
    else:
        services = set()
    tin = tin.dropna(subset=["cluster"]).drop_duplicates(["cluster", "txid"])
    n_tx = tin.groupby("cluster").size()
    keep = n_tx[(n_tx >= MIN_TX) & (n_tx <= MAX_TX)].index.difference(list(services))
    if len(keep) < 20:
        return None
    tin = tin[tin["cluster"].isin(keep)]
    tx = f.tx.set_index("txid")
    d = tin.assign(
        hour=tx["ts"].reindex(tin["txid"]).dt.hour.values,
        software=tx_fingerprint(f.tx).reindex(tin["txid"]).values,
        script=tx["script_type"].reindex(tin["txid"]).values,
        fee=np.log1p(X_tx["fee_rate"].reindex(tin["txid"]).values),
        ip=(f.spy.set_index("txid")["spy_ip"].reindex(tin["txid"]).values if len(f.spy) else np.nan))
    names = sorted(keep)
    row_of = {c: i for i, c in enumerate(names)}
    n = len(names)
    blocks, has = {}, {}
    for col in ("software", "script", "ip"):
        blocks[col], has[col] = _tfidf_block(d, col, row_of, n)
    hist = np.zeros((n, 24))
    h = d.dropna(subset=["hour"])
    np.add.at(hist, (h["cluster"].map(row_of).values, h["hour"].astype(int).values), 1.0)
    sm = sum(np.roll(hist, s, axis=1) * w for s, w in zip((-1, 0, 1), HOUR_KERNEL))
    sm = np.sqrt(sm / np.maximum(sm.sum(1, keepdims=True), 1e-12))
    blocks["diurnal"], has["diurnal"] = sm, hist.sum(1) >= MIN_TX
    fee = d.groupby("cluster")["fee"].median().reindex(names)
    has["fee"] = fee.notna().values
    ipc = {}
    for (c, ip), k in d.dropna(subset=["ip"]).groupby(["cluster", "ip"]).size().items():
        ipc.setdefault(c, {})[ip] = int(k)
    return Fingerprints(names, n_tx.reindex(names).values, blocks, has, fee.fillna(0).values, ipc)


def _combine(fp: Fingerprints, sims: Dict[str, np.ndarray], q: List[int]) -> np.ndarray:
    num = np.zeros_like(sims["ip"])
    den = np.zeros_like(sims["ip"])
    for k, w in BEHAVIOUR_WEIGHTS.items():
        avail = fp.has[k][q][:, None] & fp.has[k][None, :]
        num += w * sims[k] * avail
        den += w * avail
    behaviour = np.divide(num, den, out=np.zeros_like(num), where=den > 0)
    return 1 - (1 - BEHAVIOUR_CAP * behaviour) * (1 - NETWORK_CAP * sims["ip"]), behaviour


def candidates(fp: Optional[Fingerprints], queries: List[str], top: int = TOP_K,
               min_score: float = 0.0) -> Dict[str, List[dict]]:
    """Top same-operator candidates for each query cluster (the query itself excluded)."""
    qs = [c for c in dict.fromkeys(queries) if fp is not None and c in fp.index]
    if not qs:
        return {}
    q = [fp.index[c] for c in qs]
    sims = fp.similarity(qs)
    score, behaviour = _combine(fp, sims, q)
    score[np.arange(len(q)), q] = -1
    out = {}
    for r, c in enumerate(qs):
        order = np.argsort(-score[r], kind="stable")[:top]
        rows = []
        for j in order:
            if score[r, j] < min_score:
                break
            other = fp.clusters[j]
            shared = sorted(set(fp.ip_counts.get(c, {})) & set(fp.ip_counts.get(other, {})))
            rows.append({"cluster_id": other, "score": round(float(score[r, j]), 4),
                         "behaviour": round(float(behaviour[r, j]), 4),
                         "signals": {k: round(float(sims[k][r, j]), 3) for k in ("ip", *BEHAVIOUR_WEIGHTS)},
                         "shared_ips": shared[:5], "transactions": int(fp.n_tx[j])})
        out[c] = rows
    return out


def evaluate(fp: Optional[Fingerprints], queries: List[str], labels: pd.DataFrame, clusters: pd.Series,
             ks=(1, 5, 10)) -> dict:
    """Do the top-k candidates contain another cluster of the same real operator? (ground truth, evaluation only)"""
    if fp is None:
        return {}
    ent = clusters.to_frame("cluster").join(labels["entity_id"], how="inner").dropna()
    owner = ent.groupby("cluster")["entity_id"].agg(lambda s: s.mode().iat[0])
    siblings = owner.groupby(owner).groups
    qs = [c for c in dict.fromkeys(queries) if c in fp.index and c in owner.index]
    if not qs:
        return {}
    q = [fp.index[c] for c in qs]
    sims = fp.similarity(qs)
    score, behaviour = _combine(fp, sims, q)
    score[np.arange(len(q)), q] = -1
    behaviour = behaviour.copy()
    behaviour[np.arange(len(q)), q] = -1
    ranks, b_ranks, base = [], [], {k: [] for k in ks}
    for r, c in enumerate(qs):
        sib = [s for s in siblings[owner[c]] if s != c and s in fp.index]
        if not sib:
            continue
        order = np.argsort(-score[r], kind="stable")
        pos = {fp.clusters[j]: i for i, j in enumerate(order)}
        ranks.append(min(pos[s] for s in sib) + 1)
        b_pos = {fp.clusters[j]: i for i, j in enumerate(np.argsort(-behaviour[r], kind="stable"))}
        b_ranks.append(min(b_pos[s] for s in sib) + 1)
        for k in ks:
            base[k].append(1 - np.prod([1 - k / max(len(fp.clusters) - 1 - i, 1) for i in range(len(sib))]))
    if not ranks:
        return {"queries_with_a_findable_sibling": 0}
    ranks = np.array(ranks)
    rep = {"queries_with_a_findable_sibling": int(len(ranks)), "fingerprinted_clusters": int(len(fp.clusters)),
           "mrr": round(float(np.mean(1 / ranks)), 3), "median_rank": float(np.median(ranks))}
    for k in ks:
        rep[f"hit_at_{k}"] = round(float(np.mean(ranks <= k)), 3)
        rep[f"hit_at_{k}_random"] = round(float(np.mean(base[k])), 4)
    b_ranks = np.array(b_ranks)
    rep["without_network"] = {f"hit_at_{k}": round(float(np.mean(b_ranks <= k)), 3) for k in ks}
    rep["without_network"]["mrr"] = round(float(np.mean(1 / b_ranks)), 3)
    rep["note"] = ("synthetic operators broadcast from their own IPs, which real relays do not allow; "
                   "`without_network` is the number to expect where IP identity is unavailable")
    rep["ablation_hit_at_5"] = {}
    for name in ("ip", *BEHAVIOUR_WEIGHTS):
        only = {k: np.zeros_like(v) for k, v in sims.items()}
        only[name] = sims[name]
        sc = (1 - (1 - NETWORK_CAP * only["ip"])) if name == "ip" else \
            BEHAVIOUR_CAP * only[name]
        sc[np.arange(len(q)), q] = -1
        hits = []
        for r, c in enumerate(qs):
            sib = {s for s in siblings[owner[c]] if s != c and s in fp.index}
            if sib:
                top = np.argsort(-sc[r], kind="stable")[:5]
                hits.append(any(fp.clusters[j] in sib for j in top) and sc[r, top[0]] > 0)
        rep["ablation_hit_at_5"][name] = round(float(np.mean(hits)), 3)
    return rep
