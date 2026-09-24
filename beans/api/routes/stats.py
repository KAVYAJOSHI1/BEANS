from typing import Any, Dict

from fastapi import APIRouter

from beans.api import db

router = APIRouter(prefix="/stats", tags=["Statistics & KPIs"])


@router.get("/overview")
def get_system_overview() -> Dict[str, Any]:
    sev = {r["severity"]: r["n"] for r in db.query("SELECT severity, COUNT(*) AS n FROM alerts GROUP BY 1")}
    kpis = {
        "total_transactions": db.scalar("SELECT COUNT(*) FROM transactions"),
        "total_observations": db.scalar("SELECT COUNT(*) FROM net_observations"),
        "total_volume_btc": round(db.scalar("SELECT COALESCE(SUM(total_output), 0) FROM transactions"), 4),
        "total_wallets": db.scalar("SELECT COUNT(*) FROM wallet_profiles"),
        "total_ips": db.scalar("SELECT COUNT(DISTINCT src_ip) FROM net_observations"),
        "total_clusters": db.scalar("SELECT COUNT(DISTINCT cluster_id) FROM wallet_profiles WHERE cluster_id IS NOT NULL"),
        "total_alerts": sum(sev.values()),
        "critical_alerts": sev.get("CRITICAL", 0),
        "high_alerts": sev.get("HIGH", 0),
        "medium_alerts": sev.get("MEDIUM", 0),
        "low_alerts": sev.get("LOW", 0),
        "open_alerts": db.scalar("SELECT COUNT(*) FROM alerts WHERE status = 'OPEN'"),
        "active_seeds": db.scalar("SELECT COUNT(*) FROM seeds"),
    }
    typology = [{"name": r["alert_type"].replace("_PATTERN", ""), "value": r["n"]}
                for r in db.query("SELECT alert_type, COUNT(*) AS n FROM alerts GROUP BY 1 ORDER BY 2 DESC")]
    countries = [{"country": r["geo_country"], "count": r["n"]} for r in db.query(
        "SELECT geo_country, COUNT(*) AS n FROM net_observations GROUP BY 1 ORDER BY 2 DESC LIMIT 8")]
    asn_types = [{"asn_type": r["asn_type"], "count": r["n"]} for r in db.query(
        "SELECT asn_type, COUNT(*) AS n FROM net_observations GROUP BY 1 ORDER BY 2 DESC")]
    activity = [{"hour": r["h"], "transactions": r["n"], "volume_btc": round(r["v"], 4)} for r in db.query(
        "SELECT strftime(date_trunc('hour', timestamp), '%Y-%m-%d %H:00') AS h, COUNT(*) AS n, SUM(total_output) AS v "
        "FROM transactions GROUP BY 1 ORDER BY 1")]
    return {"kpis": kpis, "typology_distribution": typology, "top_countries": countries,
            "asn_types": asn_types, "activity": activity}
