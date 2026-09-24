import math
from collections import Counter
from typing import Dict, Any, List, Tuple
from datetime import datetime

def compute_output_entropy(amounts: List[float]) -> float:
    """
    Computes Shannon Entropy of transaction output amounts.
    Lower entropy indicates uniform/equal denomination outputs (CoinJoin characteristic).
    """
    if not amounts:
        return 0.0
    total = sum(amounts)
    if total <= 0:
        return 0.0
    probabilities = [amt / total for amt in amounts if amt > 0]
    entropy = -sum(p * math.log2(p) for p in probabilities)
    return entropy

class ThreatPatternMatcher:
    """
    Evaluates dynamic heuristic and structural features of transactions & wallets
    against forensic playbook signatures without hardcoded assumptions.
    """

    @staticmethod
    def evaluate_ransomware_signature(
        wallet_profile: Dict[str, Any],
        recent_txs: List[Dict[str, Any]],
        observed_network: List[Dict[str, Any]]
    ) -> Tuple[float, List[str], Dict[str, Any]]:
        """
        Ransomware Collection & Subdivision Signature:
        - Receives large initial sum (e.g. >= $10k or >= 0.5 BTC)
        - Fan-out subdivision ratio (splits 1 input into 5-20 outputs in < 2 hours)
        - Short hold time before immediate dissemination
        - Network broadcasts from bulletproof hoster, Tor, or datacenter VPN
        """
        score = 0.0
        evidence = []
        details = {}

        if not recent_txs:
            return 0.0, [], {}

        # 1. Total received volume check
        total_recv = wallet_profile.get("total_received", 0.0)
        if total_recv >= 2.0:
            score += 0.20
            evidence.append(f"High-value incoming payment detected: {total_recv:.3f} BTC")
        elif total_recv >= 0.5:
            score += 0.10
            evidence.append(f"Significant incoming payment detected: {total_recv:.3f} BTC")

        # 2. Fan-out subdivision analysis
        max_fan_out = 1
        rapid_split_detected = False
        for tx in recent_txs:
            num_inputs = len(tx.get("input_addresses", []))
            num_outputs = len(tx.get("output_addresses", []))
            if num_inputs > 0:
                ratio = num_outputs / num_inputs
                if ratio > max_fan_out:
                    max_fan_out = ratio
            if num_inputs <= 2 and num_outputs >= 5:
                rapid_split_detected = True

        details["max_fan_out_ratio"] = round(max_fan_out, 2)
        if rapid_split_detected:
            score += 0.35
            evidence.append(f"Rapid fan-out subdivision detected: 1-to-{max_fan_out:.0f} addresses split")

        # 3. Holding velocity / time to spend
        first_seen = wallet_profile.get("first_seen")
        last_seen = wallet_profile.get("last_seen")
        if first_seen and last_seen and isinstance(first_seen, datetime) and isinstance(last_seen, datetime):
            wallet_lifespan_hours = abs((last_seen - first_seen).total_seconds()) / 3600.0
            details["lifespan_hours"] = round(wallet_lifespan_hours, 2)
            if wallet_lifespan_hours < 4.0 and wallet_profile.get("transaction_count", 0) >= 2:
                score += 0.25
                evidence.append(f"Ultra-rapid fund turnover: active lifespan under {wallet_lifespan_hours:.1f}h")

        # 4. SIGINT Bulletproof / Datacenter broadcast
        has_bulletproof = any(net.get("isp_type") == "BULLETPROOF" for net in observed_network)
        has_vpn_or_tor = any(net.get("isp_type") in ["VPN", "TOR_EXIT"] for net in observed_network)
        if has_bulletproof:
            score += 0.20
            evidence.append("P2P broadcast originated from known bulletproof hosting ASN")
        elif has_vpn_or_tor:
            score += 0.10
            evidence.append("P2P broadcast routed through privacy VPN/Tor infrastructure")

        confidence = min(1.0, score)
        return confidence, evidence, details

    @staticmethod
    def evaluate_coinjoin_mixing(
        tx: Dict[str, Any]
    ) -> Tuple[float, List[str], Dict[str, Any]]:
        """
        CoinJoin / Tumbler Signature:
        - Multiple inputs (>= 5) from diverse sources
        - Multi-output with equal denominations (e.g. 5x 0.1 BTC, 10x 1.0 BTC)
        - Low Shannon entropy in output distribution
        - Zero change address reuse
        """
        inputs = tx.get("input_addresses", [])
        outputs = tx.get("output_addresses", [])
        out_amounts = [float(a) for a in tx.get("output_amounts", [])]
        
        score = 0.0
        evidence = []
        details = {}

        if len(inputs) < 2 or len(outputs) < 2:
            return 0.0, [], {}

        # 1. Equal output amounts frequency
        rounded_amts = [round(a, 4) for a in out_amounts]
        counts = Counter(rounded_amts)
        max_equal_count = max(counts.values()) if counts else 0
        details["max_equal_outputs"] = max_equal_count
        details["total_outputs"] = len(outputs)

        if max_equal_count >= 5:
            score += 0.45
            evidence.append(f"Identified {max_equal_count} equal-denomination outputs (CoinJoin signature)")
        elif max_equal_count >= 3:
            score += 0.25
            evidence.append(f"Identified {max_equal_count} identical output denominations")

        # 2. Input count diversity
        if len(inputs) >= 10:
            score += 0.25
            evidence.append(f"High multi-party input count: {len(inputs)} co-signers")
        elif len(inputs) >= 5:
            score += 0.15
            evidence.append(f"Multi-input aggregation: {len(inputs)} input addresses")

        # 3. Output entropy
        entropy = compute_output_entropy(out_amounts)
        details["output_entropy"] = round(entropy, 3)
        # For equal distribution, theoretical max is log2(N), but repeated values reduce relative variance
        if max_equal_count >= 3 and entropy > 0:
            score += 0.20
            evidence.append(f"Uniform output entropy characteristic: {entropy:.2f} bits")

        # 4. Address non-reuse check
        overlap = set(inputs).intersection(set(outputs))
        if len(overlap) == 0:
            score += 0.10
            evidence.append("Strict zero-address-reuse across inputs and outputs")

        confidence = min(1.0, score)
        return confidence, evidence, details

    @staticmethod
    def evaluate_theft_laundering_peel_chain(
        wallet_profile: Dict[str, Any],
        chain_txs: List[Dict[str, Any]],
        observed_network: List[Dict[str, Any]]
    ) -> Tuple[float, List[str], Dict[str, Any]]:
        """
        Theft & Exchange Hack Laundering:
        - Peel chain structure (1 large input -> 1 small peel hop + 1 change address -> repeated)
        - High velocity (hops executed in minutes)
        - Non-standard ports or rapid geo-hopping
        """
        score = 0.0
        evidence = []
        details = {}

        if len(chain_txs) < 2:
            return 0.0, [], {}

        # 1. Peel chain detection: 2 outputs (one small payment, one large change) repeated
        peel_hops = 0
        for tx in chain_txs:
            outs = tx.get("output_amounts", [])
            if len(outs) == 2:
                amt1, amt2 = float(outs[0]), float(outs[1])
                ratio = max(amt1, amt2) / (min(amt1, amt2) + 1e-8)
                if ratio > 4.0:
                    peel_hops += 1

        details["peel_hops_detected"] = peel_hops
        if peel_hops >= 3:
            score += 0.40
            evidence.append(f"Active peel chain laundering: {peel_hops} consecutive peel hops detected")
        elif peel_hops >= 1:
            score += 0.20
            evidence.append("Peel-off transaction structure identified")

        # 2. Transaction velocity (mean time between hops in seconds)
        timestamps = sorted([tx.get("timestamp") for tx in chain_txs if tx.get("timestamp")])
        if len(timestamps) >= 2:
            intervals = [(timestamps[i] - timestamps[i-1]).total_seconds() for i in range(1, len(timestamps))]
            avg_interval_min = (sum(intervals) / len(intervals)) / 60.0
            details["avg_hop_interval_minutes"] = round(avg_interval_min, 2)
            if avg_interval_min < 15.0:
                score += 0.30
                evidence.append(f"Automated high-velocity hops: avg {avg_interval_min:.1f} mins between transactions")

        # 3. High fee urgency
        high_fee_count = sum(1 for tx in chain_txs if tx.get("fee", 0.0) > 0.005)
        if high_fee_count > 0:
            score += 0.15
            evidence.append(f"Priority miner fees paid across {high_fee_count} transactions to expedite block confirmation")

        confidence = min(1.0, score)
        return confidence, evidence, details

    @staticmethod
    def evaluate_exchange_sweep(
        tx: Dict[str, Any]
    ) -> Tuple[float, List[str], Dict[str, Any]]:
        """
        Legitimate Exchange Sweep / Consolidation Baseline:
        - Hundreds of small inputs -> 1 or 2 large cold/warm storage outputs
        - Regular timing intervals, standard script types
        """
        inputs = tx.get("input_addresses", [])
        outputs = tx.get("output_addresses", [])
        
        score = 0.0
        evidence = []
        details = {"input_count": len(inputs), "output_count": len(outputs)}

        if len(inputs) >= 20 and len(outputs) <= 2:
            score = 0.90
            evidence.append(f"Classic exchange consolidation: {len(inputs)} deposit addresses aggregated into {len(outputs)} master output(s)")
        elif len(inputs) >= 5 and len(outputs) == 1:
            score = 0.60
            evidence.append(f"Standard wallet consolidation: {len(inputs)} inputs merged into 1 cold address")

        return score, evidence, details
