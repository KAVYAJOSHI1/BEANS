"""Global search (Ctrl+K): one box for wallets, transactions, IPs, alerts, clusters and cases."""
from typing import Any, Dict, List

from fastapi import APIRouter, Query

from beans.api import db

router = APIRouter(tags=["Search"])


@router.get("/search")
def search(q: str = Query(..., min_length=2, max_length=128), limit: int = Query(6, ge=1, le=25)) -> Dict[str, List[Dict[str, Any]]]:
    s = q.strip()
    pre, sub = f"{s}%", f"%{s}%"
    out: Dict[str, List[Dict[str, Any]]] = {}
    if db.table_exists("wallet_scores"):
        out["wallets"] = db.query("""SELECT w.address AS id, round(100 * w.p, 1) AS risk, w.cluster_id, a.alert_id
                                     FROM wallet_scores w LEFT JOIN alerts a ON a.entity_id = w.address
                                     WHERE w.address ILIKE ? ORDER BY w.p DESC LIMIT ?""", [pre, limit])
        out["clusters"] = db.query("""SELECT cluster_id AS id, COUNT(*) AS wallets, round(100 * max(p), 1) AS max_risk,
                                             arg_max(address, p) AS top_wallet
                                      FROM wallet_scores WHERE cluster_id ILIKE ? GROUP BY 1 ORDER BY 3 DESC LIMIT ?""",
                                   [pre, limit])
    out["transactions"] = db.query("SELECT txid AS id, timestamp, total_output FROM transactions WHERE txid ILIKE ? "
                                   "ORDER BY timestamp DESC LIMIT ?", [pre, limit])
    out["ips"] = db.query("""SELECT src_ip AS id, any_value(geo_country) AS country, any_value(asn_type) AS asn_type,
                                    COUNT(*) AS observations FROM net_observations WHERE src_ip LIKE ?
                             GROUP BY src_ip ORDER BY observations DESC LIMIT ?""", [pre, limit])
    out["alerts"] = db.query("""SELECT alert_id AS id, entity_id, alert_type, risk_score, severity FROM alerts
                                WHERE alert_id ILIKE ? OR alert_type ILIKE ? ORDER BY risk_score DESC LIMIT ?""",
                             [pre, sub, limit])
    out["cases"] = db.query("""SELECT id, case_name, status, priority FROM case_files
                               WHERE case_name ILIKE ? OR CAST(id AS VARCHAR) = ? OR notes ILIKE ?
                                  OR list_contains(suspect_entities, ?) ORDER BY updated_at DESC LIMIT ?""",
                            [sub, s, sub, s, limit]) if db.table_exists("case_files") else []
    return {k: v for k, v in out.items() if v}
