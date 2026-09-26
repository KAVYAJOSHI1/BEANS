from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Response

from beans.api import db

router = APIRouter(prefix="/alerts", tags=["Alerts"])

STATUSES = {"OPEN", "INVESTIGATING", "CONFIRMED", "RESOLVED", "FALSE_POSITIVE"}
FEEDBACK_LABEL = {"FALSE_POSITIVE": "FALSE_POSITIVE", "CONFIRMED": "TRUE_POSITIVE"}


def alert_out(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "alert_id": row["alert_id"],
        "entity_id": row["entity_id"],
        "entity_type": row["entity_type"],
        "alert_type": row["alert_type"],
        "risk_score": float(row.get("risk_score") or 0.0),
        "calibrated_confidence": float(row.get("calibrated_confidence") or 0.0),
        "severity": row.get("severity"),
        "reasons": row.get("reasons") or [],
        "shap_top_features": row.get("shap_top_features") or [],
        "engine_scores": row.get("engine_scores") or {},
        "evidence": row.get("evidence") or {},
        "recommended_action": row.get("recommended_action") or {},
        "status": row.get("status") or "OPEN",
        "assigned_to": row.get("assigned_to") or "Unassigned",
        "created_at": row.get("created_at"),
    }


@router.get("")
def list_alerts(
    response: Response,
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    alert_type: Optional[str] = Query(None, alias="type"),
    action: Optional[str] = Query(None, description="recommended action, e.g. IMMEDIATE_FREEZE_DRAFT"),
    q: Optional[str] = Query(None, description="search entity id, alert type, txid or IP"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> List[Dict[str, Any]]:
    where, params = ["1=1"], []
    if severity and severity != "ALL":
        where.append("severity = ?")
        params.append(severity)
    if status and status != "ALL":
        where.append("status = ?")
        params.append(status)
    if alert_type and alert_type != "ALL":
        where.append("alert_type = ?")
        params.append(alert_type)
    if action and action != "ALL":
        where.append("json_extract_string(recommended_action, '$.action') = ?")
        params.append(action)
    if q:
        where.append("(entity_id ILIKE ? OR alert_type ILIKE ? OR CAST(evidence AS VARCHAR) ILIKE ?)")
        params.extend([f"%{q}%"] * 3)
    cond = " AND ".join(where)
    response.headers["X-Total-Count"] = str(db.scalar(f"SELECT COUNT(*) FROM alerts WHERE {cond}", params))
    rows = db.query(
        f"SELECT * FROM alerts WHERE {cond} ORDER BY risk_score DESC, calibrated_confidence DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    )
    return [alert_out(r) for r in rows]


@router.get("/{alert_id}")
def get_alert(alert_id: str) -> Dict[str, Any]:
    row = db.one("SELECT * FROM alerts WHERE alert_id = ?", [alert_id])
    if not row:
        raise HTTPException(404, f"alert {alert_id} not found")
    return alert_out(row)


@router.patch("/{alert_id}/status")
def update_alert_status(alert_id: str, payload: Dict[str, Any]):
    row = db.one("SELECT alert_id, entity_id, status FROM alerts WHERE alert_id = ?", [alert_id])
    if not row:
        raise HTTPException(404, f"alert {alert_id} not found")
    new_status = str(payload.get("status", "OPEN")).upper()
    if new_status not in STATUSES:
        raise HTTPException(422, f"status must be one of {sorted(STATUSES)}")
    assigned_to = payload.get("assigned_to")
    notes = payload.get("notes", "")

    if assigned_to:
        db.execute("UPDATE alerts SET status = ?, assigned_to = ? WHERE alert_id = ?", [new_status, assigned_to, alert_id])
    else:
        db.execute("UPDATE alerts SET status = ? WHERE alert_id = ?", [new_status, alert_id])

    # Analyst verdicts become labelled feedback for the next training run (roadmap S5)
    if new_status in FEEDBACK_LABEL:
        db.execute(
            "INSERT INTO feedback (id, alert_id, entity_id, user_label, notes) "
            "VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM feedback), ?, ?, ?, ?)",
            [alert_id, row["entity_id"], FEEDBACK_LABEL[new_status], notes],
        )
    db.audit("ALERT_STATUS", "ALERT", alert_id,
             {"from": row["status"], "to": new_status, "assigned_to": assigned_to, "notes": notes})
    return {"status": "success", "alert_id": alert_id, "new_status": new_status}
