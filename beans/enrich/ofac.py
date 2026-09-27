"""Real seeds for real data: Bitcoin addresses on the US Treasury OFAC SDN list.

The SDN list (Specially Designated Nationals) names sanctioned people and organisations; since 2018 many entries
carry "Digital Currency Address - XBT" identifiers (e.g. Lazarus Group, Garantex, Hydra, ransomware operators).
Loading them as seeds gives the E4 risk propagation real, citable starting points on live or bulk real data.

Only the official export is used (sdn.xml from treasury.gov), never a third-party copy, so each seed cites the list's
publish date and the file's SHA-256. Download it on a connected machine and carry it over, or use --download.
A sanctioned address is a legal fact about who controls it, not proof that a transacting counterparty is criminal:
the propagated risk says "funds are close to a sanctioned actor", which is what the investigator then checks.
"""
import hashlib
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List

from beans.config import settings

SDN_URL = "https://www.treasury.gov/ofac/downloads/sdn.xml"
DEFAULT_FILE = settings.INTEL_DIR / "ofac_sdn.xml"
ID_TYPE = "Digital Currency Address - XBT"


def download(dest: Path = DEFAULT_FILE, url: str = SDN_URL) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "BEANS/1.0 (sanctions screening)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if b"<sdnList" not in data[:2000]:
        raise ValueError("the download is not an OFAC sdn.xml file")
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return dest


def parse(path: Path) -> Dict:
    """{"publish_date", "sha256", "entries": [{"address", "name", "sdn_type", "programs", "uid"}]}"""
    raw = Path(path).read_bytes()
    root = ET.fromstring(raw)
    ns = root.tag[:root.tag.index("}") + 1] if root.tag.startswith("{") else ""
    q = lambda el, tag: el.find(ns + tag)  # noqa: E731
    publish = q(root, "publshInformation")
    date = publish.findtext(ns + "Publish_Date") if publish is not None else None
    entries: List[dict] = []
    for e in root.iter(ns + "sdnEntry"):
        ids = q(e, "idList")
        if ids is None:
            continue
        addrs = [i.findtext(ns + "idNumber", "").strip() for i in ids.iter(ns + "id")
                 if i.findtext(ns + "idType", "").strip() == ID_TYPE]
        if not addrs:
            continue
        name = " ".join(x for x in (e.findtext(ns + "firstName"), e.findtext(ns + "lastName")) if x).strip()
        programs = [p.text for p in e.iter(ns + "program") if p.text]
        for a in addrs:
            if a:
                entries.append({"address": a, "name": name, "sdn_type": e.findtext(ns + "sdnType"),
                                "programs": programs, "uid": e.findtext(ns + "uid")})
    return {"publish_date": date, "sha256": hashlib.sha256(raw).hexdigest(), "entries": entries}


def load_seeds(conn, parsed: Dict) -> int:
    """Insert (or refresh) every sanctioned XBT address as a seed; returns the number of addresses."""
    src = f"OFAC SDN list {parsed['publish_date']} (sha256 {parsed['sha256'][:16]}…)"
    first = {}
    for e in parsed["entries"]:          # an address listed under two entries keeps the first
        first.setdefault(e["address"], e)
    rows = [(a, "SANCTIONED", f"OFAC SDN #{e['uid']}: {e['name']} [{', '.join(e['programs'])}]", 1.0, src)
            for a, e in first.items()]
    conn.executemany("INSERT OR REPLACE INTO seeds (address, threat_type, incident_name, confidence, source) "
                     "VALUES (?, ?, ?, ?, ?)", rows)
    return len(rows)
