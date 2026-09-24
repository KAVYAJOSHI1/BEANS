"""Plain-English reasons generated from a wallet's strongest positive SHAP contributions."""

TEMPLATES = {
    "max_peel_chain_len": lambda v: f"Part of a {v:.0f}-hop peeling chain (small amounts shaved off at each hop)",
    "cluster_max_p_peel": lambda v: f"Its cluster contains peel-chain transactions (model probability {v:.0%})",
    "max_p_peel": lambda v: f"Takes part in a peel-shaped transaction (model probability {v:.0%})",
    "max_p_coinjoin": lambda v: f"Takes part in a CoinJoin-like mixing transaction (probability {v:.0%})",
    "max_equal_output_share": lambda v: f"{v:.0%} of a transaction's outputs have identical value (mixing signature)",
    "max_p_fan_out": lambda v: f"Takes part in a rapid fan-out split (probability {v:.0%})",
    "max_p_fan_in": lambda v: f"Takes part in a consolidation (many inputs → one output, probability {v:.0%})",
    "max_p_round_trip": lambda v: f"Funds move in a circle back to the sender (probability {v:.0%})",
    "max_returns_to_input": lambda v: "Funds return to an address they came from within 3 hops (round trip)",
    "taint": lambda v: f"{v:.0%} of incoming value traces back to a known illicit seed wallet",
    "ppr": lambda v: f"High proximity to seed wallets in the money-flow graph (PPR {v:.2f})",
    "ppr_reverse": lambda v: f"Sends money towards known illicit seed wallets (reverse PPR {v:.2f})",
    "hops_from_seed": lambda v: f"Receives funds {v:.0f} hop(s) downstream of a known illicit seed wallet",
    "hops_to_seed": lambda v: f"Funds reach a known illicit seed wallet within {v:.0f} hop(s)",
    "anomaly": lambda v: f"Behaviour is more unusual than {v:.0%} of wallets (Isolation Forest)",
    "share_risky_asn": lambda v: f"{v:.0%} of its transactions were first relayed from Tor / VPN / bulletproof hosting",
    "share_datacenter": lambda v: f"{v:.0%} of its transactions were first relayed from datacenter IPs",
    "n_spend_countries": lambda v: f"Its spends were broadcast from {v:.0f} different countries",
    "max_geo_velocity_kmh": lambda v: f"Consecutive broadcasts imply {v:,.0f} km/h travel (impossible for one person)",
    "n_spend_ips": lambda v: f"Its spends were broadcast from {v:.0f} different IP addresses",
    "hold_h": lambda v: f"Funds held only {v:.1f} h before being moved on" if v >= 0 else "Funds never moved on",
    "min_respend_min": lambda v: f"Received funds were spent again within {v:.0f} minutes",
    "spend_max_n_out": lambda v: f"Spent in a transaction with {v:.0f} outputs",
    "fund_max_n_in": lambda v: f"Funded by a transaction with {v:.0f} inputs",
    "log_cluster_size": lambda v: f"Belongs to a multi-address entity cluster (~{max(1, round(2.718 ** v - 1))} addresses)",
    "cluster_share_risky": lambda v: f"{v:.0%} of its cluster's spends come from Tor / VPN / bulletproof relays",
    "max_dust_outputs": lambda v: f"Involved in a transaction with {v:.0f} dust outputs (dusting)",
    "lifetime_h": lambda v: f"Active for only {v:.1f} h",
}


def reasons_from_shap(contribs: list, typology: str, p: float, max_n: int = 4) -> list[str]:
    out = []
    if typology and typology not in ("UNKNOWN", "NORMAL"):
        out.append(f"Behaviour most similar to {typology.replace('_', ' ').lower()} wallets "
                   f"(fused probability of illicit activity {p:.0%})")
    for c in contribs:
        if c["impact"] <= 0 or len(out) >= max_n + 1:
            continue
        fn = TEMPLATES.get(c["feature"])
        if fn:
            try:
                text = fn(c["value"])
                if text:
                    out.append(text)
            except (TypeError, ValueError):
                pass
    return out or [f"Fused probability of illicit activity {p:.0%}"]
