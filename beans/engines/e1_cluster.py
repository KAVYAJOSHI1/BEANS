"""E1: entity clustering = common-input-ownership (CIOH) + change heuristic + graph-embedding suggestions.

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
    ins = frames.tin.groupby("txid")["address"].apply(list)
    merged_cioh = merged_change = 0
    for txid, addrs in ins.items():
        if txid in coinjoin_txids or len(addrs) < 2:
            continue
        for a in addrs[1:]:
            uf.union(addrs[0], a)
        merged_cioh += 1
    # change heuristic (conservative): 2 outputs, exactly one has full 8-decimal precision → that one is change
    first_seen = frames.tout.groupby("address")["ts"].min()
    two = frames.tout[frames.tout["txid"].isin(X_tx.index[(X_tx["n_out"] == 2) & (X_tx["n_in"] >= 1)])]
    for txid, g in two.groupby("txid"):
        if txid in coinjoin_txids or txid not in ins.index:
            continue
        prec = [(_decimals(v) >= 7, a, ts) for a, v, ts in zip(g["address"], g["amount"], g["ts"])]
        change = [a for p, a, ts in prec if p and first_seen.get(a) == ts]
        if len(change) == 1 and sum(p for p, _, _ in prec) == 1:
            uf.union(ins[txid][0], change[0])
            merged_change += 1
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
