from typing import Dict, List, Any
from datetime import datetime
from collections import defaultdict
from beans.schema import CanonicalRecord

class FirstSpyEstimator:
    """
    First-Spy Estimator (Biryukov et al.):
    Identifies the earliest relaying IP peer for each transaction to estimate originator node.
    Computes confidence score based on the propagation time delta (Δt) between 1st and 2nd relayers.
    """

    @classmethod
    def estimate_originators(cls, records: List[CanonicalRecord]) -> Dict[str, Dict[str, Any]]:
        """
        Returns: { txid: { "first_spy_ip": str, "timestamp": datetime, "confidence": float, "relay_count": int } }
        """
        tx_relays = defaultdict(list)
        for r in records:
            tx_relays[r.txid].append(r)

        origin_map = {}
        for txid, relays in tx_relays.items():
            sorted_relays = sorted(relays, key=lambda x: x.timestamp)
            first_relay = sorted_relays[0]
            
            # Confidence estimation based on propagation lead time
            confidence = 0.65 # Base single-observation confidence
            if len(sorted_relays) > 1:
                delta_sec = (sorted_relays[1].timestamp - first_relay.timestamp).total_seconds()
                if delta_sec > 2.0:
                    confidence = 0.90 # High lead time indicates clear first relayer
                elif delta_sec > 0.5:
                    confidence = 0.78

            origin_map[txid] = {
                "first_spy_ip": first_relay.src_ip,
                "first_seen_timestamp": first_relay.timestamp,
                "confidence": confidence,
                "relay_count": len(sorted_relays),
                "asn": first_relay.asn,
                "asn_type": first_relay.asn_type,
                "geo_country": first_relay.geo_country
            }

        return origin_map
