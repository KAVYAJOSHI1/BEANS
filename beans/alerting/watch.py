"""Watchlist: re-alert when watched funds move.

A wallet is watched from a point in *data time* (the latest transaction in the database when it was added), so
replaying historical files behaves the same as live monitoring. After every scoring run, any spend by a watched
wallet later than that point becomes a movement event. Events are permanent (the alerts table is rebuilt on every
run), unique per (wallet, transaction), traced forward to known exchanges, and pushed to the SIEM webhooks.

Wallets are added:
  * automatically when their action directive is PASSIVE_TAINT_MONITOR (settings.WATCH_AUTO_TAINT_MONITOR)
  * by an analyst (alert drawer, API) or from a case
"""
import hashlib
import json
from typing import Any, Dict, List, Optional

import pandas as pd

from beans.config import settings

EVENT_SEVERITY = "CRITICAL"


def data_now(conn):
    return conn.execute("SELECT max(timestamp) FROM transactions").fetchone()[0]


def add(conn, address: str, reason: str, alert_id: Optional[str] = None, case_id: Optional[int] = None,
        note: str = "", watched_from=None) -> bool:
    """Start watching `address` (idempotent; re-activates an inactive entry). Returns True if newly added."""
    row = conn.execute("SELECT active FROM watchlist WHERE address = ?", [address]).fetchone()
    if row and row[0]:
        return False
    since = watched_from or data_now(conn)
    balance = conn.execute("SELECT balance FROM wallet_profiles WHERE address = ?", [address]).fetchone()
    if row:
        conn.execute("UPDATE watchlist SET active = TRUE, reason = ?, watched_from = ?, alert_id = ?, case_id = ?, "
                     "note = ?, balance_at_watch = ? WHERE address = ?",
                     [reason, since, alert_id, case_id, note, balance[0] if balance else None, address])
    else:
        conn.execute("INSERT INTO watchlist (address, reason, alert_id, case_id, note, watched_from, balance_at_watch) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?)",
                     [address, reason, alert_id, case_id, note, since, balance[0] if balance else None])
    return True


def auto_watch(conn, alerts: List[dict]) -> int:
    if not settings.WATCH_AUTO_TAINT_MONITOR:
        return 0
    return sum(add(conn, a["entity_id"], "AUTO_TAINT_WATCH", alert_id=a["alert_id"],
                   note=(a.get("recommended_action") or {}).get("rule", ""))
               for a in alerts if (a.get("recommended_action") or {}).get("action") == "PASSIVE_TAINT_MONITOR")


def check(conn, frames=None, known: Optional[Dict[str, dict]] = None) -> List[dict]:
    """Record a movement event for every new spend by an active watched wallet. Returns the new events."""
    watched = conn.execute("SELECT address, watched_from, reason, alert_id, case_id FROM watchlist WHERE active").df()
    if watched.empty:
        return []
    spends = _spends(conn, watched)
    if not spends:
        return []
    flows = None
    if frames is not None and known:
        from beans.decision.actions import _Flows
        flows = _Flows(frames)
    now = data_now(conn)
    meta = watched.set_index("address")
    events = []
    for addr, txid, ts, ip, asn_type, country, outs, amts, moved in spends:
        hits = []
        if flows is not None:
            hits = [h for h in flows.trace_to_vasp(addr, known) if pd.Timestamp(h["deposit_ts"]) >= pd.Timestamp(ts)]
        first_vasp = min(hits, key=lambda h: h["deposit_ts"]) if hits else None
        m = meta.loc[addr]
        ev = {
            "event_id": "W-" + hashlib.sha1(f"{addr}|{txid}".encode()).hexdigest()[:10],
            "address": addr, "txid": txid, "ts": ts, "amount_btc": round(float(moved or 0), 8),
            "destinations": json.dumps([{"address": a, "amount": v} for a, v in zip(outs or [], amts or [])][:20]),
            "first_spy_ip": ip, "first_spy_asn_type": asn_type, "first_spy_country": country,
            "vasp": first_vasp["vasp"] if first_vasp else None,
            "vasp_in_jurisdiction": bool(first_vasp["in_jurisdiction"]) if first_vasp else None,
            "vasp_deposit_address": first_vasp["deposit_address"] if first_vasp else None,
            "vasp_deposit_ts": first_vasp["deposit_ts"] if first_vasp else None,
            "minutes_since_move": round((pd.Timestamp(now) - pd.Timestamp(ts)).total_seconds() / 60, 1),
            "watch_reason": m["reason"], "alert_id": m["alert_id"], "case_id": None if pd.isna(m["case_id"]) else int(m["case_id"]),
            "recommended": ("IMMEDIATE_FREEZE_DRAFT" if first_vasp else "TRACE_AND_REVIEW"),
        }
        conn.execute(f"INSERT INTO watch_events ({', '.join(ev)}) VALUES ({', '.join('?' * len(ev))})", list(ev.values()))
        events.append(ev)
    return events


def _spends(conn, watched: pd.DataFrame) -> list:
    conn.register("watched_in", watched[["address", "watched_from"]])
    try:
        return conn.execute("""
            SELECT w.address, t.txid, t.timestamp, t.src_ip, t.asn_type, t.geo_country, t.output_addresses,
                   t.output_amounts,
                   list_sum(list_transform(list_zip(t.input_addresses, t.input_amounts),
                                           x -> CASE WHEN x[1] = w.address THEN x[2] ELSE 0 END)) AS moved
            FROM watched_in w
            JOIN transactions t ON list_contains(t.input_addresses, w.address) AND t.timestamp > w.watched_from
            WHERE NOT EXISTS (SELECT 1 FROM watch_events e WHERE e.address = w.address AND e.txid = t.txid)
            ORDER BY t.timestamp""").fetchall()
    finally:
        conn.unregister("watched_in")


def as_alert(ev: Dict[str, Any]) -> Dict[str, Any]:
    """A movement event in the alert shape the webhook formats expect."""
    where = f" to {ev['vasp']}" if ev.get("vasp") else ""
    return {
        "alert_id": ev["event_id"], "entity_id": ev["address"], "entity_type": "WALLET",
        "alert_type": "WATCHED_FUNDS_MOVED", "risk_score": 100.0, "calibrated_confidence": 1.0,
        "severity": EVENT_SEVERITY, "status": ev.get("status") or "OPEN", "created_at": str(ev.get("detected_at") or ev["ts"]),
        "reasons": [f"Watched wallet moved {ev['amount_btc']:.8f} BTC{where} in tx {ev['txid'][:16]}… "
                    f"({ev.get('minutes_since_move')} min before the latest data)"],
        "engine_scores": {}, "evidence": {"txid": ev["txid"], "first_spy_ip": ev.get("first_spy_ip"),
                                          "first_spy_asn_type": ev.get("first_spy_asn_type")},
        "recommended_action": {"action": ev.get("recommended"),
                               "rule": "Watched funds moved" + (" and reached a known exchange: freeze while they are there"
                                                                if ev.get("vasp") else "")},
    }
