from typing import Dict, Any, List, Tuple
from beans.config import settings

class MetaFusionEngine:
    """
    Fuses outputs from all 4 ML Engines + Network First-Spy Telemetry:
    - E1: Cluster Risk Max/Mean
    - E2: Anomaly Score (Isolation Forest)
    - E3: Typology Probabilities (LightGBM/RF)
    - E4: PPR Proximity & Decayed Taint
    - Network: Bulletproof ASN, Impossible Travel, First-Spy Lead Time
    """

    @classmethod
    def fuse_entity_score(
        cls,
        address: str,
        cluster_id: str,
        e2_anomaly: float,
        e3_typology: str,
        e3_conf: float,
        e4_ppr: float,
        e4_taint: float,
        network_meta: Dict[str, Any]
    ) -> Tuple[float, float, str, Dict[str, float]]:
        """
        Returns: (risk_score_0_to_100, calibrated_confidence, severity, score_components)
        """
        # Engine contributions
        e2_contrib = e2_anomaly * 25.0
        
        # Typology multiplier
        typology_weight = 0.0
        if e3_typology == "RANSOMWARE":
            typology_weight = 35.0 * e3_conf
        elif e3_typology == "PEEL_CHAIN":
            typology_weight = 30.0 * e3_conf
        elif e3_typology == "COINJOIN":
            typology_weight = 20.0 * e3_conf
        elif e3_typology == "EXCHANGE_SWEEP":
            typology_weight = 0.0 # Legitimate baseline

        # Seed proximity & taint
        e4_contrib = (e4_ppr * 15.0) + (e4_taint * 15.0)

        # Network indicators
        net_contrib = 0.0
        if network_meta.get("asn_type") == "BULLETPROOF":
            net_contrib += 10.0
        if network_meta.get("has_impossible_travel", False):
            net_contrib += 10.0
        if network_meta.get("asn_type") in ["VPN", "TOR_EXIT"]:
            net_contrib += 5.0

        raw_score = e2_contrib + typology_weight + e4_contrib + net_contrib
        
        # Dampen if legitimate exchange sweep
        if e3_typology == "EXCHANGE_SWEEP":
            raw_score = min(raw_score * 0.15, 12.0)

        risk_score = round(min(100.0, max(0.0, raw_score)), 1)

        # Calibrated Confidence calculation (model agreement + data completeness)
        engines_active = sum([
            1 if e2_anomaly > 0.4 else 0,
            1 if e3_conf > 0.6 and e3_typology != "NORMAL" else 0,
            1 if e4_taint > 0.1 or e4_ppr > 0.2 else 0,
            1 if net_contrib > 0 else 0
        ])
        base_conf = 0.60 + (engines_active * 0.09)
        calibrated_conf = round(min(0.98, max(0.50, base_conf)), 2)

        # Severity classification
        if risk_score >= settings.RISK_CRITICAL_MIN:
            severity = "CRITICAL"
        elif risk_score >= settings.RISK_HIGH_MIN:
            severity = "HIGH"
        elif risk_score >= settings.RISK_MEDIUM_MIN:
            severity = "MEDIUM"
        else:
            severity = "LOW"

        components = {
            "e2_anomaly_score": round(e2_contrib, 1),
            "e3_typology_score": round(typology_weight, 1),
            "e4_seed_proximity_score": round(e4_contrib, 1),
            "network_sigint_score": round(net_contrib, 1),
            "total_risk_score": risk_score
        }

        return risk_score, calibrated_conf, severity, components
