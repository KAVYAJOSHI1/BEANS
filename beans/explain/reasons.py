from typing import List, Dict, Any

class PlainEnglishReasonGenerator:
    """
    Generates human-readable, investigator-friendly rationale sentences for why an alert was triggered.
    """

    @classmethod
    def generate_reasons(
        cls,
        typology: str,
        typology_conf: float,
        taint_pct: float,
        path_to_seed: List[str],
        network_meta: Dict[str, Any],
        anomaly_score: float,
        fan_out_ratio: float = 1.0,
        peel_chain_length: int = 0
    ) -> List[str]:
        reasons = []

        # 1. Typology reason
        if typology == "RANSOMWARE":
            reasons.append(f"Classified as Ransomware collection signature (model confidence {typology_conf * 100:.0f}%) with rapid fund fan-out")
        elif typology == "PEEL_CHAIN":
            reasons.append(f"Identified sequential automated peeling chain ({peel_chain_length} consecutive peel hops)")
        elif typology == "COINJOIN":
            reasons.append(f"Participated in privacy CoinJoin mixing pool with equal-denomination output distribution")

        # 2. Seed Proximity & Taint
        if taint_pct > 0.05:
            seed_addr = path_to_seed[0] if path_to_seed else "Known Seed"
            hops = len(path_to_seed) - 1 if path_to_seed else 1
            reasons.append(f"{hops} hop(s) from illicit seed wallet {seed_addr[:6]}...{seed_addr[-4:]} with {taint_pct * 100:.1f}% decayed taint exposure")

        # 3. Network & Geo SIGINT
        if network_meta.get("asn_type") == "BULLETPROOF":
            reasons.append(f"P2P transaction relayed from known bulletproof hosting ASN ({network_meta.get('asn', 'AS9009')})")
        elif network_meta.get("asn_type") in ["VPN", "TOR_EXIT"]:
            reasons.append(f"Relayed through anonymized privacy infrastructure ({network_meta.get('asn_type')}) in {network_meta.get('geo_country', 'XX')}")

        if network_meta.get("has_impossible_travel", False):
            speed = network_meta.get("travel_speed_kmh", 0)
            reasons.append(f"Impossible travel geo-velocity detected across consecutive broadcasts ({speed:.0f} km/h)")

        # 4. Outlier Anomaly
        if anomaly_score >= 0.75:
            reasons.append(f"Behavioral anomaly index in the {anomaly_score * 100:.0f}th percentile compared to normal network traffic")

        if not reasons:
            reasons.append("Elevated risk profile correlated from multi-hop counterparties")

        return reasons
