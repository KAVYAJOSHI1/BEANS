# GeoIP databases (offline)

- `dbip-country-lite.mmdb`: IP → country (DB-IP Lite, 2026-09)
- `dbip-asn-lite.mmdb`: IP → ASN number + org (DB-IP Lite, 2026-09, GeoLite2-ASN compatible)

Source: https://db-ip.com/db/lite.php. License: **CC BY 4.0**. Attribution "IP Geolocation by DB-IP" must appear in the UI footer and the write-up.
Refresh (online, once): `scripts/fetch_geoip.sh`. Read with `maxminddb.open_database(path).get(ip)`.
