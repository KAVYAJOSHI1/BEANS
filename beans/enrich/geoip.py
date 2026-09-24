"""Offline IP enrichment from the bundled DB-IP Lite databases (country + ASN, CC BY 4.0)."""
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from beans.api.geo import CENTROIDS
from beans.config import settings
from beans.enrich.asn_classifier import ASNClassifier


def _open(path: Path):
    if not path.exists():
        return None
    try:
        import maxminddb
        return maxminddb.open_database(str(path))
    except Exception:
        return None


class OfflineGeoIPEnricher:
    """IP -> country, approximate coordinates (country centroid), ASN number/org, infrastructure type."""

    def __init__(self, country_mmdb: Optional[Path] = None, asn_mmdb: Optional[Path] = None):
        self.country_db = _open(country_mmdb or settings.GEOIP_DIR / "dbip-country-lite.mmdb")
        self.asn_db = _open(asn_mmdb or settings.GEOIP_DIR / "dbip-asn-lite.mmdb")
        self.enrich = lru_cache(maxsize=200_000)(self._enrich)

    def _enrich(self, ip_str: str) -> Dict[str, Any]:
        ip = (ip_str or "").strip()
        country, asn, asn_name = "XX", "AS_UNKNOWN", "Unknown"
        try:
            if self.country_db and (rec := self.country_db.get(ip)):
                country = rec.get("country", {}).get("iso_code") or "XX"
            if self.asn_db and (rec := self.asn_db.get(ip)):
                if rec.get("autonomous_system_number"):
                    asn = f"AS{rec['autonomous_system_number']}"
                asn_name = rec.get("autonomous_system_organization") or "Unknown"
        except ValueError:  # not an IP address
            pass
        lat, lon = CENTROIDS.get(country, (0.0, 0.0))
        return {"country": country, "city": "", "lat": lat, "lon": lon, "asn": asn, "asn_name": asn_name,
                "asn_type": ASNClassifier.classify(asn, ip)}
