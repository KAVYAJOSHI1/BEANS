"""E3: transaction-shape classifier (normal / peel / coinjoin / fan_out / fan_in / round_trip).

Structural signals (equal-output groups, peel ratio + chain length, returns-to-input, respend timing) are
FEATURES; a LightGBM model learns the decision from labelled transactions. Out-of-fold predictions (grouped by
the entity that created the tx) are used downstream so fusion never sees in-sample probabilities.
"""
import warnings
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedGroupKFold

from beans.config import settings

CLASSES = ["normal", "peel", "coinjoin", "fan_out", "fan_in", "round_trip"]
MODEL = settings.MODELS_DIR / "e3_txclass.joblib"
warnings.filterwarnings("ignore", message=".*does not have valid feature names.*")


def _model():
    return LGBMClassifier(n_estimators=200, learning_rate=0.08, num_leaves=31, class_weight="balanced",
                          min_child_samples=5, verbose=-1, random_state=42, deterministic=True, force_row_wise=True)


def _proba(clf, X) -> np.ndarray:
    p = np.zeros((len(X), len(CLASSES)))
    for j, c in enumerate(clf.classes_):
        p[:, CLASSES.index(c)] = clf.predict_proba(X)[:, j]
    return p


def run(X: pd.DataFrame, labels: Optional[pd.DataFrame]) -> tuple[pd.DataFrame, dict]:
    """labels: DataFrame indexed by txid with tx_class, entity_id (or None → use the persisted model)."""
    feats = list(X.columns)
    report = {"features": feats}
    if labels is not None and len(labels):
        lab = labels.reindex(X.index).dropna(subset=["tx_class"])
        Xl, y = X.loc[lab.index], lab["tx_class"].values
        # group by (entity, day): one entity's same-day activity (e.g. a peel chain) never straddles train/test,
        # while shapes produced by a single actor over many days (a CoinJoin coordinator) remain learnable
        day = pd.to_datetime(X.attrs.get("ts", pd.Series(dtype="datetime64[ns]")).reindex(lab.index)).dt.strftime("%m%d")
        groups = (lab["entity_id"].astype(str) + "|" + day.fillna("")).values
        oof = np.zeros((len(Xl), len(CLASSES)))
        n_splits = min(5, max(2, pd.Series(groups).nunique() // 20))
        for tr, te in StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=42).split(Xl, y, groups):
            clf = _model().fit(Xl.iloc[tr], y[tr])
            oof[te] = _proba(clf, Xl.iloc[te])
        pred = np.array(CLASSES)[oof.argmax(1)]
        report.update({"trained_on": int(len(Xl)), "cv_folds": n_splits,
                       "macro_f1": round(float(f1_score(y, pred, average="macro")), 4),
                       "per_class_f1": {c: round(float(v), 4) for c, v in zip(
                           CLASSES, f1_score(y, pred, labels=CLASSES, average=None, zero_division=0))},
                       "confusion": {"labels": CLASSES, "matrix": pd.crosstab(
                           pd.Categorical(y, CLASSES), pd.Categorical(pred, CLASSES), dropna=False).values.tolist()}})
        final = _model().fit(Xl, y)
        MODEL.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": final, "features": feats}, MODEL)
        probs = pd.DataFrame(_proba(final, X), index=X.index, columns=[f"p_{c}" for c in CLASSES])
        probs.loc[Xl.index] = oof   # labelled txs get honest out-of-fold probabilities
    elif MODEL.exists():
        bundle = joblib.load(MODEL)
        probs = pd.DataFrame(_proba(bundle["model"], X[bundle["features"]]), index=X.index,
                             columns=[f"p_{c}" for c in CLASSES])
        report["used_persisted_model"] = str(MODEL.name)
    else:
        probs = pd.DataFrame(0.0, index=X.index, columns=[f"p_{c}" for c in CLASSES])
        probs["p_normal"] = 1.0
        report["unavailable"] = "no labels and no trained model"
    probs["tx_class_pred"] = np.array(CLASSES)[probs[[f"p_{c}" for c in CLASSES]].values.argmax(1)]
    return probs, report
