import csv
import io
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, UploadFile

from beans.api import db
from beans.api.rescore import rescore_all

router = APIRouter(prefix="/seeds", tags=["Seed Wallets"])


def _insert(address: str, threat_type: str, incident: str, confidence: float, source: str) -> None:
    db.execute("INSERT OR REPLACE INTO seeds (address, threat_type, incident_name, confidence, source) "
               "VALUES (?, ?, ?, ?, ?)", [address, threat_type, incident, confidence, source])


@router.get("")
def list_seeds() -> List[Dict[str, Any]]:
    return db.query("SELECT * FROM seeds ORDER BY created_at DESC")


@router.post("")
def add_seed(payload: Dict[str, Any]):
    address = str(payload.get("address") or "").strip()
    if not address:
        raise HTTPException(422, "address is required")
    _insert(address, payload.get("threat_type", "UNKNOWN"), payload.get("incident_name", "manual seed"),
            float(payload.get("confidence", 0.9)), payload.get("source", "ANALYST"))
    db.audit("SEED_ADD", "WALLET", address, payload)
    return {"status": "success", "address": address}


@router.post("/upload")
async def upload_seeds(file: UploadFile = File(...), rescore: bool = True):
    """CSV with an `address` column; optional threat_type/label, incident_name, confidence, source."""
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "address" not in reader.fieldnames:
        raise HTTPException(422, "CSV needs an 'address' column")
    n = 0
    for row in reader:
        addr = (row.get("address") or "").strip()
        if addr:
            _insert(addr, row.get("threat_type") or row.get("label") or "UNKNOWN",
                    row.get("incident_name") or file.filename, float(row.get("confidence") or 0.9),
                    row.get("source") or "UPLOAD")
            n += 1
    db.audit("SEED_UPLOAD", "FILE", file.filename, {"seeds": n})
    result = {"status": "success", "seeds_loaded": n}
    if rescore and n:
        result["rescore"] = rescore_all()
    return result


@router.delete("/{address}")
def delete_seed(address: str):
    db.execute("DELETE FROM seeds WHERE address = ?", [address])
    db.audit("SEED_DELETE", "WALLET", address)
    return {"status": "success", "address": address}


@router.post("/repropagate")
def repropagate():
    """Re-run all engines + fusion over the whole DB with the current seed list."""
    return rescore_all()
