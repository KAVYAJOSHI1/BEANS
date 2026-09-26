"""Action directives: every alert gets one recommended next step, chosen by fixed, citable rules.

Why rules and not a model: each directive can lead to a legal request, so the reason has to be checkable
("deposit 18 min after receipt ≤ 30 min"), and the same data must always give the same directive. The
model's contribution is quoted next to the rule as SHAP support, but the rule decides.

Inputs are the scored wallet matrix, the transaction frames and the attribution list `known_entities`
(exchange / mining-pool addresses). Ground-truth tables are never read here.

Rules, in priority order (the first match is the directive; every match is listed). The numbers below are the
defaults; they live in beans/config.py (ACTION_*) and can be overridden from the environment / .env:
  R0 REVIEW_LIKELY_BENIGN   the flagged wallet itself is a known exchange / mining-pool address
  R1 IMMEDIATE_FREEZE_DRAFT funds traced (≤ 4 hops) to a known exchange ≤ 30 min after receipt or ≤ 30 min before
                            the latest data (money still likely on the exchange), risk ≥ 65
  R2 DRAFT_SECTION_94_BNSS  funds traced to an exchange that operates in India (any delay)
  R3 FIU_REFERRAL_PACK      ≥ 1 BTC moved (by the wallet's cluster), broadcast via Tor/VPN/bulletproof hosting, with a layering pattern
  R4 PASSIVE_TAINT_MONITOR  unspent balance, dormant ≥ 6 h, linked to a seed (taint or ≤ 4 hops)
  R5 REVIEW_LIKELY_BENIGN   funded by a known mining pool, no seed link, no risky infrastructure
  —  ANALYST_REVIEW         nothing above matched
"""
from bisect import bisect_right
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional

import pandas as pd

from beans.config import settings

FREEZE_WINDOW_MIN = settings.ACTION_FREEZE_WINDOW_MIN
FREEZE_MIN_RISK = settings.ACTION_FREEZE_MIN_RISK
MAX_HOPS = settings.ACTION_MAX_HOPS
LAYERING_MIN_BTC = settings.ACTION_LAYERING_MIN_BTC
DORMANT_H = settings.ACTION_DORMANT_H
SEED_LINK_HOPS = settings.ACTION_SEED_LINK_HOPS
MIN_PEEL_CHAIN = settings.ACTION_MIN_PEEL_CHAIN
NO_SEED_PATH = 20   # E4 writes hops = 20 (clipped) when no path to a seed exists

ACTIONS: Dict[str, Dict[str, str]] = {
    "IMMEDIATE_FREEZE_DRAFT": {
        "title": "Draft freeze / hold request to exchange",
        "rule": f"Funds traced (≤ {MAX_HOPS} hops) to a known exchange deposit made ≤ {FREEZE_WINDOW_MIN:.0f} min after "
                f"receipt or ≤ {FREEZE_WINDOW_MIN:.0f} min before the latest data, and risk ≥ {FREEZE_MIN_RISK:.0f}",
        "legal_basis": "Section 106 BNSS 2023 (seizure of property), request to the exchange to hold the credited funds",
        "priority": "1",
    },
    "DRAFT_SECTION_94_BNSS": {
        "title": "Draft Section 94 BNSS requisition (KYC + records)",
        "rule": f"Funds traced (≤ {MAX_HOPS} hops) to an exchange that operates in India / is registered with FIU-IND",
        "legal_basis": "Section 94 BNSS 2023 (summons to produce documents or other things)",
        "priority": "2",
    },
    "FIU_REFERRAL_PACK": {
        "title": "Prepare FIU-IND intelligence referral pack",
        "rule": f"≥ {LAYERING_MIN_BTC:g} BTC moved, broadcast via Tor / VPN / bulletproof hosting, with a layering "
                "pattern (peel chain, CoinJoin or fan-out)",
        "legal_basis": "PMLA 2002 intelligence sharing; the pack goes to the IO / FIU-IND liaison, not filed as an STR",
        "priority": "3",
    },
    "PASSIVE_TAINT_MONITOR": {
        "title": "Put on passive taint watch",
        "rule": f"Unspent balance, dormant ≥ {DORMANT_H:.0f} h, linked to a seed wallet (taint > 0 or ≤ {SEED_LINK_HOPS} hops)",
        "legal_basis": "No legal step yet. Watch the funds and re-alert when they move",
        "priority": "4",
    },
    "REVIEW_LIKELY_BENIGN": {
        "title": "Review as a likely false positive",
        "rule": "The wallet is a known exchange / mining-pool address, or is funded by a mining pool with no seed "
                "link and no risky infrastructure",
        "legal_basis": "None. Confirm or reject; the verdict feeds model retraining",
        "priority": "5",
    },
    "ANALYST_REVIEW": {
        "title": "Manual analyst review",
        "rule": "No directive rule matched. Read the reasons and evidence",
        "legal_basis": "None",
        "priority": "6",
    },
}


class _Flows:
    """Address → receipts / spends and txid → outputs, for forward tracing."""

    def __init__(self, f):
        self.recv_ts: Dict[str, list] = defaultdict(list)
        for a, ts in zip(f.tout["address"], f.tout["ts"]):
            self.recv_ts[a].append(ts)
        for v in self.recv_ts.values():
            v.sort()
        self.spends: Dict[str, list] = defaultdict(list)
        for a, t, ts in zip(f.tin["address"], f.tin["txid"], f.tin["ts"]):
            self.spends[a].append((ts, t))
        for v in self.spends.values():
            v.sort()
        self.outs: Dict[str, list] = defaultdict(list)
        for t, a, v in zip(f.tout["txid"], f.tout["address"], f.tout["amount"]):
            self.outs[t].append((a, float(v)))
        self.ins_of: Dict[str, set] = defaultdict(set)
        for t, a in zip(f.tin["txid"], f.tin["address"]):
            self.ins_of[t].add(a)
        self.recv_txids: Dict[str, list] = defaultdict(list)
        for t, a in zip(f.tout["txid"], f.tout["address"]):
            self.recv_txids[a].append(t)
        self.last_seen = pd.concat([f.tin[["address", "ts"]], f.tout[["address", "ts"]]]).groupby("address")["ts"].max()

    def trace_to_vasp(self, addr: str, known: Dict[str, dict]) -> List[dict]:
        """Every known-exchange deposit reachable from `addr` (≤ MAX_HOPS spends, forward in time)."""
        hits, seen = [], set()
        q = deque()
        for ts, txid in self.spends.get(addr, [])[:25]:
            recv = self.recv_ts.get(addr, [])
            i = bisect_right(recv, ts)
            q.append((txid, ts, 1, recv[i - 1] if i else None, [txid]))
        while q and len(seen) < 600:
            txid, ts, hop, start, path = q.popleft()
            if txid in seen:
                continue
            seen.add(txid)
            for o, amt in self.outs.get(txid, []):
                k = known.get(o)
                if k and k["entity_type"] == "VASP":
                    delay = None if start is None else (ts - start).total_seconds() / 60
                    hits.append({"vasp": k["entity_name"], "in_jurisdiction": bool(k["in_jurisdiction"]),
                                 "country": k["country"], "deposit_address": o, "txid": txid, "path": path,
                                 "hops": hop, "amount_btc": round(amt, 8), "deposit_ts": str(ts),
                                 "minutes_after_receipt": None if delay is None else round(delay, 1)})
                elif hop < MAX_HOPS and o not in known:
                    for ts2, t2 in self.spends.get(o, [])[:3]:
                        if ts2 >= ts:
                            q.append((t2, ts2, hop + 1, start, path + [t2]))
        return hits

    def funders(self, addr: str) -> set:
        return {a for t in self.recv_txids.get(addr, []) for a in self.ins_of.get(t, ())}


def _shap_support(alert: dict, n: int = 3) -> List[dict]:
    feats = [s for s in alert.get("shap_top_features") or [] if float(s.get("impact", 0) or 0) > 0]
    return [{"feature": s["feature"], "value": s.get("value"), "impact": s.get("impact")} for s in feats[:n]]


def _decide(alert: dict, w: pd.Series, flows: _Flows, known: Dict[str, dict], now) -> dict:
    addr, risk = alert["entity_id"], float(alert["risk_score"])
    matched: List[tuple] = []   # (action, facts)

    own = known.get(addr)
    if own:
        matched.append(("REVIEW_LIKELY_BENIGN", {"known_entity": own["entity_name"], "entity_type": own["entity_type"],
                                                 "why": "the flagged address is on the attribution list"}))

    hits = [] if own else flows.trace_to_vasp(addr, known)
    # freeze while the money is likely still on the exchange: it arrived fast after receipt (quick cash-out), or it
    # arrived within the window before the latest data (e.g. a dormant watched wallet that just woke up)
    fresh = []
    for h in hits:
        age = (now - pd.Timestamp(h["deposit_ts"])).total_seconds() / 60
        quick = h["minutes_after_receipt"] is not None and h["minutes_after_receipt"] <= FREEZE_WINDOW_MIN
        if quick or 0 <= age <= FREEZE_WINDOW_MIN:
            fresh.append((0 if quick else 1, h["minutes_after_receipt"] if quick else age, h, round(age, 1), quick))
    if fresh and risk >= FREEZE_MIN_RISK:
        _, _, h, age, quick = min(fresh, key=lambda x: (x[0], x[1]))
        check = (f"{h['minutes_after_receipt']} min after receipt ≤ {FREEZE_WINDOW_MIN:.0f} min" if quick
                 else f"deposited {age} min before the latest data ≤ {FREEZE_WINDOW_MIN:.0f} min")
        matched.append(("IMMEDIATE_FREEZE_DRAFT", {**h, "risk": risk, "minutes_before_latest_data": age,
                        "jurisdiction_note": None if h["in_jurisdiction"] else
                        "exchange is outside India: send as a voluntary hold request; formal route is a Letter of Request (Section 112 BNSS) / MLAT",
                        "check": check}))
    indian = [h for h in hits if h["in_jurisdiction"]]
    if indian:
        h = min(indian, key=lambda x: x["hops"])
        matched.append(("DRAFT_SECTION_94_BNSS", {**h, "vasps_reached": sorted({x["vasp"] for x in indian}),
                                                  "deposits_found": len(indian)}))

    # value is measured over the whole CIOH cluster (one owner): launderers split funds over many small wallets
    moved = max(float(w.get("sent_btc", 0)), float(w.get("recv_btc", 0)), float(w.get("_cluster_sent_btc", 0)))
    risky_share = float(w.get("share_risky_asn", 0))
    layering = {k: round(float(w.get(c, 0)), 3) for k, c in (("peel", "max_p_peel"), ("coinjoin", "max_p_coinjoin"),
                                                             ("fan_out", "max_p_fan_out")) if float(w.get(c, 0)) > 0.5}
    if float(w.get("max_peel_chain_len", 0)) >= MIN_PEEL_CHAIN:
        layering["peel_chain_len"] = int(w["max_peel_chain_len"])
    if moved >= LAYERING_MIN_BTC and risky_share > 0 and layering:
        matched.append(("FIU_REFERRAL_PACK", {
            "btc_moved": round(moved, 6), "risky_broadcast_share": round(risky_share, 3),
            "first_relay_asn_type": (alert.get("evidence") or {}).get("first_spy_asn_type"), "layering": layering,
            "offshore_vasps": sorted({h["vasp"] for h in hits if not h["in_jurisdiction"]}),
            "measured_over": "cluster" if moved > max(float(w.get("sent_btc", 0)), float(w.get("recv_btc", 0))) else "wallet",
            "check": f"{moved:.3f} BTC ≥ {LAYERING_MIN_BTC:g}, risky share {risky_share:.2f} > 0"}))

    balance = float(w.get("recv_btc", 0)) - float(w.get("sent_btc", 0))
    last = flows.last_seen.get(addr)
    dormant_h = (now - last).total_seconds() / 3600 if last is not None else 0.0
    taint, hops_from, hops_to = float(w.get("taint", 0)), float(w.get("hops_from_seed", 99)), float(w.get("hops_to_seed", 99))
    if balance > 1e-4 and dormant_h >= DORMANT_H and (taint > 0 or min(hops_from, hops_to) <= SEED_LINK_HOPS):
        matched.append(("PASSIVE_TAINT_MONITOR", {"unspent_btc": round(balance, 8), "dormant_h": round(dormant_h, 1),
                                                  "taint": round(taint, 4), "hops_to_nearest_seed": int(min(hops_from, hops_to))}))

    if not own:
        pools = sorted({known[a]["entity_name"] for a in flows.funders(addr) if known.get(a, {}).get("entity_type") == "MINING_POOL"})
        if pools and taint == 0 and min(hops_from, hops_to) >= NO_SEED_PATH and risky_share == 0:
            matched.append(("REVIEW_LIKELY_BENIGN", {"funded_by": pools, "why": "mining-pool payout recipient, no seed link"}))

    if not matched:
        matched.append(("ANALYST_REVIEW", {}))
    matched.sort(key=lambda m: int(ACTIONS[m[0]]["priority"]))
    action, facts = matched[0]
    spec = ACTIONS[action]
    return {"action": action, "title": spec["title"], "rule": spec["rule"], "legal_basis": spec["legal_basis"],
            "facts": facts, "shap_support": _shap_support(alert),
            "vasp_exposure": sorted(hits, key=lambda h: (h["hops"], h["deposit_ts"]))[:25],
            "also_matched": [m[0] for m in matched[1:] if m[0] != action]}


def recommend(alerts: List[dict], W: pd.DataFrame, f, known: Dict[str, dict], now: Optional[Any] = None) -> None:
    """Attach `recommended_action` to every alert in place."""
    if not alerts:
        return
    flows = _Flows(f)
    if "cluster_id" in W and "sent_btc" in W:
        solo = W["cluster_id"].astype(str).str.startswith("SOLO")
        W = W.assign(_cluster_sent_btc=W.groupby("cluster_id")["sent_btc"].transform("sum").where(~solo, W["sent_btc"]))
    now = now if now is not None else pd.to_datetime(f.tx["ts"]).max()
    for a in alerts:
        w = W.loc[a["entity_id"]] if a["entity_id"] in W.index else pd.Series(dtype=float)
        a["recommended_action"] = _decide(a, w, flows, known, now)


def load_known(conn) -> Dict[str, dict]:
    try:
        rows = conn.execute("SELECT address, entity_name, entity_type, country, in_jurisdiction FROM known_entities").fetchall()
    except Exception:  # older database without the table
        return {}
    return {r[0]: {"entity_name": r[1], "entity_type": (r[2] or "VASP").upper(), "country": r[3],
                   "in_jurisdiction": bool(r[4])} for r in rows}
