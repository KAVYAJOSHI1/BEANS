"""External validation on the Elliptic dataset (real Bitcoin transactions, Weber et al. 2019).

Elliptic has 203,769 transactions (4,545 illicit, 42,019 licit, the rest unknown), 234,355 payment-flow edges and
49 time steps. Its 166 features are anonymised: no addresses, amounts or IPs. BEANS's ingest pipeline therefore
cannot run on it; what can be validated on real data is the *modelling approach*:

1. Detection: BEANS's calibrated LightGBM recipe (beans/score/fuse.py) on local features (LF), all features (AF) and
   AF + graph features computed by us (in/out degree, PageRank, neighbour degree), on the standard temporal split
   (train on time steps 1-34, test on 35-49). The paper's random-forest baseline is re-run in the same code so the
   comparison is like for like, and the published numbers are listed next to it.
2. Seed propagation (the E4 idea): in each test time step, 30 % of the illicit transactions are revealed as seeds;
   personalised PageRank from them ranks the remaining labelled transactions. Measured: how well that separates
   the hidden illicit ones from licit ones, alone and combined with the detector.

The data is downloaded on demand and never committed (it has its own licence).
"""
import hashlib
import json
import time
import urllib.request
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, roc_auc_score

from beans.config import settings

URL = "https://data.pyg.org/datasets/elliptic/{}"
FILES = {  # zip → sha256 (as downloaded 2026-09-26)
    "elliptic_txs_features.csv.zip": "d33d62159e64b5e889f1a7ea880227c612775b58d409598855e0c4400fa52b3e",
    "elliptic_txs_edgelist.csv.zip": "a2f9f6b67a39da2d8cf87fe77b9db89571ba6d880e5dd5b5991dc45c80fa34ec",
    "elliptic_txs_classes.csv.zip": "4ca957f0ceffd5dd164e255c7d5ad9ee69a6fa64ae1dd94d6f113e5ebf3b07ba",
}
DEFAULT_DIR = settings.DATA_DIR / "external" / "elliptic"
REPORT = settings.MODELS_DIR / "elliptic_report.json"
TRAIN_LAST_STEP, CAL_FIRST_STEP = 34, 31
N_LOCAL = 93            # features 1-93 after the time step are local; the remaining 72 are neighbourhood aggregates
SEED_SHARE = 0.30       # like the synthetic benchmark: investigators know ~30 % of the illicit side

# Weber et al. 2019, Table 1 (illicit class, same temporal split): precision, recall, F1
PUBLISHED = {
    "Logistic regression (AF)": (0.404, 0.593, 0.481),
    "Random forest (LF)": (0.803, 0.611, 0.694),
    "Random forest (AF)": (0.956, 0.670, 0.788),
    "Random forest (AF + GCN embeddings)": (0.971, 0.675, 0.796),
    "GCN": (0.812, 0.512, 0.628),
    "Skip-GCN": (0.812, 0.623, 0.705),
}


def download(folder: Path = DEFAULT_DIR) -> Path:
    import zipfile
    folder.mkdir(parents=True, exist_ok=True)
    for name, sha in FILES.items():
        z = folder / name
        if not z.exists():
            urllib.request.urlretrieve(URL.format(name), z)
        if hashlib.sha256(z.read_bytes()).hexdigest() != sha:
            raise ValueError(f"{name}: checksum mismatch (corrupt or changed download)")
        with zipfile.ZipFile(z) as zf:
            zf.extractall(folder)
    return folder


def load(folder: Path = DEFAULT_DIR):
    # the id column must stay int64: float32 would round 9-digit ids and make them collide
    n_cols = len(pd.read_csv(folder / "elliptic_txs_features.csv", header=None, nrows=1).columns)
    feats = pd.read_csv(folder / "elliptic_txs_features.csv", header=None,
                        dtype={0: np.int64, **{i: np.float32 for i in range(1, n_cols)}})
    feats.columns = ["txId", "time_step"] + [f"f{i}" for i in range(1, n_cols - 1)]
    feats = feats.set_index("txId")
    assert feats.index.is_unique, "duplicate transaction ids"
    cls = pd.read_csv(folder / "elliptic_txs_classes.csv").set_index("txId")["class"].astype(str)
    y = cls.map({"1": 1.0, "2": 0.0}).reindex(feats.index)          # 1 = illicit, 0 = licit, NaN = unknown
    edges = pd.read_csv(folder / "elliptic_txs_edgelist.csv")
    return feats, y, edges


def graph_features(feats: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    """Structure computed by us from the edge list (not part of the published feature set)."""
    G = nx.DiGraph()
    G.add_nodes_from(feats.index)
    G.add_edges_from(edges[["txId1", "txId2"]].itertuples(index=False, name=None))
    indeg, outdeg = pd.Series(dict(G.in_degree())), pd.Series(dict(G.out_degree()))
    pr = pd.Series(nx.pagerank(G, alpha=0.85, max_iter=100, tol=1e-6))
    U = G.to_undirected(as_view=True)
    deg = pd.Series(dict(U.degree()))
    nbr_max = pd.Series({n: max((deg[m] for m in U[n]), default=0) for n in U.nodes})
    nbr_mean = pd.Series({n: (np.mean([deg[m] for m in U[n]]) if len(U[n]) else 0.0) for n in U.nodes})
    Gf = pd.DataFrame({"g_in_degree": indeg, "g_out_degree": outdeg, "g_log_pagerank": np.log(pr),
                       "g_nbr_max_degree": nbr_max, "g_nbr_mean_degree": nbr_mean}).reindex(feats.index)
    return Gf.astype(np.float32)


def _metrics(y, p, threshold=0.5) -> dict:
    pred = (p >= threshold).astype(int)
    return {"precision": round(float(precision_score(y, pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
            "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
            "pr_auc": round(float(average_precision_score(y, p)), 4),
            "roc_auc": round(float(roc_auc_score(y, p)), 4)}


def _ece(y, p) -> float:
    idx = np.clip((p * 10).astype(int), 0, 9)
    return round(float(sum((idx == b).mean() * abs(p[idx == b].mean() - y[idx == b].mean()) for b in range(10) if (idx == b).any())), 4)


def _beans_model(X_tr, y_tr, steps_tr):
    """BEANS fusion recipe: LightGBM, isotonic calibration on the latest training steps (held out from fitting)."""
    from beans.score.fuse import _lgbm
    fit, cal = steps_tr < CAL_FIRST_STEP, steps_tr >= CAL_FIRST_STEP
    pw = max(1.0, (y_tr[fit] == 0).sum() / max((y_tr[fit] == 1).sum(), 1))
    clf = _lgbm(pw).fit(X_tr[fit], y_tr[fit])
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(clf.predict_proba(X_tr[cal])[:, 1], y_tr[cal])
    return lambda X: iso.predict(clf.predict_proba(X)[:, 1])


def run(folder: Path = DEFAULT_DIR, seed: int = 42) -> dict:
    t0 = time.time()
    feats, y, edges = load(folder)
    Gf = graph_features(feats, edges)
    lab = y.dropna()
    steps = feats.loc[lab.index, "time_step"].values
    tr, te = steps <= TRAIN_LAST_STEP, steps > TRAIN_LAST_STEP
    yl = lab.values.astype(int)
    feature_sets = {
        "LF": [c for c in feats.columns if c != "time_step"][:N_LOCAL],
        "AF": [c for c in feats.columns if c != "time_step"],
    }
    X_all = feats.join(Gf)
    feature_sets["AF + graph"] = feature_sets["AF"] + list(Gf.columns)

    results, test_scores = {}, {}
    for name, cols in feature_sets.items():
        X = X_all.loc[lab.index, cols].values
        predict = _beans_model(X[tr], yl[tr], steps[tr])
        p = predict(X[te])
        results[f"BEANS LightGBM + calibration ({name})"] = {**_metrics(yl[te], p), "ece": _ece(yl[te], p)}
        test_scores[name] = p
    for name in ("LF", "AF"):   # the paper's baseline, re-run here: RF, 50 trees, 50 features per split
        X = X_all.loc[lab.index, feature_sets[name]].values
        rf = RandomForestClassifier(n_estimators=50, max_features=50, n_jobs=-1, random_state=seed).fit(X[tr], yl[tr])
        results[f"Random forest ({name}), re-run here"] = _metrics(yl[te], rf.predict_proba(X[te])[:, 1])

    best = "AF + graph"
    p_best = test_scores[best]
    per_step = []
    for s in sorted(set(steps[te])):
        m = steps[te] == s
        if yl[te][m].sum():
            per_step.append({"time_step": int(s), "illicit": int(yl[te][m].sum()),
                             "f1": round(float(f1_score(yl[te][m], (p_best[m] >= 0.5).astype(int), zero_division=0)), 4)})

    report = {
        "dataset": {"transactions": int(len(feats)), "edges": int(len(edges)), "illicit": int((y == 1).sum()),
                    "licit": int((y == 0).sum()), "unknown": int(y.isna().sum()), "time_steps": int(feats["time_step"].max())},
        "split": {"train_steps": f"1-{TRAIN_LAST_STEP}", "test_steps": f"{TRAIN_LAST_STEP + 1}-{int(feats['time_step'].max())}",
                  "calibration_steps": f"{CAL_FIRST_STEP}-{TRAIN_LAST_STEP}", "train_labelled": int(tr.sum()),
                  "test_labelled": int(te.sum()), "test_illicit": int(yl[te].sum())},
        "detection": results,
        "published_weber_2019": {k: dict(zip(("precision", "recall", "f1"), v)) for k, v in PUBLISHED.items()},
        "per_test_step_f1": per_step,
        "propagation": _propagation(feats, lab, edges, dict(zip(lab.index[te], p_best)), seed),
        "seconds": round(time.time() - t0, 1),
        "notes": ["Elliptic features are anonymised: no addresses, amounts or IPs, so this validates the modelling "
                  "approach, not BEANS's ingest / clustering / network layer.",
                  "Published numbers are quoted from Weber et al. 2019 (arXiv:1908.02591), Table 1.",
                  "Time steps after 43 follow the closure of a large dark market; every published model degrades there."],
    }
    settings.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2))
    return report


def _propagation(feats, lab, edges, model_p: dict, seed: int) -> dict:
    """Per test step: reveal 30 % of illicit as seeds, PPR from them, rank the other labelled transactions."""
    rng = np.random.default_rng(seed)
    step_of = feats["time_step"]
    G = nx.Graph()
    G.add_edges_from(edges[["txId1", "txId2"]].itertuples(index=False, name=None))
    rows = []
    for s in range(TRAIN_LAST_STEP + 1, int(step_of.max()) + 1):
        in_step = lab.index[step_of.loc[lab.index].values == s]
        ill = [t for t in in_step if lab[t] == 1]
        if len(ill) < 4:
            continue
        seeds = set(rng.choice(ill, size=max(1, int(round(SEED_SHARE * len(ill)))), replace=False).tolist())
        nodes = set(step_of.index[step_of.values == s]) & set(G.nodes)
        H = G.subgraph(nodes)
        pers = {n: (1.0 if n in seeds else 0.0) for n in H.nodes}
        ppr = nx.pagerank(H, alpha=0.85, personalization=pers, max_iter=100, tol=1e-8) if any(pers.values()) else {}
        dist = nx.multi_source_dijkstra_path_length(H, seeds & set(H.nodes), cutoff=3) if seeds & set(H.nodes) else {}
        hidden = [t for t in in_step if t not in seeds]
        ppr_rank = pd.Series({t: ppr.get(t, 0.0) for t in hidden}).rank(pct=True)
        for t in hidden:
            rows.append({"step": s, "y": int(lab[t]), "ppr_pct": float(ppr_rank[t]), "within_2_hops": int(dist.get(t, 99) <= 2),
                         "model": float(model_p.get(t, 0.0))})
    d = pd.DataFrame(rows)
    if d.empty:
        return {}
    d["combined"] = 1 - (1 - d["model"]) * (1 - 0.5 * d["ppr_pct"] * d["within_2_hops"])
    ill, lic = d[d.y == 1], d[d.y == 0]
    auc = lambda c: round(float(average_precision_score(d["y"], d[c])), 4)  # noqa: E731
    return {"seed_share": SEED_SHARE, "hidden_illicit": int(len(ill)), "hidden_licit": int(len(lic)),
            "hidden_illicit_within_2_hops_of_a_seed": round(float(ill["within_2_hops"].mean()), 4),
            "licit_within_2_hops_of_a_seed": round(float(lic["within_2_hops"].mean()), 4),
            "pr_auc_ppr_only": auc("ppr_pct"), "pr_auc_model_only": auc("model"), "pr_auc_model_plus_seeds": auc("combined"),
            "base_rate": round(float(d["y"].mean()), 4)}
