"""Infrastructure type for an IP/ASN from offline snapshots in data/intel/ (see scripts/build_intel.py)."""
import csv
from functools import lru_cache
from typing import Optional

from beans.config import settings

TYPES = {"RESIDENTIAL", "DATACENTER", "VPN", "TOR_EXIT", "BULLETPROOF", "UNKNOWN"}


@lru_cache(maxsize=1)
def _asn_types() -> dict:
    path = settings.INTEL_DIR / "asn_types.csv"
    if not path.exists():
        return {}
    with open(path, newline="") as fh:
        return {int(r["asn"]): r["type"] for r in csv.DictReader(fh)}


@lru_cache(maxsize=1)
def _tor_exits() -> frozenset:
    path = settings.INTEL_DIR / "tor_exits.csv"
    if not path.exists():
        return frozenset()
    return frozenset(l.strip() for l in open(path) if l.strip() and not l.startswith("#") and l.strip() != "ip")


def _asn_number(asn) -> Optional[int]:
    if asn is None:
        return None
    s = str(asn).upper().removeprefix("AS").strip()
    return int(s) if s.isdigit() else None


class ASNClassifier:
    @staticmethod
    def classify(asn, ip: Optional[str] = None) -> str:
        """TOR_EXIT if the IP is a known exit, else the ASN's type, else RESIDENTIAL for known ISPs / UNKNOWN."""
        if ip and ip in _tor_exits():
            return "TOR_EXIT"
        n = _asn_number(asn)
        if n is None:
            return "UNKNOWN"
        return _asn_types().get(n, "UNKNOWN")
