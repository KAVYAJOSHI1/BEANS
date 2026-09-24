#!/usr/bin/env bash
# ONLINE, run once: refresh the DB-IP Lite GeoIP databases in data/geoip/ (CC BY 4.0).
set -euo pipefail
cd "$(dirname "$0")/../data/geoip"
M=${1:-$(date +%Y-%m)}
for k in country asn; do
  curl -fL "https://download.db-ip.com/free/dbip-$k-lite-$M.mmdb.gz" | gunzip -c > "dbip-$k-lite.mmdb"
  echo "updated dbip-$k-lite.mmdb ($M)"
done
