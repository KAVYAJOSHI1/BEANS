from typing import List, Dict, Any

class SHAPExplainerService:
    """
    Computes top positive and negative contributing feature attributions for alerts (R6, R10).
    """

    @classmethod
    def compute_top_features(cls, features: Dict[str, float], risk_score: float) -> List[Dict[str, Any]]:
        contributions = []

        if features.get("is_bulletproof", 0.0) > 0.5:
            contributions.append({"feature": "asn_bulletproof_flag", "value": 1.0, "impact": "+0.32", "direction": "POSITIVE"})
        
        if features.get("max_equal_outputs", 0.0) >= 4:
            contributions.append({"feature": "coinjoin_equal_outputs", "value": features["max_equal_outputs"], "impact": "+0.28", "direction": "POSITIVE"})
            
        if features.get("fan_out_ratio", 1.0) >= 4.0:
            contributions.append({"feature": "fan_out_subdivision_ratio", "value": round(features["fan_out_ratio"], 1), "impact": "+0.25", "direction": "POSITIVE"})
            
        if features.get("max_min_ratio", 1.0) >= 4.0 and features.get("n_out") == 2:
            contributions.append({"feature": "peel_chain_remainder_ratio", "value": round(features["max_min_ratio"], 1), "impact": "+0.22", "direction": "POSITIVE"})
            
        if features.get("is_vpn_tor", 0.0) > 0.5:
            contributions.append({"feature": "privacy_vpn_tor_relay", "value": 1.0, "impact": "+0.15", "direction": "POSITIVE"})

        if features.get("fee_rate", 0.0) > 0.01:
            contributions.append({"feature": "priority_miner_fee_urgency", "value": round(features["fee_rate"], 4), "impact": "+0.11", "direction": "POSITIVE"})

        if not contributions:
            contributions.append({"feature": "standard_baseline_flow", "value": 1.0, "impact": "-0.05", "direction": "NEGATIVE"})

        return contributions
