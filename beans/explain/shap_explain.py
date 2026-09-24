"""Per-wallet SHAP explanations of the fusion model (shap.TreeExplainer, exact for tree ensembles)."""
import warnings

import numpy as np
import pandas as pd
import shap


def explain(model, X: pd.DataFrame, top_k: int = 6) -> tuple[dict, list]:
    """Returns ({address: [{feature, value, impact}]}, global importance list). Impact is in log-odds."""
    if model is None or X.empty:
        return {}, []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sv = shap.TreeExplainer(model).shap_values(X)
    if isinstance(sv, list):          # older shap: [class0, class1]
        sv = sv[1]
    sv = np.asarray(sv)
    if sv.ndim == 3:
        sv = sv[:, :, 1]
    out = {}
    cols = list(X.columns)
    for i, addr in enumerate(X.index):
        order = np.argsort(-np.abs(sv[i]))[:top_k]
        out[addr] = [{"feature": cols[j], "value": round(float(X.iat[i, j]), 4), "impact": round(float(sv[i, j]), 4)}
                     for j in order]
    imp = np.abs(sv).mean(0)
    glob = [{"feature": cols[j], "importance": round(float(imp[j]), 4)} for j in np.argsort(-imp)[:15]]
    return out, glob
