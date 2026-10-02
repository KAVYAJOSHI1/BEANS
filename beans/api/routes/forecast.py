"""Cash-out forecast (E7): wallets that still hold coins, ordered by how soon they are expected to reach an exchange."""
from typing import Any, Dict, List

from fastapi import APIRouter

from beans.api import db

router = APIRouter(prefix="/forecast", tags=["Cash-out forecast"])

STATE_ORDER = {"IN_WINDOW": 0, "OVERDUE": 1, "EXPECTED_LATER": 2}


@router.get("")
def interdiction_queue() -> Dict[str, Any]:
    """Pending forecasts, most urgent first: in the expected window, then overdue, then by time to window start."""
    rows = db.query("SELECT alert_id, entity_id, alert_type, risk_score, severity, evidence FROM alerts")
    pending: List[Dict[str, Any]] = []
    for r in rows:
        fc = (r["evidence"] or {}).get("cashout_forecast") or {}
        if fc.get("status") == "PENDING" and fc.get("window"):
            pending.append({"alert_id": r["alert_id"], "entity_id": r["entity_id"], "alert_type": r["alert_type"],
                            "risk_score": r["risk_score"], "severity": r["severity"], **fc})
    pending.sort(key=lambda x: (STATE_ORDER.get(x["window"]["state"], 9), -x["risk_score"],
                                x["window"]["minutes_to_window_start"]))
    return {"pending": pending, "count": len(pending)}
