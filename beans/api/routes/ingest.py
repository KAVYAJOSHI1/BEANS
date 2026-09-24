from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
import shutil
from typing import Dict, Any
from beans.config import settings
from beans.ingest.pipeline import ForensicPipeline
from beans.synth.writer import SyntheticDatasetWriter

router = APIRouter(prefix="/ingest", tags=["Ingestion & Pipeline"])

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = settings.DATA_DIR / file.filename

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    pipeline = ForensicPipeline()
    result = pipeline.run_file_ingestion(temp_path)
    return result

@router.post("/synth-demo")
def generate_synth_demo(n_tx: int = 500) -> Dict[str, Any]:
    """Generates synthetic dataset and immediately runs full ingestion pipeline"""
    demo_dir = settings.DATA_DIR / "synth" / "demo"
    manifest = SyntheticDatasetWriter.generate_dataset(demo_dir, n_tx=n_tx)

    # Ingest the generated CSV
    pipeline = ForensicPipeline()
    csv_file = demo_dir / "transactions.csv"
    res = pipeline.run_file_ingestion(csv_file)

    return {
        "status": "success",
        "manifest": manifest,
        "pipeline_result": res
    }
