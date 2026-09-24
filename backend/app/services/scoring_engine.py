from typing import Dict, Any, List, Tuple
from backend.app.core.config import settings

class CompositeScoringEngine:
    """
    Computes dynamic risk score (0-100) based on weighted multi-factor forensic telemetry.
    No hardcoded scores: all calculations are derived from mathematical features and configurable weights.
    """

    @classmethod
    def calculate_score(
        cls,
        pattern_confidence: float,
        osint_hits: List[Dict[str, Any]],
        sigint_features: Dict[str, Any],
        temporal_features: Dict[str, Any],
        weights: Dict[str, float] = None
    ) -> Tuple[float, str, Dict[str, float], List[str]]:
        """
        Calculates composite risk score and returns:
        (total_score, severity, component_breakdown, explanation_bullets)
        """
        w = weights or {
            "pattern": settings.WEIGHT_PATTERN,
            "osint": settings.WEIGHT_OSINT,
            "sigint": settings.WEIGHT_SIGINT_GEO,
            "temporal": settings.WEIGHT_TEMPORAL_VELOCITY
        }

        # 1. Pattern Score (0 to w["pattern"])
        pattern_contrib = pattern_confidence * w.get("pattern", 40.0)

        # 2. OSINT Score (0 to w["osint"])
        osint_score_norm = 0.0
        osint_bullets = []
        if osint_hits:
            # Weighted average of OSINT hit confidences, scaled by number of corroborated feeds
            total_osint_conf = sum(h.get("confidence", 0.9) for h in osint_hits)
            feed_multiplier = min(1.0, 0.6 + (len(osint_hits) * 0.2)) # More feeds = higher confidence
            osint_score_norm = min(1.0, (total_osint_conf / max(1, len(osint_hits))) * feed_multiplier)
            for h in osint_hits:
                osint_bullets.append(f"OSINT Match: {h.get('source')} ({h.get('threat_type')}) - Incident: {h.get('incident_name')}")
        
        osint_contrib = osint_score_norm * w.get("osint", 30.0)

        # 3. SIGINT / Network Geo Score (0 to w["sigint"])
        sigint_score_norm = 0.0
        sigint_bullets = []
        
        if sigint_features.get("has_bulletproof", False):
            sigint_score_norm += 0.55
            sigint_bullets.append(f"SIGINT: Broadcast through bulletproof hosting ASN ({sigint_features.get('src_asn', 'Unknown')})")
        
        if sigint_features.get("has_impossible_travel", False):
            sigint_score_norm += 0.35
            sigint_bullets.append(f"SIGINT: Impossible travel velocity detected ({sigint_features.get('travel_speed_kmh', 0)} km/h)")
            
        if sigint_features.get("is_non_standard_port", False):
            sigint_score_norm += 0.15
            sigint_bullets.append(f"SIGINT: Non-standard P2P broadcast port {sigint_features.get('src_port')}")
            
        if sigint_features.get("is_tor_or_vpn", False) and not sigint_features.get("has_bulletproof", False):
            sigint_score_norm += 0.25
            sigint_bullets.append(f"SIGINT: Privacy network route ({sigint_features.get('isp_type', 'VPN')})")

        sigint_score_norm = min(1.0, sigint_score_norm)
        sigint_contrib = sigint_score_norm * w.get("sigint", 20.0)

        # 4. Temporal Velocity Score (0 to w["temporal"])
        temporal_score_norm = 0.0
        temporal_bullets = []
        
        velocity_minutes = temporal_features.get("avg_hop_interval_minutes")
        lifespan_hours = temporal_features.get("lifespan_hours")
        
        if velocity_minutes is not None and velocity_minutes < 10.0:
            temporal_score_norm += 0.60
            temporal_bullets.append(f"Temporal: Ultra-fast transaction cycle ({velocity_minutes:.1f} mins/hop)")
            
        if lifespan_hours is not None and lifespan_hours < 2.0:
            temporal_score_norm += 0.40
            temporal_bullets.append(f"Temporal: Immediate wallet dissipation (lifespan < {lifespan_hours:.1f}h)")

        temporal_score_norm = min(1.0, temporal_score_norm)
        temporal_contrib = temporal_score_norm * w.get("temporal", 10.0)

        # Total Raw Score
        raw_total = pattern_contrib + osint_contrib + sigint_contrib + temporal_contrib
        total_score = round(min(100.0, max(0.0, raw_total)), 1)

        # Severity categorization
        if total_score >= settings.RISK_CRITICAL_MIN:
            severity = "CRITICAL"
        elif total_score >= settings.RISK_HIGH_MIN:
            severity = "HIGH"
        elif total_score >= settings.RISK_MEDIUM_MIN:
            severity = "MEDIUM"
        else:
            severity = "LOW"

        breakdown = {
            "pattern_score": round(pattern_contrib, 1),
            "osint_score": round(osint_contrib, 1),
            "sigint_score": round(sigint_contrib, 1),
            "temporal_score": round(temporal_contrib, 1),
            "total_score": total_score
        }

        all_bullets = osint_bullets + sigint_bullets + temporal_bullets
        return total_score, severity, breakdown, all_bullets
