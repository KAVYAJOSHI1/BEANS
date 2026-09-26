"""Counterfactual explanations: what would have to be different for the wallet not to be flagged.

For each alert, every factor that pushed its risk up (from SHAP) is set to what a typical wallet looks like (the median
of all wallets, no labels involved) and the wallet is re-scored with the real fusion model. A factor is a *group* of
related columns (e.g. every Tor/VPN column: wallet, cluster and GNN neighbourhood versions), because the model sees one
signal through several correlated features and changing only one of them would understate its effect.

Output per alert: the effect of each factor alone, and the smallest set of factors (greedy) that takes the risk below the
HIGH threshold. Scores are the persisted ensemble's, so "before" can differ slightly from the out-of-fold risk shown.
"""
from typing import Callable, Dict, List

import numpy as np
import pandas as pd

from beans.config import settings

FACTORS: List[tuple] = [
    ("Tor / VPN / bulletproof relaying", ("risky", "spy_tor", "share_datacenter")),
    ("proximity to known illicit seed wallets", ("taint", "ppr", "hops_", "seed")),
    ("peel-chain behaviour", ("peel",)),
    ("CoinJoin / mixing", ("coinjoin", "equal_output")),
    ("fan-out splitting", ("fan_out", "spend_max_n_out", "below_round")),
    ("round-trip flows", ("round_trip", "returns_to_input")),
    ("unusual behaviour (anomaly score)", ("anomaly",)),
    ("multi-country / fast-moving broadcasts", ("countries", "velocity", "n_spend_ips")),
    ("large entity cluster", ("cluster_size", "log_size")),
    ("fast re-spending of received funds", ("respend", "hold_h", "spent_1h")),
]


def _factor_of(col: str):
    for name, keys in FACTORS:
        if any(k in col for k in keys):
            return name
    return None


def compute(alerts: List[dict], X: pd.DataFrame, shap_map: Dict[str, list], predict: Callable[[pd.DataFrame], pd.Series],
            max_factors: int = 4) -> None:
    """Adds alert["evidence"]["counterfactual"] in place."""
    if not alerts:
        return
    typical = X.median()
    groups: Dict[str, list] = {}
    for c in X.columns:
        f = _factor_of(c)
        if f:
            groups.setdefault(f, []).append(c)
    target = settings.RISK_HIGH_MIN / 100

    plans = []   # (alert, factors ranked by their total positive SHAP impact)
    rows, keys = [], []
    for a in alerts:
        addr = a["entity_id"]
        if addr not in X.index:
            continue
        weight: Dict[str, float] = {}
        for s in shap_map.get(addr, []):
            f = _factor_of(s["feature"])
            if f and s["impact"] > 0:
                weight[f] = weight.get(f, 0.0) + s["impact"]
        factors = [f for f, _ in sorted(weight.items(), key=lambda kv: -kv[1])][:max_factors]
        if not factors:
            continue
        plans.append((a, factors))
        base = X.loc[addr]
        rows.append(base)
        keys.append((addr, None))
        for f in factors:
            r = base.copy()
            r[groups[f]] = typical[groups[f]]
            rows.append(r)
            keys.append((addr, (f,)))
        for k in range(2, len(factors) + 1):                  # greedy prefixes: top-1, top-2, ... together
            r = base.copy()
            for f in factors[:k]:
                r[groups[f]] = typical[groups[f]]
            rows.append(r)
            keys.append((addr, tuple(factors[:k])))
    if not rows:
        return
    p = predict(pd.DataFrame(rows, columns=X.columns).reset_index(drop=True)).values
    score = {k: float(v) for k, v in zip(keys, p)}
    for a, factors in plans:
        addr = a["entity_id"]
        before = score[(addr, None)]
        single = [{"factor": f, "risk_after": round(100 * score[(addr, (f,))], 1)} for f in factors]
        minimal = None
        for k in range(1, len(factors) + 1):
            key = (addr, tuple(factors[:k])) if k > 1 else (addr, (factors[0],))
            if score[key] < target:
                minimal = {"factors": list(factors[:k]), "risk_after": round(100 * score[key], 1)}
                break
        a["evidence"]["counterfactual"] = {
            "risk_before": round(100 * before, 1), "typical_means": "median of all wallets in this dataset",
            "single_factor": single, "threshold": settings.RISK_HIGH_MIN,
            "minimal_change": minimal,
            "summary": _summary(before, single, minimal),
        }


def _summary(before: float, single: list, minimal) -> str:
    if minimal and len(minimal["factors"]) == 1:
        return (f"Without {minimal['factors'][0]}, the risk would fall from {100 * before:.0f} to "
                f"{minimal['risk_after']:.0f}: this factor alone decides the alert.")
    if minimal:
        return (f"The risk only falls below the alert threshold (from {100 * before:.0f} to {minimal['risk_after']:.0f}) "
                f"when {', '.join(minimal['factors'][:-1])} and {minimal['factors'][-1]} are "
                f"{'both' if len(minimal['factors']) == 2 else 'all'} removed: the evidence is "
                f"corroborated, not a single signal.")
    best = min(single, key=lambda s: s["risk_after"])
    return (f"No single change clears the wallet: even the strongest factor ({best['factor']}) only brings the risk from "
            f"{100 * before:.0f} to {best['risk_after']:.0f}. Several independent signals agree.")
