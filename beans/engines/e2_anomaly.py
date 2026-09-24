import numpy as np
from typing import List, Dict, Tuple
from sklearn.ensemble import IsolationForest
from beans.schema import CanonicalRecord
from beans.features.extractors import FeatureExtractor

class AnomalyDetectionEngine:
    """
    Engine 2: Unsupervised Anomaly Detection using Isolation Forest (R5, E2).
    Generates normalized anomaly scores S_anomaly in [0, 1].
    """

    def __init__(self, contamination: float = 0.05):
        self.model = IsolationForest(
            n_estimators=100,
            contamination=contamination,
            random_state=42
        )
        self.is_fitted = False
        self.feature_names = []

    def fit_predict(self, records: List[CanonicalRecord]) -> Dict[str, float]:
        """Returns { txid: anomaly_score_0_to_1 }"""
        if not records:
            return {}

        feature_dicts = [FeatureExtractor.extract_tx_features(r) for r in records]
        self.feature_names = list(feature_dicts[0].keys())
        X = np.array([[fd[k] for k in self.feature_names] for fd in feature_dicts])

        self.model.fit(X)
        self.is_fitted = True

        # raw score: lower means more anomalous. Invert & percentile-normalize
        raw_scores = self.model.score_samples(X)
        min_s, max_s = raw_scores.min(), raw_scores.max()
        
        # Invert: highest anomaly score = most anomalous
        if max_s > min_s:
            norm_scores = 1.0 - (raw_scores - min_s) / (max_s - min_s)
        else:
            norm_scores = np.zeros_like(raw_scores)

        results = {}
        for r, score in zip(records, norm_scores):
            results[r.txid] = round(float(score), 4)

        return results
