import math
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Query

from beans.api import db
from beans.api.geo import locate
from beans.config import settings

router = APIRouter(prefix="/geomap", tags=["Geo Map"])


def _km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


@router.get("/origins")
def get_geomap_origins(max_arcs: int = Query(25, ge=1, le=200)) -> Dict[str, Any]:
    points = []
    for r in db.query("""
            SELECT src_ip AS ip, any_value(geo_country) AS country, any_value(geo_city) AS city,
                   any_value(geo_lat) AS lat, any_value(geo_lon) AS lon, any_value(asn) AS asn,
                   any_value(asn_name) AS asn_name, any_value(asn_type) AS asn_type, COUNT(*) AS tx_count
            FROM net_observations GROUP BY src_ip ORDER BY tx_count DESC LIMIT 2000"""):
        loc = locate(r["country"], r["lat"], r["lon"])
        if loc:
            points.append({**r, "lat": loc[0], "lon": loc[1],
                           "approximate": not (r["lat"] or r["lon"])})  # True = country centroid

    # Impossible travel: consecutive broadcasts of one wallet's spends from places further apart
    # than a plane could fly in the elapsed time (threshold: settings.IMPOSSIBLE_TRAVEL_KMH).
    by_wallet = defaultdict(list)
    for h in db.query("""
            SELECT unnest(input_addresses) AS wallet, timestamp AS ts, geo_country AS country, geo_city AS city,
                   geo_lat AS lat, geo_lon AS lon, src_ip
            FROM transactions WHERE src_ip IS NOT NULL"""):
        loc = locate(h["country"], h["lat"], h["lon"])
        if loc:
            by_wallet[h["wallet"]].append((h["ts"], loc, h))

    best: Dict[tuple, Dict[str, Any]] = {}
    for wallet, seq in by_wallet.items():
        seq.sort(key=lambda x: x[0])
        for (t0, l0, a), (t1, l1, b) in zip(seq, seq[1:]):
            if l0 == l1:
                continue
            km = _km(*l0, *l1)
            hours = max((datetime.fromisoformat(t1) - datetime.fromisoformat(t0)).total_seconds(), 60) / 3600
            speed = km / hours
            if speed < settings.IMPOSSIBLE_TRAVEL_KMH:
                continue
            key = (a["country"], b["country"])
            if key not in best or speed > best[key]["speed_kmh"]:
                best[key] = {
                    "wallet": wallet,
                    "from": {"city": a["city"], "country": a["country"], "lat": l0[0], "lon": l0[1], "ip": a["src_ip"]},
                    "to": {"city": b["city"], "country": b["country"], "lat": l1[0], "lon": l1[1], "ip": b["src_ip"]},
                    "distance_km": round(km, 1), "minutes": round(hours * 60, 1), "speed_kmh": round(speed, 1),
                    "is_impossible": True,
                    "label": f"{round(km):,} km in {round(hours * 60)} min ({round(speed):,} km/h)",
                }
    arcs = sorted(best.values(), key=lambda x: -x["speed_kmh"])[:max_arcs]
    return {"points": points, "arcs": arcs, "threshold_kmh": settings.IMPOSSIBLE_TRAVEL_KMH}
