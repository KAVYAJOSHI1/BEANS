"""Build the offline intel snapshots in data/intel/ (run once; only the Tor list needs internet).

  asn_types.csv   ASN -> infrastructure type (DATACENTER / VPN / BULLETPROOF / RESIDENTIAL), hand-curated
  tor_exits.csv   Tor exit IPs (snapshot of check.torproject.org/torbulkexitlist, dated)
  ip_pools.json   real IPv4 prefixes per ASN taken from the bundled DB-IP databases, so that synthetic
                  IPs geolocate and classify exactly like real traffic would
"""
import csv
import ipaddress
import json
import random
import sys
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

import maxminddb

ROOT = Path(__file__).resolve().parent.parent
INTEL, GEOIP = ROOT / "data" / "intel", ROOT / "data" / "geoip"

ASN_TYPES = {
    # cloud / hosting
    16509: ("DATACENTER", "Amazon AWS"), 14618: ("DATACENTER", "Amazon AES"), 15169: ("DATACENTER", "Google"),
    396982: ("DATACENTER", "Google Cloud"), 8075: ("DATACENTER", "Microsoft Azure"), 14061: ("DATACENTER", "DigitalOcean"),
    16276: ("DATACENTER", "OVH"), 24940: ("DATACENTER", "Hetzner"), 63949: ("DATACENTER", "Akamai Linode"),
    20473: ("DATACENTER", "Vultr / Choopa"), 51167: ("DATACENTER", "Contabo"), 12876: ("DATACENTER", "Scaleway"),
    45102: ("DATACENTER", "Alibaba Cloud"), 132203: ("DATACENTER", "Tencent Cloud"), 13335: ("DATACENTER", "Cloudflare"),
    # networks heavily used by commercial VPN providers
    9009: ("VPN", "M247"), 60068: ("VPN", "Datacamp / CDN77"), 212238: ("VPN", "Datacamp"),
    136787: ("VPN", "TEFINCOM (NordVPN)"), 39351: ("VPN", "31173 Services (Mullvad)"),
    # hosting frequently reported as abuse-tolerant ("bulletproof")
    202425: ("BULLETPROOF", "IP Volume"), 44477: ("BULLETPROOF", "Stark Industries"), 49981: ("BULLETPROOF", "WorldStream"),
    # residential / mobile ISPs
    55836: ("RESIDENTIAL", "Reliance Jio"), 24560: ("RESIDENTIAL", "Bharti Airtel"), 45609: ("RESIDENTIAL", "Bharti Airtel Mobile"),
    9829: ("RESIDENTIAL", "BSNL"), 7922: ("RESIDENTIAL", "Comcast"), 7018: ("RESIDENTIAL", "AT&T"), 701: ("RESIDENTIAL", "Verizon"),
    3320: ("RESIDENTIAL", "Deutsche Telekom"), 2856: ("RESIDENTIAL", "BT"), 4134: ("RESIDENTIAL", "China Telecom"),
    3215: ("RESIDENTIAL", "Orange"), 12389: ("RESIDENTIAL", "Rostelecom"), 5089: ("RESIDENTIAL", "Virgin Media"),
    17676: ("RESIDENTIAL", "SoftBank"), 4766: ("RESIDENTIAL", "Korea Telecom"), 28573: ("RESIDENTIAL", "Claro Brasil"),
    8151: ("RESIDENTIAL", "Telmex"),
}


def main(fetch_tor: bool = True) -> None:
    INTEL.mkdir(parents=True, exist_ok=True)
    with open(INTEL / "asn_types.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["asn", "type", "name"])
        for asn, (t, n) in sorted(ASN_TYPES.items()):
            w.writerow([asn, t, n])

    tor_path = INTEL / "tor_exits.csv"
    if fetch_tor:
        ips = urllib.request.urlopen("https://check.torproject.org/torbulkexitlist", timeout=30).read().decode().split()
        with open(tor_path, "w", newline="") as fh:
            fh.write(f"# Tor exit relays, snapshot {date.today().isoformat()} from check.torproject.org/torbulkexitlist\n")
            fh.write("ip\n" + "\n".join(sorted(set(ips), key=lambda x: tuple(int(p) for p in x.split(".")) if "." in x else (999,))) + "\n")

    rng = random.Random(7)
    asn_db = maxminddb.open_database(str(GEOIP / "dbip-asn-lite.mmdb"))
    country_db = maxminddb.open_database(str(GEOIP / "dbip-country-lite.mmdb"))
    nets = defaultdict(list)
    for net, rec in asn_db:
        a = rec.get("autonomous_system_number")
        if a in ASN_TYPES and net.version == 4 and 16 <= net.prefixlen <= 24:
            nets[a].append(net)
    pools = {}
    for a, lst in nets.items():
        chosen = rng.sample(lst, min(40, len(lst)))
        entries = []
        for n in chosen:
            c = country_db.get(str(n.network_address + 1)) or {}
            entries.append([str(n), c.get("country", {}).get("iso_code", "XX")])
        pools[str(a)] = {"type": ASN_TYPES[a][0], "name": ASN_TYPES[a][1], "prefixes": entries}
    tor = [l.strip() for l in open(tor_path) if l.strip() and not l.startswith("#") and l.strip() != "ip"]
    pools["TOR"] = {"type": "TOR_EXIT", "name": "Tor exit relays", "ips": [ip for ip in tor if "." in ip][:400]}
    (INTEL / "ip_pools.json").write_text(json.dumps(pools, indent=1))
    print(f"asn_types: {len(ASN_TYPES)}  pools: {len(pools)}  tor exits: {len(tor)}")


if __name__ == "__main__":
    main(fetch_tor="--no-tor" not in sys.argv)
