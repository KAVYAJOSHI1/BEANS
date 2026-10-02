"""Watchlist: re-alert when watched funds move.

A wallet is watched from a point in *data time* (the latest transaction in the database when it was added), so
replaying historical files behaves the same as live monitoring. After every scoring run, any spend by a watched
wallet later than that point becomes a movement event. Events are permanent (the alerts table is rebuilt on every
run), unique per (wallet, transaction), traced forward to known exchanges, and pushed to the SIEM webhooks.

Unconfirmed-first: `quick_check` runs right after files are loaded (the ingest worker, every few seconds), without waiting
for the next scoring run (at most once a minute). It records spends by watched wallets and seeds in the files that were
just loaded, marks each one unconfirmed when the transaction has no block yet, and flags BIP-125 replaceable ones. The
next scoring run adds the exchange trace to those events. An unconfirmed movement is a heads-up, never a freeze trigger:
the coins can still be replaced or dropped, and nothing has reached an exchange yet.

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
    flows = None
    if frames is not None and known:
        from beans.decision.actions import _Flows
        flows = _Flows(frames)
    if flows is not None:
        _enrich_quick(conn, flows, known)
    if watched.empty:
        return []
    spends = _spends(conn, watched)
    if not spends:
        return []
    return _record(conn, spends, watched.set_index("address"), flows, known, "SCORING")


def quick_check(conn, since) -> List[dict]:
    """Fast path: record spends by watched wallets and seeds in transactions stored at or after `since`, now."""
    watched = conn.execute("SELECT address, watched_from, reason, alert_id, case_id FROM watchlist WHERE active").df()
    spends = _spends(conn, watched if not watched.empty else pd.DataFrame(columns=["address", "watched_from"]),
                     since=since, seeds=True)
    return _record(conn, spends, watched.set_index("address") if not watched.empty else watched, None, None, "QUICK") \
        if spends else []


def _forecast(conn, alert_id) -> Optional[str]:
    """What the cash-out forecast (E7) says about the alert behind this event, if there is one."""
    if not alert_id:
        return None
    row = conn.execute("SELECT evidence FROM alerts WHERE alert_id = ?", [alert_id]).fetchone()
    try:
        fc = (json.loads(row[0]) if row and row[0] else {}).get("cashout_forecast") or {}
    except (TypeError, ValueError):
        return None
    if not fc.get("delay_minutes"):
        return None
    return json.dumps({"delay_minutes": fc["delay_minutes"], "likely_exchange": fc.get("likely_exchange"),
                       "destinations": (fc.get("destinations") or [])[:2]})


def _record(conn, spends, meta, flows, known, via: str) -> List[dict]:
    now = data_now(conn)
    events = []
    for addr, txid, ts, ip, asn_type, country, outs, amts, moved, confirmed_flag, rbf, src in spends:
        hits = []
        if flows is not None:
            hits = [h for h in flows.trace_to_vasp(addr, known) if pd.Timestamp(h["deposit_ts"]) >= pd.Timestamp(ts)]
        first_vasp = min(hits, key=lambda h: h["deposit_ts"]) if hits else None
        confirmed = confirmed_flag is not False   # unknown counts as confirmed: only the collector says False
        m = meta.loc[addr] if addr in meta.index else None
        alert_id = None if m is None or pd.isna(m["alert_id"]) else m["alert_id"]
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
            "watch_reason": "SEED" if src == "SEED" else (m["reason"] if m is not None else "SEED"),
            "alert_id": alert_id,
            "case_id": None if m is None or pd.isna(m["case_id"]) else int(m["case_id"]),
            "recommended": _recommend(confirmed, first_vasp),
            "confirmed": confirmed, "replaceable": None if rbf is None or pd.isna(rbf) else bool(rbf),
            "detected_via": via, "forecast": _forecast(conn, alert_id),
        }
        conn.execute(f"INSERT INTO watch_events ({', '.join(ev)}) VALUES ({', '.join('?' * len(ev))})", list(ev.values()))
        events.append(ev)
    return events


def _recommend(confirmed: bool, first_vasp) -> str:
    """Unconfirmed coins can still be replaced or dropped and have reached no exchange: a heads-up, never a freeze."""
    if not confirmed:
        return "UNCONFIRMED_MOVEMENT"
    return "IMMEDIATE_FREEZE_DRAFT" if first_vasp else "TRACE_AND_REVIEW"


def _enrich_quick(conn, flows, known) -> None:
    """Scoring has run: give the events recorded by the fast path their exchange trace."""
    rows = conn.execute("SELECT event_id, address, ts, confirmed FROM watch_events "
                        "WHERE detected_via = 'QUICK' AND vasp IS NULL AND vasp_deposit_ts IS NULL").fetchall()
    for eid, addr, ts, confirmed in rows:
        hits = [h for h in flows.trace_to_vasp(addr, known) if pd.Timestamp(h["deposit_ts"]) >= pd.Timestamp(ts)]
        if not hits:
            continue
        h = min(hits, key=lambda x: x["deposit_ts"])
        conn.execute("UPDATE watch_events SET vasp = ?, vasp_in_jurisdiction = ?, vasp_deposit_address = ?, "
                     "vasp_deposit_ts = ?, recommended = ? WHERE event_id = ?",
                     [h["vasp"], bool(h["in_jurisdiction"]), h["deposit_address"], h["deposit_ts"],
                      _recommend(bool(confirmed), h), eid])


def db_now(conn):
    """The database clock in the same form as `created_at` (use it to mark the start of a load)."""
    return conn.execute("SELECT CURRENT_TIMESTAMP::TIMESTAMP").fetchone()[0]


def _spends(conn, watched: pd.DataFrame, since=None, seeds: bool = False) -> list:
    """New spends by watched wallets (and, with `seeds`, by seed wallets). `since` limits them to transactions stored
    at or after that database time (the files just loaded)."""
    conn.register("watched_in", watched[["address", "watched_from"]])
    try:
        seed_sql = ("UNION ALL SELECT address, CAST(NULL AS TIMESTAMP), 'SEED' FROM seeds "
                    "WHERE address NOT IN (SELECT address FROM watched_in)") if seeds else ""
        return conn.execute(f"""
            WITH w AS (SELECT address, watched_from, 'WATCHLIST' AS src FROM watched_in {seed_sql})
            SELECT w.address, t.txid, t.timestamp, t.src_ip, t.asn_type, t.geo_country, t.output_addresses,
                   t.output_amounts,
                   list_sum(list_transform(list_zip(t.input_addresses, t.input_amounts),
                                           x -> CASE WHEN x[1] = w.address THEN x[2] ELSE 0 END)) AS moved,
                   t.confirmed, t.rbf, w.src
            FROM w
            JOIN transactions t ON list_contains(t.input_addresses, w.address)
                 AND (w.watched_from IS NULL OR t.timestamp > w.watched_from)
                 AND (? IS NULL OR t.created_at >= ?)
            WHERE NOT EXISTS (SELECT 1 FROM watch_events e WHERE e.address = w.address AND e.txid = t.txid)
            ORDER BY t.timestamp""", [since, since]).fetchall()
    finally:
        conn.unregister("watched_in")


def as_alert(ev: Dict[str, Any]) -> Dict[str, Any]:
    """A movement event in the alert shape the webhook formats expect."""
    where = f" to {ev['vasp']}" if ev.get("vasp") else ""
    unconfirmed = ev.get("confirmed") is False
    return {
        "alert_id": ev["event_id"], "entity_id": ev["address"], "entity_type": "WALLET",
        "alert_type": "WATCHED_FUNDS_MOVED", "risk_score": 100.0, "calibrated_confidence": 1.0,
        "severity": EVENT_SEVERITY, "status": ev.get("status") or "OPEN", "created_at": str(ev.get("detected_at") or ev["ts"]),
        "reasons": [f"Watched wallet moved {ev['amount_btc']:.8f} BTC{where} in tx {ev['txid'][:16]}… "
                    f"({ev.get('minutes_since_move')} min before the latest data)"
                    + (". UNCONFIRMED: not in a block yet, may still be replaced or dropped" if unconfirmed else "")],
        "engine_scores": {}, "evidence": {"txid": ev["txid"], "first_spy_ip": ev.get("first_spy_ip"),
                                          "first_spy_asn_type": ev.get("first_spy_asn_type")},
        "recommended_action": {"action": ev.get("recommended"),
                               "rule": ("Watched funds moved in an unconfirmed transaction: heads-up only, no freeze until it confirms"
                                if unconfirmed else "Watched funds moved" + (" and reached a known exchange: freeze while they are there"
                                                                              if ev.get("vasp") else ""))},
    }
