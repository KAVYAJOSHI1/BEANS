"""Re-run the ML pipeline over everything in the DB (after new seeds or a new file) without losing analyst work."""
import threading
from typing import Any, Dict

from beans.api import db
from beans.ingest.pipeline import ForensicPipeline
from beans.schema import CanonicalRecord

_lock = threading.Lock()
_FIELDS = set(CanonicalRecord.model_fields)


def rescore_all() -> Dict[str, Any]:
    with _lock:
        records = []
        for r in db.query("SELECT * FROM transactions ORDER BY timestamp"):
            data = {k: v for k, v in r.items() if k in _FIELDS and v is not None}
            try:
                records.append(CanonicalRecord(**data))
            except ValueError:
                continue
        # Alert ids are regenerated on every run, so carry analyst state over by entity
        kept = db.query("SELECT entity_id, status, assigned_to FROM alerts "
                        "WHERE status != 'OPEN' OR assigned_to != 'Unassigned'")
        db.execute("DELETE FROM alerts")
        stats = ForensicPipeline().execute_ml_pipeline(records)
        for k in kept:
            db.execute("UPDATE alerts SET status = ?, assigned_to = ? WHERE entity_id = ?",
                       [k["status"], k["assigned_to"], k["entity_id"]])
        return {"records_rescored": len(records), "pipeline_stats": stats, "analyst_states_preserved": len(kept)}
