from fastapi import APIRouter
from typing import List, Dict, Any
from beans.store.duck import DuckStore

router = APIRouter(prefix="/seeds", tags=["Seed Wallets"])

@router.get("")
def list_seeds() -> List[Dict[str, Any]]:
    store = DuckStore()
    conn = store.get_connection()
    df = conn.execute("SELECT * FROM seeds ORDER BY created_at DESC").fetchdf()
    conn.close()
    return df.to_dict(orient="records")

@router.post("")
def add_seed(payload: Dict[str, Any]):
    store = DuckStore()
    conn = store.get_connection()

    address = payload["address"].strip()
    threat_type = payload.get("threat_type", "RANSOMWARE")
    incident_name = payload.get("incident_name", "Investigator Manual Seed")
    confidence = float(payload.get("confidence", 0.95))
    source = payload.get("source", "MANUAL_INVESTIGATOR_INPUT")

    conn.execute("""
    INSERT OR REPLACE INTO seeds (address, threat_type, incident_name, confidence, source)
    VALUES (?, ?, ?, ?, ?)
    """, [address, threat_type, incident_name, confidence, source])

    conn.close()
    return {"status": "success", "address": address, "threat_type": threat_type}
