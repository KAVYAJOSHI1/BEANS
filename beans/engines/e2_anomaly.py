"""E2: unsupervised anomaly detection (Isolation Forest) on wallet behaviour + network features."""
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


def anomaly(W: pd.DataFrame, cols: list[str]) -> pd.Series:
    X = W[cols].replace([np.inf, -np.inf], 0).fillna(0).values
    iso = IsolationForest(n_estimators=200, contamination="auto", random_state=42).fit(X)
    raw = -iso.score_samples(X)                     # higher = more anomalous
    return pd.Series(pd.Series(raw).rank(pct=True).values, index=W.index, name="anomaly")
