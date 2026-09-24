import math
from datetime import datetime
from typing import Tuple, Dict, Any

EARTH_RADIUS_KM = 6371.0

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees) using Haversine formula.
    """
    if lat1 == lat2 and lon1 == lon2:
        return 0.0
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return EARTH_RADIUS_KM * c

def calculate_geo_velocity(
    loc1: Dict[str, Any], 
    loc2: Dict[str, Any], 
    t1: datetime, 
    t2: datetime
) -> Tuple[float, float, bool]:
    """
    Calculate travel distance in KM, travel speed in KM/H between two network observations.
    Returns (distance_km, speed_kmh, is_impossible_travel)
    """
    delta_seconds = abs((t2 - t1).total_seconds())
    if delta_seconds <= 0:
        delta_seconds = 1.0  # Avoid division by zero
    
    delta_hours = delta_seconds / 3600.0
    
    lat1, lon1 = float(loc1.get("lat", 0.0)), float(loc1.get("lon", 0.0))
    lat2, lon2 = float(loc2.get("lat", 0.0)), float(loc2.get("lon", 0.0))
    
    # If both locations are default coordinates, distance cannot be accurately computed
    if (lat1 == 0.0 and lon1 == 0.0) or (lat2 == 0.0 and lon2 == 0.0):
        return 0.0, 0.0, False
    
    dist_km = haversine_distance_km(lat1, lon1, lat2, lon2)
    speed_kmh = dist_km / delta_hours
    
    # Threshold for commercial flight speed (~900 km/h)
    is_impossible = speed_kmh > 900.0 and dist_km > 500.0
    
    return round(dist_km, 2), round(speed_kmh, 2), is_impossible
