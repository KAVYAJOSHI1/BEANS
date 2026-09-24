from pathlib import Path
from typing import Dict, Set
from beans.config import settings

# Snapshot offline threat lists
BULLETPROOF_ASNS = {"AS9009", "AS200052", "AS51852", "AS206980", "AS49870"}
TOR_EXIT_ASNS = {"AS13030", "AS208294", "AS60729", "AS200651"}
VPN_ASNS = {"AS9009", "AS200052", "AS39351", "AS212238"}
DATACENTER_ASNS = {"AS16509", "AS15169", "AS45102", "AS8560", "AS14061", "AS24940"}

class ASNClassifier:
    """
    Classifies ASNs into threat categories (BULLETPROOF, TOR_EXIT, VPN, DATACENTER, RESIDENTIAL).
    """

    @staticmethod
    def classify(asn_code: str) -> str:
        asn_clean = asn_code.upper().strip()
        if asn_clean in BULLETPROOF_ASNS:
            return "BULLETPROOF"
        if asn_clean in TOR_EXIT_ASNS:
            return "TOR_EXIT"
        if asn_clean in VPN_ASNS:
            return "VPN"
        if asn_clean in DATACENTER_ASNS:
            return "DATACENTER"
        return "RESIDENTIAL"
