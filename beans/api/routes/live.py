"""Live monitor: state of the P2P collector and the watch folder, ingest rate and the newest alerts.

The collector (`beans collect --out DIR`) and the watcher (`beans watch DIR`) run as their own processes and write
`collector.status` / `watch.status` into DIR every few seconds; this route only reads those files and the database.
"""
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query

from beans.api import db
from beans.config import settings

router = APIRouter(prefix="/live", tags=["Live monitor"])
STALE_S = 30   # a status file older than this means the process stopped (or hangs)


def _status(path: Path) -> Optional[Dict[str, Any]]:
    try:
        s = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    age = time.time() - float(s.get("updated_at", 0))
    s["age_s"] = round(age, 1)
    s["alive"] = bool(s.get("running", True)) and age <= STALE_S
    return s


@router.get("/status")
def status(folder: Optional[str] = Query(None, description="watched folder (default: settings.LIVE_INBOX)"),
           minutes: int = Query(30, ge=5, le=24 * 60)) -> Dict[str, Any]:
    inbox = Path(folder) if folder else (settings.LIVE_INBOX or settings.DATA_DIR / "inbox")
    waiting = sorted(p.name for p in inbox.glob("*") if p.is_file() and p.suffix.lower() in
                     {".csv", ".json", ".ndjson", ".jsonl", ".xml"}) if inbox.is_dir() else []
    # transactions stored per minute (wall clock of ingestion), for the rate chart
    rate = db.query("""SELECT strftime(date_trunc('minute', created_at), '%H:%M') AS minute, COUNT(*) AS n
                       FROM transactions WHERE created_at >= now()::TIMESTAMP - to_minutes(CAST(? AS BIGINT))
                       GROUP BY date_trunc('minute', created_at) ORDER BY date_trunc('minute', created_at)""", [minutes])
    files = db.query("SELECT file, records, source, ingested_at FROM ingest_log ORDER BY ingested_at DESC LIMIT 12") \
        if db.table_exists("ingest_log") else []
    alerts = db.query("""SELECT alert_id, entity_id, alert_type, risk_score, severity, created_at,
                                json_extract_string(recommended_action, '$.action') AS action
                         FROM alerts ORDER BY created_at DESC, risk_score DESC LIMIT 10""")
    latest = db.query("SELECT MAX(timestamp) AS newest_tx, COUNT(*) AS transactions FROM transactions")[0]
    return {"folder": str(inbox), "collector": _status(inbox / "collector.status"),
            "watcher": _status(inbox / "watch.status"), "files_waiting": waiting, "recent_files": files,
            "tx_per_minute": rate, "recent_alerts": alerts, "newest_transaction": latest["newest_tx"],
            "transactions": latest["transactions"], "open_movement_events": db.scalar(
                "SELECT COUNT(*) FROM watch_events WHERE status = 'OPEN'") if db.table_exists("watch_events") else 0}
