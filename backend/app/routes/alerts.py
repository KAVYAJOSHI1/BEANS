from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import json
from datetime import datetime

from backend.app.db.database import get_db
from backend.app.models.schema import Alert, AuditLog
from backend.app.schemas.pydantic_schemas import AlertResponse, AlertStatusUpdate

router = APIRouter(prefix="/alerts", tags=["Alerts"])

@router.get("", response_model=List[AlertResponse])
def get_alerts(
    status: Optional[str] = Query(None, description="Filter by status: OPEN, INVESTIGATING, RESOLVED, FALSE_POSITIVE"),
    severity: Optional[str] = Query(None, description="Filter by severity: CRITICAL, HIGH, MEDIUM, LOW"),
    min_score: Optional[float] = Query(0.0, description="Minimum risk score"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(Alert)
    if status and status != "ALL":
        query = query.filter(Alert.status == status)
    if severity and severity != "ALL":
        query = query.filter(Alert.severity == severity)
    if min_score > 0:
        query = query.filter(Alert.automated_score >= min_score)

    alerts = query.order_by(Alert.automated_score.desc(), Alert.created_at.desc()).limit(limit).all()

    return [
        AlertResponse(
            id=a.id,
            entity_type=a.entity_type,
            entity_id=a.entity_id,
            alert_type=a.alert_type,
            severity=a.severity,
            reason=a.reason,
            evidence_breakdown=a.get_evidence(),
            score_components=a.get_score_components(),
            automated_score=float(a.automated_score or 0.0),
            investigator_confidence=float(a.investigator_confidence or 0.0),
            status=a.status,
            assigned_to=a.assigned_to or "Unassigned",
            created_at=a.created_at
        )
        for a in alerts
    ]

@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert_by_id(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertResponse(
        id=alert.id,
        entity_type=alert.entity_type,
        entity_id=alert.entity_id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        reason=alert.reason,
        evidence_breakdown=alert.get_evidence(),
        score_components=alert.get_score_components(),
        automated_score=float(alert.automated_score or 0.0),
        investigator_confidence=float(alert.investigator_confidence or 0.0),
        status=alert.status,
        assigned_to=alert.assigned_to or "Unassigned",
        created_at=alert.created_at
    )

@router.patch("/{alert_id}/status")
def update_alert_status(
    alert_id: int,
    payload: AlertStatusUpdate,
    db: Session = Depends(get_db)
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    old_status = alert.status
    alert.status = payload.status
    if payload.investigator_confidence is not None:
        alert.investigator_confidence = payload.investigator_confidence
    if payload.assigned_to is not None:
        alert.assigned_to = payload.assigned_to

    alert.updated_at = datetime.utcnow()

    # Log audit trail
    db.add(AuditLog(
        action="UPDATE_ALERT_STATUS",
        investigator=payload.assigned_to or "Analyst",
        entity_type=alert.entity_type,
        entity_id=alert.entity_id,
        details=json.dumps({"alert_id": alert.id, "old_status": old_status, "new_status": payload.status, "notes": payload.notes})
    ))
    db.commit()

    return {"status": "success", "alert_id": alert.id, "new_status": alert.status}
