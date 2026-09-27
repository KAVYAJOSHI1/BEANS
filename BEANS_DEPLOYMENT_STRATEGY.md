# BEANS Deployment Strategy & Live Data Ingestion Architecture

Status key: ✅ built and tested · 🟡 planned (not built yet). Commands marked ✅ exist in the current code.

## Executive Summary: Dual-Mode Deployment Model
A national-security forensic product must support two operational environments:
1. **Air-Gapped Sovereign Mode (classified enclaves / NTRO / defence):** the analysis server has no network connection.
   Live data is captured on a separate DMZ sensor and carried across a one-way data diode as files.
2. **Live Connected Mode (investigator workstation / live demo):** one command, `beans live`, runs the mainnet P2P
   collector, continuous scoring and the dashboard together.

Both modes use the same core: files land in an inbox folder, an **ingest worker inside the server process** loads them
and scores the database in batches, and the dashboard reads the same database.

---

## Live Data Ingestion Architecture

```mermaid
flowchart TD
    subgraph Live Network ["1. Live Bitcoin mainnet (internet)"]
        SEEDS["Bitcoin DNS seeds\n(seed.bitcoin.sipa.be, ...)"]
        PEERS["Public P2P nodes (port 8333)"]
        NODE["Own Bitcoin Core node (pruned is fine)\nor Esplora: input value resolver (optional)"]
        SEEDS --> PEERS
    end

    subgraph Collection Layer ["2. DMZ sensor (internet-connected)"]
        SNIFF["scripts/mempool_sniffer.py or beans collect\n(asyncio P2P client, outbound connections only)"]
        PEERS --> SNIFF
        NODE -.-> SNIFF
        ROT["Rotated CSVs, written atomically\n(mempool_YYYYMMDD_HHMMSS.csv)"]
        SNIFF --> ROT
    end

    subgraph Security Boundary ["3. One-way transfer"]
        DIODE["Optical data diode / one-way share"]
        ROT --> DIODE
    end

    subgraph Analysis Appliance ["4. BEANS analysis server (no network)"]
        SERVER["beans serve --watch INBOX\n(one process: API + dashboard + ingest worker)"]
        GEO["Offline DB-IP country + ASN databases"]
        DUCK["DuckDB embedded store"]
        ENGINES["5 engines + calibrated fusion\n(scored in batches)"]
        DOG["Watchlist: WATCHED_FUNDS_MOVED events"]

        DIODE --> SERVER
        GEO --> SERVER
        SERVER --> DUCK
        DUCK --> ENGINES
        ENGINES --> DOG
    end

    subgraph Output & UI ["5. Analyst interface & alerts"]
        UI["Web dashboard (Live Monitor, triage, graph, cases)"]
        SIEM["SIEM webhooks\n(Wazuh JSON / Splunk HEC / Elastic / STIX 2.1)"]
        DOG --> SIEM
        DUCK --> UI
    end
```

### Why the worker runs inside the server process
DuckDB lets only one **process** write a database file. With `beans watch` and `beans serve` as two processes, the
dashboard returned **HTTP 500 for the whole scoring run** (measured: 37 s on the demo data, every request failed).
Inside one process the worker and the API share the database: **45 of 45 dashboard requests succeeded during a 42 s
scoring run**. So the analysis server runs `beans serve --watch INBOX`; standalone `beans watch` is only for batch
loading when no dashboard is open.

### Why scoring runs in batches
Scoring re-runs every engine over the whole database. Mainnet produced ~12,000 transactions in 20 minutes
(~0.8 M a day), and at a million rows one scoring run takes minutes. Scoring after every file would fall behind within
a day. The worker loads every waiting file, then scores **once**, at most every `--score-every` seconds (default 60).

---

## The 2 Live Ingestion Modes

### Mode A: Air-Gapped Sovereign Enforcement Mode
* **DMZ sensor (internet-connected):**
  ✅ `python scripts/mempool_sniffer.py --dns-seed --out /mnt/diode_in/ --rotate 300`
  (optionally `--rpc http://user:pass@127.0.0.1:8332` against a node on the same DMZ host for input amounts).
* **Analysis server (no network):**
  ✅ `beans ofac-seeds --file /media/transfer/sdn.xml` (the official OFAC list, carried over like any other file)
  ✅ `beans serve --host 0.0.0.0 --watch /srv/beans/inbox --score-every 300`
* **Security properties, stated precisely:**
  - The analysis server, database, models and case files have no network path to the internet. Nobody can connect to
    it from outside, and nothing leaves it.
  - The collector only makes **outbound** connections and never listens, so the DMZ sensor exposes no service.
  - The diode stops network attacks, **not data-borne ones**: transaction data chosen by anyone on the Bitcoin network
    still crosses it. Defences: every row is schema-validated (bad rows quarantined, never guessed), corrupt or truncated
    JSON/XML files are refused as a whole and moved to `failed/` ✅, file-size and field-length limits 🟡.
  - Files are written under a temporary name and renamed when complete ✅, so a partial file is never picked up.
    Per-file sequence numbers and SHA-256 manifests, so the receiving side can detect a lost or damaged file without a
    back-channel 🟡. If the diode's output share is read-only, copy files into a local inbox first 🟡 (the worker moves
    files to `processed/`).
  - The local RFC 3161 timestamp authority is only as good as the server clock: provide a time source inside the air
    gap (GPS / internal NTP) 🟡.

### Mode B: Live Connected Workstation Mode (`beans live`) ✅
* For live demos and connected investigator laptops. One command:
  `beans live` (defaults: DNS seeds, dashboard on http://127.0.0.1:8000/#live, a file every 60 s, scoring every 60 s)
* One process runs:
  1. the P2P collector (live mainnet peers, optional `--rpc` / `--esplora` input resolver);
  2. the ingest worker (batch scoring, in process);
  3. the API + web dashboard; the **Live Monitor** page shows collector peers, throughput, the worker's progress and new alerts.
* Live data goes to its own database (`data/live.duckdb`) and model copy (`data/live_models/`), never into the demo
  data. If `data/intel/ofac_sdn.xml` is present, the sanctioned addresses are loaded as seeds on start.
* Ctrl+C stops everything cleanly: the collector writes its last rows to a final file, which the next start loads.
* **What the investigator sees, precisely:** each transaction with the IP of the peer that relayed it *to the
  collector* (a handful of peers, mostly hosting providers), geolocated to country and ASN. That is **not** the
  sender's location; first-relay attribution needs many connected peers over hours. On ordinary traffic with no seeds,
  expect **no alerts** (20 minutes of mainnet, 12,436 transactions: 0 alerts, 0 sanctioned addresses moved).

---

## Form Factor Deployment Recommendation

| Deployment option | Live data | Air-gapped suitability | Packaging | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Unified CLI** (`beans live`, `beans serve --watch`) | Direct P2P mainnet (live), or files from an inbox | Yes (`serve --watch` needs no network) | Standard install (`make install`) | ✅ |
| **Air-gapped Docker appliance** | Files via a mounted inbox volume | Yes (`--network none` tested in CI) | `make bundle` offline tarballs | 🟡 the image serves the dashboard and passes the offline test; watching a mounted inbox, a data volume, a non-root user and a health check are still to do |
| **Systemd services** (DMZ sensor + analysis server) | Sensor: collector; server: `serve --watch` | Yes | Unit files | 🟡 |
| **Linux desktop window** (`beans desktop`, pywebview) | Same as the CLI | Yes | Adds GTK/Qt WebKit dependencies that are hard to ship offline | Not recommended: a launcher that opens the browser at the dashboard gives the same experience |

## Remaining work, in order
1. Diode-safe transfer: sequence numbers + SHA-256 manifest per file, gap detection on the receiving side, read-only
   source share support, file-size and field-length limits at the boundary.
2. Docker appliance mode: `serve --watch /app/data/inbox`, data volume, non-root user, health check, demo data opt-in.
3. Retention: score a rolling window (e.g. the last 7 days) and archive older data, so scoring time stays bounded
   under continuous capture.
4. Operations: systemd units, backups of the database and case files, time source inside the air gap.
