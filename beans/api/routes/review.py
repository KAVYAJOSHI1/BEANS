"""Review queue (active learning): the cases where an analyst's verdict teaches the model the most.

Two lists:
  * uncertain alerts: open alerts, most uncertain first. Uncertainty = closeness of the fused probability to 0.5
    (60 %) and low calibrated confidence, i.e. engines disagreeing or evidence missing (40 %).
  * near misses: wallets that scored just under the alert threshold. A missed criminal hides here.

Verdicts go into the same `feedback` table the alert status buttons use; the next scoring run (`beans score`, or
"Re-run with seeds") trains on them, so every verdict on this list moves the model where it is weakest.
"""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from beans.api import db
from beans.config import settings

router = APIRouter(prefix="/review", tags=["Review queue"])

NEAR_MISS_MIN = 0.20          # wallets from this probability up to the alert threshold are near misses
LABELS = {"TRUE_POSITIVE", "FALSE_POSITIVE"}


def _uncertainty(p: float, confidence: float) -> float:
    return round(0.6 * (1 - abs(2 * p - 1)) + 0.4 * (1 - confidence), 4)


@router.get("/queue")
def queue(limit: int = Query(25, ge=1, le=200)) -> Dict[str, Any]:
    judged = "SELECT entity_id FROM feedback WHERE entity_id IS NOT NULL"
    alerts = db.query(f"""SELECT alert_id, entity_id, alert_type, risk_score, severity, calibrated_confidence, reasons,
                                 CAST(json_extract(engine_scores, '$.fused_probability') AS DOUBLE) AS p,
                                 json_extract_string(recommended_action, '$.action') AS action, status
                          FROM alerts WHERE status IN ('OPEN', 'INVESTIGATING') AND entity_id NOT IN ({judged})""")
    for a in alerts:
        p, c = float(a["p"] if a["p"] is not None else a["risk_score"] / 100), float(a["calibrated_confidence"] or 0)
        a["uncertainty"] = _uncertainty(p, c)
        why = []
        if abs(p - 0.5) <= 0.15:
            why.append(f"model is undecided (P = {p:.2f})")
        if c < 0.5:
            why.append(f"low confidence {c:.2f}: engines disagree or evidence is missing")
        a["why_review"] = why or [f"P = {p:.2f}, confidence {c:.2f}"]
    alerts.sort(key=lambda a: -a["uncertainty"])

    near = []
    if db.table_exists("wallet_scores"):
        near = db.query(f"""SELECT address, p, typology_pred, anomaly, taint, hops_to_seed, cluster_id, max_p_peel,
                                   max_p_coinjoin, share_risky_asn
                            FROM wallet_scores WHERE p >= ? AND p < ?
                              AND address NOT IN (SELECT entity_id FROM alerts)
                              AND address NOT IN ({judged})
                            ORDER BY p DESC LIMIT ?""", [NEAR_MISS_MIN, settings.ALERT_MIN_PROBABILITY, limit])
        for w in near:
            why = [f"P = {w['p']:.2f}, just under the alert threshold {settings.ALERT_MIN_PROBABILITY:.2f}"]
            if (w["anomaly"] or 0) > 0.9:
                why.append(f"more unusual than {100 * w['anomaly']:.0f} % of wallets")
            hops = int(w["hops_to_seed"] if w["hops_to_seed"] is not None else 99)
            if hops <= 4:
                why.append(f"{hops} hop(s) from a seed wallet")
            elif (w["taint"] or 0) >= 0.001:
                why.append(f"receives tainted funds (taint {w['taint']:.3f})")
            if (w["share_risky_asn"] or 0) > 0:
                why.append("broadcast through risky infrastructure")
            w["why_review"] = why
    verdicts = db.scalar("SELECT COUNT(DISTINCT entity_id) FROM feedback WHERE entity_id IS NOT NULL") or 0
    return {"uncertain_alerts": alerts[:limit], "near_misses": near, "verdicts_so_far": int(verdicts),
            "alert_threshold": settings.ALERT_MIN_PROBABILITY, "near_miss_min": NEAR_MISS_MIN}


@router.post("/verdict")
def verdict(payload: Dict[str, Any]):
    """Verdict on any wallet (alerted or not): TRUE_POSITIVE (illicit) or FALSE_POSITIVE (legitimate)."""
    entity = str(payload.get("entity_id") or "").strip()
    label = str(payload.get("label") or "").upper()
    if not entity or label not in LABELS:
        raise HTTPException(422, f"entity_id and label ({' / '.join(sorted(LABELS))}) are required")
    if not db.scalar("SELECT COUNT(*) FROM wallet_scores WHERE address = ?", [entity]):
        raise HTTPException(404, f"wallet {entity} is not in the scored data")
    alert_id = db.scalar("SELECT alert_id FROM alerts WHERE entity_id = ?", [entity])
    db.execute("INSERT INTO feedback (id, alert_id, entity_id, user_label, notes) "
               "VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM feedback), ?, ?, ?, ?)",
               [alert_id, entity, label, str(payload.get("notes") or "")])
    if alert_id:   # keep the alert's status in step with the verdict
        db.execute("UPDATE alerts SET status = ? WHERE alert_id = ?",
                   ["CONFIRMED" if label == "TRUE_POSITIVE" else "FALSE_POSITIVE", alert_id])
    db.audit("REVIEW_VERDICT", "WALLET", entity, {"label": label, "alert_id": alert_id, "notes": payload.get("notes")})
    return {"status": "success", "entity_id": entity, "label": label, "alert_id": alert_id}
