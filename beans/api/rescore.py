"""Re-run the ML pipeline over everything in the DB (after new seeds or a new file) without losing analyst work."""
import threading
from typing import Any, Dict

from beans.api import db
from beans.ingest.pipeline import ForensicPipeline

_lock = threading.Lock()


def rescore_all() -> Dict[str, Any]:
    """Re-run all engines + fusion over the whole DB (analyst verdicts are carried over by entity)."""
    with _lock:
        stats = ForensicPipeline().execute_ml_pipeline()
        return {"records_rescored": stats.get("total_transactions", 0), "pipeline_stats": stats}
