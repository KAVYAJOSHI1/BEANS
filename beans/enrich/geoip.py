import ipaddress
from pathlib import Path
from typing import Dict, Any, Optional
from beans.config import settings

# Built-in offline IP geolocation reference dataset for demo/offline resilience
BUILTIN_OFFLINE_GEOIP = {
    "185.220.101.0/24": {"country": "NL", "city": "Rotterdam", "lat": 51.9244, "lon": 4.4777, "asn": "AS9009", "asn_name": "Bulletproof Hosting BV", "type": "BULLETPROOF"},
    "194.26.29.0/24": {"country": "PA", "city": "Panama City", "lat": 8.9824, "lon": -79.5199, "asn": "AS200052", "asn_name": "Panama Secure VPN", "type": "VPN"},
    "103.245.236.0/24": {"country": "HK", "city": "Hong Kong", "lat": 22.3193, "lon": 114.1694, "asn": "AS45102", "asn_name": "Alibaba Cloud Datacenter", "type": "DATACENTER"},
    "52.128.40.0/24": {"country": "US", "city": "Seattle", "lat": 47.6062, "lon": -122.3321, "asn": "AS16509", "asn_name": "Amazon AWS Cloud", "type": "DATACENTER"},
    "198.51.100.0/24": {"country": "CH", "city": "Zurich", "lat": 47.3769, "lon": 8.5417, "asn": "AS13030", "asn_name": "Swiss Privacy Gateway", "type": "TOR_EXIT"},
    "82.165.197.0/24": {"country": "DE", "city": "Berlin", "lat": 52.5200, "lon": 13.4050, "asn": "AS8560", "asn_name": "IONOS SE", "type": "DATACENTER"},
    "142.250.190.0/24": {"country": "US", "city": "Mountain View", "lat": 37.4220, "lon": -122.0841, "asn": "AS15169", "asn_name": "Google LLC", "type": "DATACENTER"},
    "24.120.0.0/16": {"country": "US", "city": "New York", "lat": 40.7128, "lon": -74.0060, "asn": "AS7018", "asn_name": "AT&T Residential", "type": "RESIDENTIAL"},
    "86.128.0.0/16": {"country": "GB", "city": "London", "lat": 51.5074, "lon": -0.1278, "asn": "AS2856", "asn_name": "BT Broadband Residential", "type": "RESIDENTIAL"},
    "106.51.0.0/16": {"country": "IN", "city": "Bengaluru", "lat": 12.9716, "lon": 77.5946, "asn": "AS24560", "asn_name": "Bharti Airtel Residential", "type": "RESIDENTIAL"}
}

class OfflineGeoIPEnricher:
    """
    Enriches IP addresses with Country, City, Coordinates, and ASN using DB-IP Lite or offline subnet tables.
    """

    def __init__(self, mmdb_path: Optional[Path] = None):
        self.reader = None
        target = mmdb_path or (settings.GEOIP_DIR / "dbip-country-lite.mmdb")
        if target.exists():
            try:
                import maxminddb
                self.reader = maxminddb.open_database(str(target))
            except Exception:
                self.reader = None

    def enrich(self, ip_str: str) -> Dict[str, Any]:
        """Returns { country, city, lat, lon, asn, asn_name, isp_type }"""
        ip_clean = ip_str.strip()
        
        # 1. Try DB-IP mmdb if available
        if self.reader:
            try:
                rec = self.reader.get(ip_clean)
                if rec:
                    country = rec.get("country", {}).get("iso_code", "XX")
                    return {
                        "country": country,
                        "city": rec.get("city", {}).get("names", {}).get("en", "Unknown"),
                        "lat": float(rec.get("location", {}).get("latitude", 0.0)),
                        "lon": float(rec.get("location", {}).get("longitude", 0.0)),
                        "asn": rec.get("traits", {}).get("autonomous_system_number", "AS_UNKNOWN"),
                        "asn_name": rec.get("traits", {}).get("autonomous_system_organization", "Unknown"),
                        "isp_type": "RESIDENTIAL"
                    }
            except Exception:
                pass

        # 2. Match against built-in subnet database
        try:
            ip_obj = ipaddress.ip_address(ip_clean)
            for subnet, meta in BUILTIN_OFFLINE_GEOIP.items():
                if ip_obj in ipaddress.ip_network(subnet):
                    return {
                        "country": meta["country"],
                        "city": meta["city"],
                        "lat": meta["lat"],
                        "lon": meta["lon"],
                        "asn": meta["asn"],
                        "asn_name": meta["asn_name"],
                        "isp_type": meta["type"]
                    }
        except Exception:
            pass

        # 3. Default fallback
        return {
            "country": "XX",
            "city": "Unknown",
            "lat": 0.0,
            "lon": 0.0,
            "asn": "AS_UNKNOWN",
            "asn_name": "Unknown Network",
            "isp_type": "RESIDENTIAL"
        }
