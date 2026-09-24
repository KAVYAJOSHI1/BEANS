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
DATA_TABLES = ["transactions", "net_observations", "wallet_profiles", "alerts", "feedback"]


def _ingest(path: Path, source: str) -> Dict[str, Any]:
    had_data = bool(db.scalar("SELECT COUNT(*) FROM transactions"))
    result = ForensicPipeline().run_file_ingestion(path)
    db.execute("INSERT INTO ingest_log (file, sha256, size_bytes, records, source) VALUES (?, ?, ?, ?, ?)",
               [path.name, hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size,
                result.get("records_ingested", 0), source])
    db.audit("INGEST", "FILE", path.name, {"records": result.get("records_ingested"), "source": source})
    if had_data:  # the pipeline scored only this file; rebuild alerts over the whole dataset
        result["rescore"] = rescore_all()
    return result


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    name = Path(file.filename or "upload").name  # never trust client paths
    if Path(name).suffix.lower() not in ALLOWED:
        raise HTTPException(422, f"unsupported file type; allowed: {sorted(ALLOWED)}")
    INBOX.mkdir(parents=True, exist_ok=True)
    dest = INBOX / f"{datetime.now():%Y%m%d_%H%M%S}_{name}"
    dest.write_bytes(await file.read())
    try:
        return _ingest(dest, "UPLOAD")
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
    result = _ingest(demo_dir / "transactions.csv", "SYNTHETIC_DEMO")
    # synthetic data has ground truth → refresh the model card automatically
    from beans.score.model_card import build_model_card
    with db.connection() as conn:
        build_model_card(conn, demo_dir / "labels.csv")
    return {"status": "success", "manifest": manifest, "pipeline_result": result}
