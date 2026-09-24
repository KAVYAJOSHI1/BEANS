import math
from collections import Counter
from datetime import datetime
from typing import Dict, List, Any
import numpy as np
from beans.schema import CanonicalRecord

def compute_entropy(amts: List[float]) -> float:
    if not amts or sum(amts) <= 0:
        return 0.0
    tot = sum(amts)
    probs = [a / tot for a in amts if a > 0]
    return -sum(p * math.log2(p) for p in probs)

class FeatureExtractor:
    """
    Extracts tabular feature vectors for transactions, wallets, and network telemetry.
    """

    @classmethod
    def extract_tx_features(cls, record: CanonicalRecord) -> Dict[str, float]:
        n_in = len(record.input_addresses)
        n_out = len(record.output_addresses)
        tot_out = record.total_output
        tot_in = record.total_input
        fee = record.fee

        # Equal denomination outputs count
        rounded = [round(a, 4) for a in record.output_amounts]
        counts = Counter(rounded)
        max_equal = max(counts.values()) if counts else 0

        entropy = compute_entropy(record.output_amounts)
        min_out = min(record.output_amounts) if record.output_amounts else 1e-6
        max_out = max(record.output_amounts) if record.output_amounts else 1e-6
        max_min_ratio = max_out / (min_out + 1e-8)
        fan_out_ratio = n_out / (n_in + 1e-8)

        is_bulletproof = 1.0 if record.asn_type == "BULLETPROOF" else 0.0
        is_vpn_tor = 1.0 if record.asn_type in ["VPN", "TOR_EXIT"] else 0.0
        is_non_std_port = 1.0 if record.src_port != 8333 else 0.0

        return {
            "n_in": float(n_in),
            "n_out": float(n_out),
            "total_out_btc": float(tot_out),
            "log_total_out": float(math.log1p(tot_out)),
            "fee": float(fee),
            "fee_rate": float(fee / (tot_out + 1e-6)),
            "max_equal_outputs": float(max_equal),
            "output_entropy": float(entropy),
            "max_min_ratio": float(min(100.0, max_min_ratio)),
            "fan_out_ratio": float(min(50.0, fan_out_ratio)),
            "is_bulletproof": is_bulletproof,
            "is_vpn_tor": is_vpn_tor,
            "is_non_std_port": is_non_std_port
        }
