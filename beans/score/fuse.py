"""Fusion: wallet-level P(illicit) from all engine outputs + behaviour + network features.

Training (when ground truth is available):
  * StratifiedGroupKFold by entity: a criminal's wallets are never on both the train and test side.
  * inside each fold: LightGBM on 75% of the training entities, isotonic calibration on the other 25%.
  * out-of-fold calibrated probabilities are what the dashboard shows and what metrics are computed on.
  * ablation: the same procedure without network-layer features (does network ↔ chain correlation help?).
  * a second LightGBM predicts the typology (ransomware, peel chain, …) of illicit-looking wallets.
Without labels, the persisted models from the last training run are applied.
"""
import warnings

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit, StratifiedGroupKFold

from beans.config import settings

FUSION_MODEL = settings.MODELS_DIR / "fusion.joblib"
TRAINING_SET = settings.MODELS_DIR / "fusion_training_set.parquet"   # kept so analyst feedback can be added later
warnings.filterwarnings("ignore", message=".*does not have valid feature names.*")
# Wallet-level money-context features help detection but add noise to typology (3-seed benchmark,
# scripts/evaluate_seeds.py); the typology model sees their cluster-level aggregates instead.
TYPOLOGY_EXCLUDE_PREFIXES = ("fund_", "spend_to_consolidated", "is_consolidated")


def _lgbm(pos_weight: float):
    return LGBMClassifier(n_estimators=250, learning_rate=0.05, num_leaves=15, min_child_samples=10,
                          subsample=0.9, subsample_freq=1, colsample_bytree=0.8, scale_pos_weight=pos_weight,
                          verbose=-1, random_state=42, deterministic=True, force_row_wise=True)


def _oof(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, n_splits: int = 5, members: list = None,
         weights: np.ndarray = None) -> np.ndarray:
    pw = max(1.0, (y == 0).sum() / max((y == 1).sum(), 1))
    oof = np.zeros(len(X))
    for tr, te in StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=42).split(X, y, groups):
        fit_i, cal_i = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=1).split(tr, groups=groups[tr]))
        fit_i, cal_i = tr[fit_i], tr[cal_i]
        clf = _lgbm(pw).fit(X.iloc[fit_i], y[fit_i], sample_weight=None if weights is None else weights[fit_i])
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1)
        if len(set(y[cal_i])) > 1:
            iso.fit(clf.predict_proba(X.iloc[cal_i])[:, 1], y[cal_i])
        else:
            iso = None
        raw = clf.predict_proba(X.iloc[te])[:, 1]
        oof[te] = iso.predict(raw) if iso is not None else raw
        if members is not None:
            members.append((clf, iso))
    return oof


def _metrics(y, p) -> dict:
    order = np.argsort(-p)
    bins = np.linspace(0, 1, 11)
    idx = np.clip(np.digitize(p, bins) - 1, 0, 9)
    rel, ece = [], 0.0
    for b in range(10):
        m = idx == b
        if m.any():
            rel.append({"bin": f"{bins[b]:.1f}-{bins[b + 1]:.1f}", "n": int(m.sum()),
                        "mean_predicted": round(float(p[m].mean()), 4), "observed_rate": round(float(y[m].mean()), 4)})
            ece += m.mean() * abs(p[m].mean() - y[m].mean())
    return {"pr_auc": round(float(average_precision_score(y, p)), 4), "roc_auc": round(float(roc_auc_score(y, p)), 4),
            "precision_at_50": round(float(y[order[:50]].mean()), 4),
            "precision_at_100": round(float(y[order[:100]].mean()), 4),
            "recall_at_p50": round(float(((p >= 0.5) & (y == 1)).sum() / max(y.sum(), 1)), 4),
            "precision_at_p50": round(float(y[p >= 0.5].mean()), 4) if (p >= 0.5).any() else None,
            "ece": round(float(ece), 4), "base_rate": round(float(y.mean()), 4), "reliability": rel}


def train(X: pd.DataFrame, y: pd.Series, groups: pd.Series, typology: pd.Series, network_cols: list[str],
          weights: pd.Series = None, clusters: pd.Series = None) -> tuple[pd.Series, pd.Series, dict]:
    yv, gv = y.values.astype(int), groups.values
    wv = None if weights is None else weights.reindex(X.index).fillna(1.0).values
    members: list = []
    oof = _oof(X, yv, gv, members=members, weights=wv)
    report = {"wallets": int(len(X)), "illicit_wallets": int(yv.sum()), "entities": int(pd.Series(gv).nunique()),
              "illicit_entities": int(pd.Series(gv[yv == 1]).nunique()), **_metrics(yv, oof)}
    no_net = [c for c in X.columns if c not in network_cols]
    report["ablation"] = {"pr_auc_with_network": report["pr_auc"],
                          "pr_auc_without_network": round(float(average_precision_score(yv, _oof(X[no_net], yv, gv))), 4)}

    # typology of illicit wallets (grouped CV again), pooled over each CIOH cluster (one owner → one typology)
    ill = yv == 1
    typ_cols = [c for c in X.columns if not c.startswith(TYPOLOGY_EXCLUDE_PREFIXES)]
    Xi, ti, gi = X.loc[ill, typ_cols], typology.values[ill], gv[ill]
    typ_oof = pd.Series("UNKNOWN", index=X.index)
    typ_acc = typ_acc_raw = None
    if len(set(ti)) > 1 and pd.Series(gi).nunique() >= 4:
        classes = sorted(set(ti))
        proba = pd.DataFrame(0.0, index=Xi.index, columns=classes)
        k = min(4, pd.Series(gi).nunique())
        for tr, te in GroupKFold(n_splits=k).split(Xi, groups=gi):
            if len(set(ti[tr])) < 2:
                proba.iloc[te, classes.index(ti[tr][0])] = 1.0
                continue
            m = _typology_model().fit(Xi.iloc[tr], ti[tr], sample_weight=_entity_balance(gi[tr]))
            proba.iloc[te, [classes.index(c) for c in m.classes_]] = m.predict_proba(Xi.iloc[te])
        typ_acc_raw = round(float((proba.idxmax(axis=1).values == ti).mean()), 4)
        pooled = pool_typology(proba, None if clusters is None else clusters.reindex(Xi.index),
                               pd.Series(oof, index=X.index).reindex(Xi.index))
        typ_acc = round(float((pooled.values == ti).mean()), 4)
        typ_oof.loc[Xi.index] = pooled
    report["typology_accuracy_grouped_cv"] = typ_acc
    report["typology_accuracy_grouped_cv_unpooled"] = typ_acc_raw

    pw = max(1.0, (yv == 0).sum() / max(yv.sum(), 1))
    final = _lgbm(pw).fit(X, yv, sample_weight=wv)   # used for SHAP explanations
    X.assign(_y=yv, _group=gv, _typology=typology.values,
             _weight=1.0 if wv is None else wv).to_parquet(TRAINING_SET)
    typ_model = _typology_model().fit(Xi, ti, sample_weight=_entity_balance(gi)) if len(set(ti)) > 1 else None
    FUSION_MODEL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": final, "members": members, "features": list(X.columns), "typology_model": typ_model,
                 "typology_features": typ_cols,
                 "typology_default": ti[0] if len(ti) else "UNKNOWN"}, FUSION_MODEL)
    # wallets flagged by the OOF model but not illicit in truth still need a typology guess for display
    if typ_model is not None:
        need = (typ_oof == "UNKNOWN") & (oof >= 0.3)
        if need.any():
            typ_oof.loc[need] = typ_model.predict(X.loc[need.values, typ_cols])
    return pd.Series(oof, index=X.index), typ_oof, report


def _entity_balance(groups: np.ndarray) -> np.ndarray:
    """Weight 1/|entity| so a 300-wallet operation and a 5-wallet one teach the typology model equally."""
    sizes = pd.Series(groups).map(pd.Series(groups).value_counts()).values
    return len(groups) / (sizes * pd.Series(groups).nunique())


def _typology_model():
    return LGBMClassifier(n_estimators=150, learning_rate=0.08, num_leaves=15, min_child_samples=3,
                          verbose=-1, random_state=42, deterministic=True, force_row_wise=True)


def pool_typology(proba: pd.DataFrame, clusters: pd.Series = None, weight: pd.Series = None) -> pd.Series:
    """Typology per wallet = argmax of the P(illicit)-weighted mean class probabilities of its CIOH cluster.

    Single-address ("SOLO…") clusters keep their own prediction."""
    if clusters is None:
        return proba.idxmax(axis=1)
    w = (weight if weight is not None else pd.Series(1.0, index=proba.index)).reindex(proba.index).fillna(0).clip(lower=1e-3)
    cl = clusters.reindex(proba.index).fillna("SOLO").astype(str)
    solo = cl.str.startswith("SOLO")
    key = cl.where(~solo, "w:" + proba.index.astype(str))
    pooled = proba.mul(w, axis=0).groupby(key.values).transform("sum")
    return pooled.idxmax(axis=1)


def predict(X: pd.DataFrame, clusters: pd.Series = None) -> tuple[pd.Series, pd.Series, dict]:
    if not FUSION_MODEL.exists():
        return pd.Series(0.0, index=X.index), pd.Series("UNKNOWN", index=X.index), {"unavailable": "no trained fusion model"}
    b = joblib.load(FUSION_MODEL)
    Xf = X.reindex(columns=b["features"], fill_value=0)
    # calibrated ensemble of the cross-validation members (each: LightGBM + its isotonic calibrator)
    ps = [iso.predict(clf.predict_proba(Xf)[:, 1]) if iso is not None else clf.predict_proba(Xf)[:, 1]
          for clf, iso in b["members"]]
    p = pd.Series(np.mean(ps, axis=0), index=X.index)
    tm = b["typology_model"]
    if tm is not None:
        Xt = Xf[b.get("typology_features", b["features"])]
        typ = pool_typology(pd.DataFrame(tm.predict_proba(Xt), index=X.index, columns=tm.classes_), clusters, p)
    else:
        typ = pd.Series(b["typology_default"], index=X.index)
    return p, typ, {"used_persisted_model": FUSION_MODEL.name}


def final_model():
    return joblib.load(FUSION_MODEL)["model"] if FUSION_MODEL.exists() else None


def training_set():
    return pd.read_parquet(TRAINING_SET) if TRAINING_SET.exists() else None
