from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from datetime import datetime
from beans.store.duck import DuckStore
from beans.report.pdf_export import LawEnforcementReportGenerator

router = APIRouter(prefix="/cases", tags=["Case Management"])

@router.get("")
def list_cases() -> List[Dict[str, Any]]:
    store = DuckStore()
    conn = store.get_connection()
    df = conn.execute("SELECT * FROM case_files ORDER BY created_at DESC").fetchdf()
    conn.close()
    return df.to_dict(orient="records")

@router.post("")
def create_case(payload: Dict[str, Any]):
    store = DuckStore()
    conn = store.get_connection()
    
    # Next ID
    max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM case_files").fetchone()[0]
    new_id = max_id + 1

    case_name = payload.get("case_name", f"Case #{new_id}")
    incident_type = payload.get("incident_type", "RANSOMWARE")
    suspects = payload.get("suspect_entities", [])
    notes = payload.get("notes", "")
    investigator = payload.get("investigator", "Special Agent Analyst")
    priority = payload.get("priority", "HIGH")

    conn.execute("""
    INSERT INTO case_files (id, case_name, incident_type, suspect_entities, notes, investigator, priority)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [new_id, case_name, incident_type, suspects, notes, investigator, priority])

    conn.close()
    return {"status": "success", "case_id": new_id, "case_name": case_name}

@router.get("/{case_id}/export")
def export_case_dossier(case_id: int) -> Dict[str, Any]:
    store = DuckStore()
    conn = store.get_connection()

    case_df = conn.execute("SELECT * FROM case_files WHERE id = ?", [case_id]).fetchdf()
    if case_df.empty:
        # Fallback default demo case
        case = {
            "id": case_id,
            "case_name": "Operation LockBit Eclipse - Extortion Syndicate",
            "incident_type": "RANSOMWARE",
            "suspect_entities": [],
            "notes": "Target syndicate active in laundering ransomware proceeds through CoinJoin mixers.",
            "investigator": "Forensics Special Agent"
        }
    else:
        case = case_df.to_dict(orient="records")[0]

    alerts_df = conn.execute("SELECT * FROM alerts ORDER BY risk_score DESC LIMIT 10").fetchdf()
    conn.close()

    dossier = LawEnforcementReportGenerator.generate_case_dossier(
        case_id=case["id"],
        case_name=case["case_name"],
        incident_type=case.get("incident_type", "RANSOMWARE"),
        suspect_wallets=case.get("suspect_entities") or [],
        investigator=case.get("investigator", "Senior Investigator"),
        notes=case.get("notes", ""),
        alerts=alerts_df.to_dict(orient="records")
    )
    return dossier
