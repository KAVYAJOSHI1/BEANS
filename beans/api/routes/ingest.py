import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, File, HTTPException, UploadFile

from beans.api import db
from beans.api.rescore import rescore_all
from beans.config import settings
from beans.ingest.pipeline import ForensicPipeline
from beans.synth.writer import SyntheticDatasetWriter

router = APIRouter(prefix="/ingest", tags=["Ingestion & Pipeline"])

ALLOWED = {".csv", ".json", ".ndjson", ".jsonl", ".xml"}
INBOX = settings.DATA_DIR / "inbox"
DATA_TABLES = ["transactions", "net_observations", "wallet_profiles", "alerts", "feedback", "seeds", "known_entities", "watchlist", "watch_events"]


def _ingest(path: Path, source: str, mapping: Path = None) -> Dict[str, Any]:
    result = ForensicPipeline(mapping=mapping).run_file_ingestion(path)   # scores the whole DB, not just this file
    db.execute("INSERT INTO ingest_log (file, sha256, size_bytes, records, source) VALUES (?, ?, ?, ?, ?)",
               [path.name, hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size,
                result.get("records_ingested", 0), source])
    db.audit("INGEST", "FILE", path.name, {"records": result.get("records_ingested"), "source": source})
    return result


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), mapping: UploadFile = File(None)) -> Dict[str, Any]:
    """Upload a CSV/JSON/XML file, optionally with a YAML column mapping for unfamiliar layouts."""
    name = Path(file.filename or "upload").name  # never trust client paths
    if Path(name).suffix.lower() not in ALLOWED:
        raise HTTPException(422, f"unsupported file type; allowed: {sorted(ALLOWED)}")
    INBOX.mkdir(parents=True, exist_ok=True)
    dest = INBOX / f"{datetime.now():%Y%m%d_%H%M%S}_{name}"
    dest.write_bytes(await file.read())
    map_path = None
    if mapping is not None and mapping.filename:
        map_path = INBOX / f"{dest.stem}.mapping.yaml"
        map_path.write_bytes(await mapping.read())
    try:
        return _ingest(dest, "UPLOAD", map_path)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/synth-demo")
def generate_synth_demo(n_tx: int = 1000, reset: bool = True) -> Dict[str, Any]:
    """Generate a labelled synthetic dataset and run the full pipeline on it."""
    if reset:
        for t in DATA_TABLES:
            db.execute(f"DELETE FROM {t}")
    demo_dir = settings.DATA_DIR / "synth" / "demo"
    manifest = SyntheticDatasetWriter.generate_dataset(demo_dir, n_tx=n_tx)
    result = _ingest(demo_dir / "transactions.csv", "SYNTHETIC_DEMO")   # also trains + refreshes the model card
    return {"status": "success", "manifest": manifest, "pipeline_result": result}
