# BEANS: Bitcoin Encryption, Analysis & Network Security

Offline, Linux-native system for monitoring and analysing Bitcoin transaction traffic.
**Smart India Hackathon · PS 26146 · National Technical Research Organisation (NTRO)**

BEANS ingests bulk Bitcoin transaction and network metadata (CSV / JSON / XML). It enriches every IP offline with country and ASN, and links IPs, transactions and wallets in one graph. Five ML engines then run: **entity clustering, anomaly detection, peel-chain / mixing detection, risk propagation from seed wallets, and a graph neural network**. The result is a ranked, explainable alert list, viewed in an investigator dashboard with link-analysis, timeline, map and case views.
Every alert also gets a **recommended action** from fixed, citable rules (draft a freeze request, draft a Section 94 BNSS
notice, prepare an FIU-IND referral pack, put on taint watch, or review as a likely false positive). The legal drafts
and evidence packs are sealed with SHA-256 and an offline RFC 3161 timestamp, and critical alerts can be pushed to a
SIEM (Splunk, Elastic, Wazuh, MISP/OpenCTI via STIX 2.1). A **watchlist** re-alerts the moment a watched wallet moves
funds in newly ingested data, and says whether the money just reached an exchange where it can still be frozen.

- Vision, architecture, feature plan: [`MASTER_ROADMAP.md`](MASTER_ROADMAP.md) ([PDF](MASTER_ROADMAP.pdf))
- Team task split: [`TASKS_FINAL.md`](TASKS_FINAL.md)
- Interfaces: [`docs/CONTRACTS.md`](docs/CONTRACTS.md)
- Technical write-up: [`docs/TECHNICAL_WRITEUP.md`](docs/TECHNICAL_WRITEUP.md) · data formats: [`docs/DATA_FORMATS.md`](docs/DATA_FORMATS.md) · benchmark: [`docs/BENCHMARK.md`](docs/BENCHMARK.md) · references: [`docs/REFERENCES.md`](docs/REFERENCES.md)

## Quickstart (Linux)

```bash
make install        # .venv + Python dependencies
make demo           # synthetic data → ingest → 5 ML engines → alerts → dashboard
# open http://127.0.0.1:8000
```

`make demo` runs fully offline. The dashboard is served from the pre-built `ui/dist/`, so Node.js is only needed to rebuild the UI (`make build-ui`, Node ≥ 20.19). Timestamping needs the `openssl` binary (present on most Linux systems and in the Docker image).

## CLI

```bash
.venv/bin/python -m beans.cli ingest their_export.csv --mapping their.yaml # unfamiliar column names (docs/DATA_FORMATS.md)
.venv/bin/python -m beans.cli watch data/inbox                             # monitoring mode: score every new file
.venv/bin/python -m beans.cli export --neo4j out/ --stix alerts.json       # graph + STIX 2.1 indicators
.venv/bin/python -m beans.cli synth --n-tx 5000 --out data/synth/demo      # labelled synthetic dataset (CSV/JSON/XML)
.venv/bin/python -m beans.cli validate-elliptic --download                 # external validation on real Bitcoin data
.venv/bin/python -m beans.cli ingest data/synth/demo/transactions.xml      # ingest + enrich + graph + ML + alerts
.venv/bin/python -m beans.cli known-entities exchanges.csv                 # exchange / mining-pool attribution for the action rules
.venv/bin/python -m beans.cli user add alice --role supervisor             # first user switches login on (roles below)
.venv/bin/python -m beans.cli serve --port 8000                            # API (/api, docs at /docs) + dashboard
```

## Users and approvals

With no users, BEANS runs in single-user mode (no login), which is what `make demo` uses. Creating the first user with
`beans user add NAME --role admin` switches login on for the dashboard and API. Roles: **VIEWER** (read only),
**ANALYST** (triage, cases, watchlist, legal drafts), **SUPERVISOR** (approves drafts, webhooks, attribution list),
**ADMIN** (users). Section 94 and freeze drafts are filed as *pending* and must be approved by a supervisor other than
the drafter (four-eyes) before an "approved for issue" copy exists. Every action is written to the audit trail under
the user's name. Passwords: salted PBKDF2-SHA256; sessions: HttpOnly cookie, 12 h; 5 wrong passwords lock an account
for 5 minutes.

## Evaluation

Measured on the synthetic demo dataset (4,032 transactions, 13,542 wallets, 6.6 % illicit across 30 criminal entities; only 9 entities revealed as seeds). Fusion metrics are out-of-fold, grouped by entity. Full details are on the dashboard's **Model Card** page and in [`docs/TECHNICAL_WRITEUP.md`](docs/TECHNICAL_WRITEUP.md).

| | |
|---|---|
| Fused risk PR-AUC (random = 0.066) | **0.961**; without network-layer features 0.914 |
| Illicit entities alerted | **100 %** (30 of 30) with 144 alerts (4.8 per entity); 90 % of alerts are illicit, top 10: 100 % |
| Typology correct (grouped CV / on alerts) | 100 % / 100 % with the typology corpus (86 % / 91 % without); see the caveat below |
| Clustering: never mixes two actors / keeps an actor together | **1.00** / 0.79 |
| Seed propagation: hidden wallets of seeded actors reached | 77 % (legitimate wallets reached: 8 %) |
| E3 transaction-shape classifier macro-F1 | 0.993 |
| Calibration error (ECE) | 0.006 |
| End-to-end run (ingest + 5 engines + training) | 14 s on a laptop; scoring ≈ 3,300 rows/s ([benchmark](docs/BENCHMARK.md)) |

**Across 6 independently generated datasets** (`scripts/evaluate_seeds.py --seeds 42 7 123 2024 99 555`), mean:

| | start | + context features, clustering, E4 fixes | + E5 GNN (now) |
|---|---|---|---|
| PR-AUC / recall at P ≥ 0.5 | 0.940 / 0.844 | 0.954 / 0.905 | **0.966 / 0.952** |
| Typology accuracy (grouped CV) / on alerts | 0.773 / 0.798 | 0.831 / 0.834 | 0.845 / 0.883; **0.997 / 0.988 with the corpus** |
| E1 completeness (homogeneity) | 0.580 (0.999) | 0.744 (1.000) | 0.744 (1.000) |
| E4 reach inside seeded actors / legitimate reached | 0.533 / 0.169 | 0.861 / 0.097 | 0.861 / 0.097 |
| Illicit entities alerted (alerts per entity) | 0.968 (9.9) | 0.962 (5.8) | **0.984 (6.0)** |

**Typology corpus caveat.** `beans typology-corpus` adds the illicit wallets of 8 extra synthetic datasets (253 criminal
operations, seeds 1001-1008, never the evaluation seeds) to the typology model's training side. A label-shuffling control
drops accuracy to 0.48-0.61, so the gain is real, but near-perfect accuracy mainly shows that *synthetic* typologies are
separable once enough operations are seen. Expect less on real cases; the corpus is the mechanism for adding
confirmed real cases over time.

Alert *precision* is lower (0.94 → 0.86) only because each criminal now takes ~6 alerts instead of ~10: the same
handful of false alerts weighs more in a list half as long.

**On real data (Elliptic, 203k real Bitcoin transactions):** BEANS's detector recipe reaches illicit F1 0.799 on the
standard temporal split, equal to the strongest published baseline (random forest 0.788; GCN 0.628), with calibration
error 0.018; revealing 30 % of illicit transactions as seeds lifts PR-AUC from 0.736 to 0.821. Elliptic is anonymised
(no addresses, amounts or IPs), so it validates the modelling approach, not the whole pipeline:
[`docs/VALIDATION_ELLIPTIC.md`](docs/VALIDATION_ELLIPTIC.md) (`beans validate-elliptic --download`).

Runs are deterministic: the same data gives the same scores and alerts every time.
Synthetic data is generated by us, so absolute numbers are optimistic. The ablation, the grouped evaluation and the
Elliptic validation below are the meaningful parts.

## Repository layout

```
beans/
  cli.py  config.py  schema.py
  synth/      labelled synthetic dataset generator (UTXO ledger, illicit typologies)
  ingest/     streaming CSV / JSON / XML parsers, validation, quarantine
  enrich/     offline GeoIP (DB-IP Lite) + ASN type classification
  store/      embedded DuckDB storage
  graph/      IP ↔ TX ↔ wallet graph, first-spy attribution
  features/   transaction / wallet / network features
  engines/    E1 clustering · E2 anomaly · E3 peel/mix · E4 risk propagation · E5 graph neural network (SIGN)
  score/      fusion + calibration → risk and confidence
  decision/   action directives: deterministic rules → recommended next step per alert
  alerting/   SIEM / threat-intel webhooks (JSON, Splunk HEC, Elastic, STIX 2.1)
  explain/    SHAP-based reasons
  report/     case evidence pack, Section 94 / freeze drafts, FIU referral pack, RFC 3161 timestamps
  api/        FastAPI routes
ui/           React + Vite + Tailwind + Cytoscape.js + ECharts (built into ui/dist)
data/geoip/   DB-IP Lite country + ASN databases (offline)
tests/        pytest suite
docs/         contracts, write-up, archived source docs
```

## Attribution

IP geolocation by [DB-IP](https://db-ip.com), licensed CC BY 4.0. All data in this repository is synthetic.
