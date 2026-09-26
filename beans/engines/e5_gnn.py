"""E5: graph neural network, SIGN-style (Frasca et al. 2020, "SIGN: Scalable Inception Graph Neural Networks").

A GNN learns from what a node's neighbourhood looks like. SIGN computes the neighbourhood aggregation up front
(mean over 1-hop and 2-hop neighbours, separately along and against the money flow) and lets a learned model take it
from there. That is the same message passing a GCN / GraphSAGE layer does, without backpropagating through the graph,
so it runs on a CPU in seconds with scipy and needs no deep-learning framework in the offline image.

Service hubs (exchanges, pools: degree > HUB_DEGREE) are cut out of the aggregation, as in E4: their neighbourhood is
everyone, so it says nothing about a wallet.

The aggregated columns join the fusion matrix (prefix `gnn_`); the calibrated LightGBM fusion is the GNN's readout.
"""
import numpy as np
import pandas as pd
from scipy import sparse

from beans.engines.e4_propagate import HUB_DEGREE

# per-wallet signals that are propagated (no labels, no seed-derived scores)
BASE_COLS = ["share_risky_asn", "log_recv_btc", "log_sent_btc", "spend_max_n_out", "fund_max_n_in",
             "max_equal_output_share", "max_peel_shape", "max_p_peel", "max_p_coinjoin", "max_p_fan_out",
             "max_p_round_trip", "anomaly", "n_spend_countries", "fund_below_round", "spend_to_consolidated"]
HOPS = 2


def _row_normalise(A: sparse.csr_matrix) -> sparse.csr_matrix:
    deg = np.asarray(A.sum(1)).ravel()
    return sparse.diags(1.0 / np.maximum(deg, 1)) @ A


def sign_features(G, W: pd.DataFrame, cols=None) -> pd.DataFrame:
    """[A_out^k X, A_in^k X] for k = 1..HOPS, where A_* are hub-free, row-normalised (mean) flow adjacencies."""
    cols = [c for c in (cols or BASE_COLS) if c in W.columns]
    idx = {a: i for i, a in enumerate(W.index)}
    X = W[cols].replace([np.inf, -np.inf], 0).fillna(0).values.astype(np.float64)
    X = (X - X.mean(0)) / np.where(X.std(0) > 0, X.std(0), 1)
    rows, cols_, n = [], [], len(W)
    for u, v in G.edges():
        if u in idx and v in idx and G.degree(u) <= HUB_DEGREE and G.degree(v) <= HUB_DEGREE:
            rows.append(idx[u])
            cols_.append(idx[v])
    A = sparse.csr_matrix((np.ones(len(rows)), (rows, cols_)), shape=(n, n))
    A.data[:] = 1.0                                   # unweighted: a structural view, amounts are in the base features
    ops = {"out": _row_normalise(A), "in": _row_normalise(A.T.tocsr())}
    out = {}
    for name, op in ops.items():
        H = X
        for k in range(1, HOPS + 1):
            H = op @ H
            for j, c in enumerate(cols):
                out[f"gnn_{name}{k}_{c}"] = H[:, j]
    return pd.DataFrame(out, index=W.index).astype(np.float32)
