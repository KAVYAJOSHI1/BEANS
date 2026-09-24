from fastapi import APIRouter
from typing import Dict, Any, List
from beans.store.duck import DuckStore

router = APIRouter(prefix="/geomap", tags=["Geo Map"])

@router.get("/origins")
def get_geomap_origins() -> Dict[str, Any]:
    store = DuckStore()
    conn = store.get_connection()

    points_df = conn.execute("""
    SELECT src_ip, geo_country, geo_city, geo_lat, geo_lon, asn, asn_name, asn_type, COUNT(*) as tx_count
    FROM net_observations
    WHERE geo_lat != 0.0 AND geo_lon != 0.0
    GROUP BY src_ip, geo_country, geo_city, geo_lat, geo_lon, asn, asn_name, asn_type
    """).fetchdf()

    points = []
    for r in points_df.to_dict(orient="records"):
        points.append({
            "ip": r["src_ip"],
            "country": r["geo_country"],
            "city": r["geo_city"],
            "lat": float(r["geo_lat"]),
            "lon": float(r["geo_lon"]),
            "asn": r["asn"],
            "asn_name": r["asn_name"],
            "asn_type": r["asn_type"],
            "tx_count": int(r["tx_count"])
        })

    # Sample arcs (impossible travel pairs)
    arcs = [
        {
            "from": {"city": "Rotterdam", "lat": 51.9244, "lon": 4.4777, "country": "NL"},
            "to": {"city": "Hong Kong", "lat": 22.3193, "lon": 114.1694, "country": "HK"},
            "speed_kmh": 1420.0,
            "is_impossible": True,
            "label": "Impossible Travel (1,420 km/h)"
        },
        {
            "from": {"city": "Panama City", "lat": 8.9824, "lon": -79.5199, "country": "PA"},
            "to": {"city": "Zurich", "lat": 47.3769, "lon": 8.5417, "country": "CH"},
            "speed_kmh": 1180.0,
            "is_impossible": True,
            "label": "VPN Hopping (1,180 km/h)"
        }
    ]

    conn.close()

    return {
        "points": points,
        "arcs": arcs
    }
