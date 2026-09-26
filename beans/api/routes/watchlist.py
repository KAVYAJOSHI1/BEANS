"""Watchlist of wallets and the movement events raised when they spend."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from beans.alerting import watch
from beans.api import db

router = APIRouter(tags=["Watchlist"])

EVENT_STATUSES = {"OPEN", "ACKNOWLEDGED"}


@router.get("/watchlist")
def list_watchlist(active: bool = True) -> List[Dict[str, Any]]:
    return db.query("""SELECT w.*, (SELECT COUNT(*) FROM watch_events e WHERE e.address = w.address) AS movements,
                              (SELECT max(ts) FROM watch_events e WHERE e.address = w.address) AS last_movement
                       FROM watchlist w WHERE active = ? ORDER BY added_at DESC""", [active])


@router.post("/watchlist")
def add_to_watchlist(payload: Dict[str, Any]):
    address = str(payload.get("address") or "").strip()
    if not address:
        raise HTTPException(422, "address is required")
    if not db.scalar("SELECT COUNT(*) FROM wallet_profiles WHERE address = ?", [address]):
        raise HTTPException(404, f"wallet {address} is not in the database")
    with db.connection() as conn:
        added = watch.add(conn, address, str(payload.get("reason") or "ANALYST").upper(), payload.get("alert_id"),
                          payload.get("case_id"), payload.get("note", ""))
    db.audit("WATCH_ADD", "WALLET", address, {k: payload.get(k) for k in ("reason", "alert_id", "case_id", "note")})
    return {"status": "success", "address": address, "added": added}


@router.delete("/watchlist/{address}")
def remove_from_watchlist(address: str):
    if not db.scalar("SELECT COUNT(*) FROM watchlist WHERE address = ? AND active", [address]):
        raise HTTPException(404, f"{address} is not being watched")
    db.execute("UPDATE watchlist SET active = FALSE WHERE address = ?", [address])
    db.audit("WATCH_REMOVE", "WALLET", address)
    return {"status": "success", "address": address}


@router.post("/cases/{case_id}/watch")
def watch_case(case_id: int):
    case = db.one("SELECT suspect_entities FROM case_files WHERE id = ?", [case_id])
    if not case:
        raise HTTPException(404, f"case {case_id} not found")
    wallets = [a for a in case["suspect_entities"] or []
               if db.scalar("SELECT COUNT(*) FROM wallet_profiles WHERE address = ?", [a])]
    with db.connection() as conn:
        added = sum(watch.add(conn, a, "CASE", case_id=case_id, note=f"suspect in case #{case_id}") for a in wallets)
    db.audit("WATCH_CASE", "CASE", str(case_id), {"wallets": len(wallets), "added": added})
    return {"status": "success", "watched": len(wallets), "added": added}


@router.get("/watch-events")
def list_events(status: Optional[str] = Query(None), limit: int = Query(200, ge=1, le=1000)) -> List[Dict[str, Any]]:
    where, params = ("WHERE status = ?", [status.upper()]) if status and status != "ALL" else ("", [])
    rows = db.query(f"SELECT * FROM watch_events {where} ORDER BY ts DESC LIMIT ?", params + [limit])
    for r in rows:
        r["destinations"] = r.get("destinations") or []
    return rows


@router.patch("/watch-events/{event_id}")
def update_event(event_id: str, payload: Dict[str, Any]):
    status = str(payload.get("status") or "").upper()
    if status not in EVENT_STATUSES:
        raise HTTPException(422, f"status must be one of {sorted(EVENT_STATUSES)}")
    if not db.scalar("SELECT COUNT(*) FROM watch_events WHERE event_id = ?", [event_id]):
        raise HTTPException(404, f"event {event_id} not found")
    db.execute("UPDATE watch_events SET status = ? WHERE event_id = ?", [status, event_id])
    db.audit("WATCH_EVENT_STATUS", "WATCH_EVENT", event_id, {"status": status})
    return {"status": "success", "event_id": event_id, "new_status": status}
