from fastapi import APIRouter, Query, HTTPException
from typing import List, Dict, Any, Optional
import json
from beans.store.duck import DuckStore

router = APIRouter(prefix="/alerts", tags=["Alerts"])

@router.get("")
def get_ranked_alerts(
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500)
) -> List[Dict[str, Any]]:
    store = DuckStore()
    conn = store.get_connection()

    sql = "SELECT * FROM alerts WHERE 1=1"
    params = []

    if severity and severity != "ALL":
        sql += " AND severity = ?"
        params.append(severity)
    if status and status != "ALL":
        sql += " AND status = ?"
        params.append(status)
    if q:
        sql += " AND (entity_id ILIKE ? OR alert_type ILIKE ?)"
        params.extend([f"%{q}%", f"%{q}%"])

    sql += " ORDER BY risk_score DESC, created_at DESC LIMIT ?"
    params.append(limit)

    df = conn.execute(sql, params).fetchdf()
    conn.close()

    results = []
    for row in df.to_dict(orient="records"):
        # parse json fields if string
        shap_feats = row.get("shap_top_features")
        if isinstance(shap_feats, str):
            try:
                shap_feats = json.loads(shap_feats)
            except Exception:
                shap_feats = []

        engine_sc = row.get("engine_scores")
        if isinstance(engine_sc, str):
            try:
                engine_sc = json.loads(engine_sc)
            except Exception:
                engine_sc = {}

        evidence = row.get("evidence")
        if isinstance(evidence, str):
            try:
                evidence = json.loads(evidence)
            except Exception:
                evidence = {}

        results.append({
            "alert_id": row.get("alert_id"),
            "entity_id": row.get("entity_id"),
            "entity_type": row.get("entity_type"),
            "alert_type": row.get("alert_type"),
            "risk_score": float(row.get("risk_score", 0.0)),
            "calibrated_confidence": float(row.get("calibrated_confidence", 0.0)),
            "severity": row.get("severity"),
            "reasons": row.get("reasons") if isinstance(row.get("reasons"), list) else [],
            "shap_top_features": shap_feats,
            "engine_scores": engine_sc,
            "evidence": evidence,
            "status": row.get("status", "OPEN"),
            "assigned_to": row.get("assigned_to", "Unassigned"),
            "created_at": str(row.get("created_at"))
        })

    return results

@router.patch("/{alert_id}/status")
def update_alert_status(alert_id: str, payload: Dict[str, Any]):
    store = DuckStore()
    conn = store.get_connection()
    new_status = payload.get("status", "OPEN")
    assigned_to = payload.get("assigned_to")

    if assigned_to:
        conn.execute("UPDATE alerts SET status = ?, assigned_to = ? WHERE alert_id = ?", [new_status, assigned_to, alert_id])
    else:
        conn.execute("UPDATE alerts SET status = ? WHERE alert_id = ?", [new_status, alert_id])

    # Log feedback if false positive
    if new_status == "FALSE_POSITIVE":
        conn.execute("INSERT INTO feedback (alert_id, user_label, notes) VALUES (?, ?, ?)", [
            alert_id, "FALSE_POSITIVE", payload.get("notes", "Marked FP by analyst")
        ])

    conn.close()
    return {"status": "success", "alert_id": alert_id, "new_status": new_status}
