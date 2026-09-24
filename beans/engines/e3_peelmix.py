import numpy as np
from typing import List, Dict, Tuple, Any
from sklearn.ensemble import RandomForestClassifier
from beans.schema import CanonicalRecord
from beans.features.extractors import FeatureExtractor

TYPOLOGY_CLASSES = ["NORMAL", "PEEL_CHAIN", "COINJOIN", "RANSOMWARE", "EXCHANGE_SWEEP"]

class PeelingAndMixingClassifier:
    """
    Engine 3: Peeling-Chain & Mixing Typology Classifier (R5, E3).
    Evaluates sequence, shape, output entropy, and denomination symmetries.
    """

    def __init__(self):
        self.clf = RandomForestClassifier(n_estimators=100, random_state=42, class_weight="balanced")
        self.is_trained = False
        self.classes_ = TYPOLOGY_CLASSES

    def train_on_labels(self, records: List[CanonicalRecord], labels_map: Dict[str, str]):
        X_list = []
        y_list = []
        for r in records:
            typology = labels_map.get(r.txid, "NORMAL")
            feat_dict = FeatureExtractor.extract_tx_features(r)
            X_list.append(list(feat_dict.values()))
            y_list.append(typology)

        if X_list and len(set(y_list)) > 1:
            X = np.array(X_list)
            y = np.array(y_list)
            self.clf.fit(X, y)
            self.classes_ = list(self.clf.classes_)
            self.is_trained = True

    def predict_probabilities(self, records: List[CanonicalRecord]) -> Dict[str, Dict[str, float]]:
        """
        Returns { txid: { "typology": predicted_class, "confidence": float, "probs": dict } }
        """
        results = {}
        if not records:
            return {}

        feature_dicts = [FeatureExtractor.extract_tx_features(r) for r in records]
        X = np.array([list(fd.values()) for fd in feature_dicts])

        if self.is_trained:
            probs = self.clf.predict_proba(X)
            for r, p_row in zip(records, probs):
                prob_dict = {cls_name: round(float(p), 4) for cls_name, p in zip(self.classes_, p_row)}
                top_class = self.classes_[int(np.argmax(p_row))]
                results[r.txid] = {
                    "predicted_typology": top_class,
                    "confidence": prob_dict[top_class],
                    "probabilities": prob_dict
                }
        else:
            # High-fidelity baseline structural heuristics when model not yet fitted
            for r, fd in zip(records, feature_dicts):
                prob_dict = {c: 0.05 for c in TYPOLOGY_CLASSES}
                top_class = "NORMAL"
                conf = 0.50

                # CoinJoin check
                if fd["max_equal_outputs"] >= 4 and fd["n_in"] >= 3:
                    top_class = "COINJOIN"
                    conf = 0.92
                # Peel chain check
                elif fd["n_in"] == 1 and fd["n_out"] == 2 and fd["max_min_ratio"] > 4.0 and (fd["is_vpn_tor"] or fd["is_bulletproof"]):
                    top_class = "PEEL_CHAIN"
                    conf = 0.88
                # Ransomware fan-out check
                elif fd["fan_out_ratio"] >= 5.0 and fd["is_bulletproof"]:
                    top_class = "RANSOMWARE"
                    conf = 0.94
                # Exchange sweep check
                elif fd["n_in"] >= 10 and fd["n_out"] <= 2:
                    top_class = "EXCHANGE_SWEEP"
                    conf = 0.95

                prob_dict[top_class] = conf
                results[r.txid] = {
                    "predicted_typology": top_class,
                    "confidence": conf,
                    "probabilities": prob_dict
                }

        return results
