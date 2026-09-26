"""SIEM / threat-intel webhook configuration and delivery log."""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from beans.alerting import webhooks as wh
from beans.api import db
from beans.store.duck import DuckStore

router = APIRouter(prefix="/webhooks", tags=["SIEM Webhooks"])


def _get(hook_id: int) -> Dict[str, Any]:
    h = db.one("SELECT * FROM webhooks WHERE id = ?", [hook_id])
    if not h:
        raise HTTPException(404, f"webhook {hook_id} not found")
    return h


def _public(h: Dict[str, Any]) -> Dict[str, Any]:
    token = h.pop("token", None)
    h["token_set"] = bool(token)
    h["sent"] = db.scalar("SELECT COUNT(*) FROM webhook_log WHERE webhook_id = ? AND status = 'SENT'", [h["id"]])
    h["failed"] = db.scalar("SELECT COUNT(*) FROM webhook_log WHERE webhook_id = ? AND status = 'FAILED'", [h["id"]])
    return h


@router.get("")
def list_hooks() -> List[Dict[str, Any]]:
    return [_public(h) for h in db.query("SELECT * FROM webhooks ORDER BY id")]


@router.post("")
def add_hook(payload: Dict[str, Any]):
    url = str(payload.get("url") or "").strip()
    fmt = str(payload.get("fmt") or "json").lower()
    sev = str(payload.get("min_severity") or "CRITICAL").upper()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(422, "url must start with http:// or https://")
    if fmt not in wh.FORMATS:
        raise HTTPException(422, f"fmt must be one of {sorted(wh.FORMATS)}")
    if sev not in wh.SEVERITY_RANK:
        raise HTTPException(422, f"min_severity must be one of {list(wh.SEVERITY_RANK)}")
    new_id = int(db.scalar("SELECT COALESCE(MAX(id), 0) + 1 FROM webhooks"))
    name = str(payload.get("name") or f"{fmt} webhook {new_id}")
    db.execute("INSERT INTO webhooks (id, name, url, fmt, min_severity, token, enabled) VALUES (?, ?, ?, ?, ?, ?, ?)",
               [new_id, name, url, fmt, sev, payload.get("token") or None, bool(payload.get("enabled", True))])
    db.audit("WEBHOOK_ADD", "WEBHOOK", str(new_id), {"name": name, "url": url, "fmt": fmt, "min_severity": sev})
    return _public(_get(new_id))


@router.patch("/{hook_id}")
def update_hook(hook_id: int, payload: Dict[str, Any]):
    _get(hook_id)
    if "enabled" in payload:
        db.execute("UPDATE webhooks SET enabled = ? WHERE id = ?", [bool(payload["enabled"]), hook_id])
    if payload.get("min_severity"):
        sev = str(payload["min_severity"]).upper()
        if sev not in wh.SEVERITY_RANK:
            raise HTTPException(422, f"min_severity must be one of {list(wh.SEVERITY_RANK)}")
        db.execute("UPDATE webhooks SET min_severity = ? WHERE id = ?", [sev, hook_id])
    db.audit("WEBHOOK_UPDATE", "WEBHOOK", str(hook_id), {k: v for k, v in payload.items() if k != "token"})
    return _public(_get(hook_id))


@router.delete("/{hook_id}")
def delete_hook(hook_id: int):
    _get(hook_id)
    db.execute("DELETE FROM webhooks WHERE id = ?", [hook_id])
    db.audit("WEBHOOK_DELETE", "WEBHOOK", str(hook_id))
    return {"status": "success", "id": hook_id}


@router.post("/{hook_id}/test")
def test_hook(hook_id: int):
    res = wh.send_test(_get(hook_id))
    db.execute("INSERT INTO webhook_log (webhook_id, alert_id, status, http_status, attempts, error) VALUES (?, ?, ?, ?, ?, ?)",
               [hook_id, "A-TEST", "TEST" if res["ok"] else "FAILED", res["http_status"], res["attempts"], res["error"]])
    return res


@router.post("/dispatch")
def dispatch_now():
    """Send every undelivered qualifying alert now (normally this runs after each scoring run)."""
    return {"results": wh.dispatch_pending(DuckStore())}


@router.get("/log")
def delivery_log(limit: int = 100):
    return db.query("SELECT l.*, w.name FROM webhook_log l LEFT JOIN webhooks w ON w.id = l.webhook_id "
                    "ORDER BY sent_at DESC LIMIT ?", [limit])
