from fastapi import APIRouter
from typing import Dict, Any
from beans.store.duck import DuckStore

router = APIRouter(prefix="/stats", tags=["Statistics & KPIs"])

@router.get("/overview")
def get_system_overview() -> Dict[str, Any]:
    store = DuckStore()
    conn = store.get_connection()

    tx_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    alert_count = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    critical_count = conn.execute("SELECT COUNT(*) FROM alerts WHERE severity = 'CRITICAL'").fetchone()[0]
    high_count = conn.execute("SELECT COUNT(*) FROM alerts WHERE severity = 'HIGH'").fetchone()[0]
    med_count = conn.execute("SELECT COUNT(*) FROM alerts WHERE severity = 'MEDIUM'").fetchone()[0]
    low_count = conn.execute("SELECT COUNT(*) FROM alerts WHERE severity = 'LOW'").fetchone()[0]

    tot_volume = conn.execute("SELECT COALESCE(SUM(total_output), 0) FROM transactions").fetchone()[0]
    wallet_count = conn.execute("SELECT COUNT(*) FROM wallet_profiles").fetchone()[0]
    seed_count = conn.execute("SELECT COUNT(*) FROM seeds").fetchone()[0]

    # Typology distribution
    typology_rows = conn.execute("""
    SELECT alert_type, COUNT(*) as cnt 
    FROM alerts 
    GROUP BY alert_type 
    ORDER BY cnt DESC
    """).fetchall()

    typology_dist = [{"name": r[0].replace("_PATTERN", ""), "value": r[1]} for r in typology_rows]

    # Top countries
    country_rows = conn.execute("""
    SELECT geo_country, COUNT(*) as cnt 
    FROM net_observations 
    GROUP BY geo_country 
    ORDER BY cnt DESC LIMIT 5
    """).fetchall()
    top_countries = [{"country": r[0], "count": r[1]} for r in country_rows]

    conn.close()

    return {
        "kpis": {
            "total_transactions": tx_count,
            "total_volume_btc": round(tot_volume, 4),
            "total_wallets": wallet_count,
            "total_alerts": alert_count,
            "critical_alerts": critical_count,
            "high_alerts": high_count,
            "medium_alerts": med_count,
            "low_alerts": low_count,
            "active_seeds": seed_count
        },
        "typology_distribution": typology_dist,
        "top_countries": top_countries
    }
