from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from beans.api import db
from beans.api.routes.alerts import alert_out
from beans.report.pdf_export import CaseReportGenerator

router = APIRouter(prefix="/cases", tags=["Case Management"])

CASE_STATUSES = {"OPEN", "INVESTIGATING", "CLOSED"}


def _case(case_id: int) -> Dict[str, Any]:
    case = db.one("SELECT * FROM case_files WHERE id = ?", [case_id])
    if not case:
        raise HTTPException(404, f"case {case_id} not found")
    return case


@router.get("")
def list_cases() -> List[Dict[str, Any]]:
    cases = db.query("SELECT * FROM case_files ORDER BY created_at DESC")
    for c in cases:
        c["alert_count"] = db.scalar("SELECT COUNT(*) FROM alerts WHERE list_contains(?, entity_id)",
                                     [c["suspect_entities"] or []]) if c["suspect_entities"] else 0
    return cases


@router.post("")
def create_case(payload: Dict[str, Any]):
    name = str(payload.get("case_name") or "").strip()
    if not name:
        raise HTTPException(422, "case_name is required")
    suspects = sorted({s.strip() for s in payload.get("suspect_entities") or [] if str(s).strip()})
    new_id = int(db.scalar("SELECT COALESCE(MAX(id), 0) + 1 FROM case_files"))
    db.execute(
        "INSERT INTO case_files (id, case_name, incident_type, suspect_entities, linked_txids, notes, investigator, priority) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [new_id, name, payload.get("incident_type", "UNKNOWN"), suspects, payload.get("linked_txids") or [],
         payload.get("notes", ""), payload.get("investigator", "analyst"), payload.get("priority", "HIGH")])
    db.audit("CASE_CREATE", "CASE", str(new_id), {"case_name": name, "suspects": suspects})
    return {"status": "success", "case_id": new_id, "case_name": name}


@router.get("/{case_id}")
def get_case(case_id: int) -> Dict[str, Any]:
    case = _case(case_id)
    suspects = case["suspect_entities"] or []
    alerts = db.query("SELECT * FROM alerts WHERE list_contains(?, entity_id) ORDER BY risk_score DESC",
                      [suspects]) if suspects else []
    return {**case, "alerts": [alert_out(a) for a in alerts]}


@router.patch("/{case_id}")
def update_case(case_id: int, payload: Dict[str, Any]):
    case = _case(case_id)
    status = str(payload.get("status", case["status"])).upper()
    if status not in CASE_STATUSES:
        raise HTTPException(422, f"status must be one of {sorted(CASE_STATUSES)}")
    suspects = set(case["suspect_entities"] or []) | {s.strip() for s in payload.get("add_entities") or [] if s.strip()}
    suspects -= set(payload.get("remove_entities") or [])
    db.execute("UPDATE case_files SET status = ?, notes = ?, suspect_entities = ?, updated_at = now() WHERE id = ?",
               [status, payload.get("notes", case["notes"]), sorted(suspects), case_id])
    db.audit("CASE_UPDATE", "CASE", str(case_id), payload)
    return get_case(case_id)


@router.get("/{case_id}/export")
def export_case(case_id: int, fmt: str = Query("json", pattern="^(json|md|pdf|html)$")):
    case = get_case(case_id)
    sources = db.query("SELECT file, sha256, records, source, ingested_at FROM ingest_log ORDER BY ingested_at")
    audit = db.query("SELECT created_at, investigator, action, entity_type, entity_id FROM audit_log "
                     "WHERE (entity_type = 'CASE' AND entity_id = ?) OR list_contains(?, entity_id) ORDER BY created_at",
                     [str(case_id), [a["alert_id"] for a in case["alerts"]]])
    pack = CaseReportGenerator.build(case, case["alerts"], sources, audit)
    db.audit("CASE_EXPORT", "CASE", str(case_id), {"format": fmt, "evidence_sha256": pack["evidence_sha256"],
                                                   "timestamp_serial": (pack.get("timestamp") or {}).get("serial")})
    stem = f"BEANS_case_{case_id}"
    if fmt == "pdf":
        try:
            pdf = CaseReportGenerator.to_pdf(pack["html"])
        except Exception as e:  # missing system libs → tell the UI to use the HTML export instead
            raise HTTPException(501, f"PDF rendering unavailable ({e}); use fmt=html") from e
        return Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{stem}.pdf"'})
    if fmt == "html":
        return Response(pack["html"], media_type="text/html")
    if fmt == "md":
        return Response(pack["markdown"], media_type="text/markdown",
                        headers={"Content-Disposition": f'attachment; filename="{stem}.md"'})
    return {k: pack[k] for k in ("case_id", "case_name", "evidence_sha256", "timestamp", "evidence", "markdown")}
