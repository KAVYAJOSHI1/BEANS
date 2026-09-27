# BEANS: Bitcoin Encryption, Analysis & Network Security

[![CI](https://github.com/KAVYAJOSHI1/BEANS/actions/workflows/ci.yml/badge.svg)](https://github.com/KAVYAJOSHI1/BEANS/actions/workflows/ci.yml)

Offline, Linux-native system for monitoring and analysing Bitcoin transaction traffic.
**Smart India Hackathon · PS 26146 · National Technical Research Organisation (NTRO)**

BEANS ingests bulk Bitcoin transaction and network metadata (CSV / JSON / XML). It enriches every IP offline with country and ASN, and links IPs, transactions and wallets in one graph. Five ML engines then run: **entity clustering, anomaly detection, peel-chain / mixing detection, risk propagation from seed wallets, and a graph neural network**. The result is a ranked, explainable alert list, viewed in an investigator dashboard with link-analysis, timeline, map and case views.
Every alert also gets a **recommended action** from fixed, citable rules (draft a freeze request, draft a Section 94 BNSS
notice, prepare an FIU-IND referral pack, put on taint watch, or review as a likely false positive). The legal drafts
and evidence packs are sealed with SHA-256 and an offline RFC 3161 timestamp, and critical alerts can be pushed to a
SIEM (Splunk, Elastic, Wazuh, MISP/OpenCTI via STIX 2.1). A **watchlist** re-alerts the moment a watched wallet moves
funds in newly ingested data, and says whether the money just reached an exchange where it can still be frozen.

- **Technical report (PDF): [`docs/BEANS_Technical_Report.pdf`](docs/BEANS_Technical_Report.pdf)**: implementation, features and every measured result (rebuild: `scripts/build_report.py`)
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
.venv/bin/python -m beans.cli ingest day1.csv day2.csv … --no-score        # bulk load (chunked), then: beans score
.venv/bin/python -m beans.cli serve --watch data/inbox                     # monitoring mode: dashboard + ingest worker
.venv/bin/python -m beans.cli live                                         # live mainnet in one command (needs network)
.venv/bin/python -m beans.cli collect --dns-seed --out data/inbox           # OPTIONAL live P2P collector (needs network)
.venv/bin/python -m beans.cli collect --dns-seed --rpc http://user:pass@127.0.0.1:8332   # … + input amounts from your own node
.venv/bin/python scripts/mempool_sniffer.py --dns-seed --out data/inbox     # same collector, standalone (no ML deps)
.venv/bin/python -m beans.cli ofac-seeds --download                        # US Treasury OFAC SDN Bitcoin addresses as seeds
.venv/bin/python -m beans.cli export --neo4j out/ --stix alerts.json       # graph + STIX 2.1 indicators
.venv/bin/python -m beans.cli synth --n-tx 5000 --out data/synth/demo      # labelled synthetic dataset (CSV/JSON/XML)
.venv/bin/python -m beans.cli validate-elliptic --download                 # external validation on real Bitcoin data
.venv/bin/python -m beans.cli ingest data/synth/demo/transactions.xml      # ingest + enrich + graph + ML + alerts
.venv/bin/python -m beans.cli known-entities exchanges.csv                 # exchange / mining-pool attribution for the action rules
.venv/bin/python -m beans.cli user add alice --role supervisor             # first user switches login on (roles below)
.venv/bin/python -m beans.cli serve --port 8000                            # API (/api, docs at /docs) + dashboard
```

## Live data

`beans collect` records live mainnet transactions and the peer that announced each one. Input addresses are read from
the signature data (P2WPKH / P2PKH / P2SH-P2WPKH / P2WSH), so common-input clustering works on nearly every
transaction. Input *amounts* need the parent transaction: coins from chains seen live are resolved automatically, and
confirmed coins need `--rpc` (your own Bitcoin Core node, `gettxout`, pruned is fine) or `--esplora`. A resolver that is
slow or unreachable is given up on within a minute, and collection continues.

**One command (live connected mode):**

```bash
beans ofac-seeds --download --no-load        # once: fetch the OFAC list (loaded as seeds by `beans live`)
beans live                                   # collector + ingest worker + dashboard → http://127.0.0.1:8000/#live
```

`beans live` keeps live data in its own database (`data/live.duckdb`) and model copy (`data/live_models/`), loads new
files every 5 s and scores in batches at most every 60 s (`--score-every`); Ctrl+C stops everything cleanly.

**Air-gapped analysis server:** files arrive in a folder (for example from a DMZ sensor running
`scripts/mempool_sniffer.py` behind a data diode) and one process serves the dashboard and ingests them:

```bash
beans serve --host 0.0.0.0 --watch /srv/beans/inbox --score-every 300
```

Run the ingest worker inside the server like this rather than as a separate `beans watch` process: DuckDB lets one
process write the database, so a separate watcher makes the dashboard fail while it scores (measured: every request
failed for 37 s; in process, 45 of 45 succeeded during a 42 s scoring run). Corrupt or truncated JSON/XML files are
refused and moved to `failed/`. The full deployment plan is in [`BEANS_DEPLOYMENT_STRATEGY.md`](BEANS_DEPLOYMENT_STRATEGY.md).

What to expect: 20 minutes of mainnet (12,436 transactions, 4,720 wallets, 27 Sep 2026) produced **no alerts**. The
highest fused probability was 0.39 (threshold 0.40), and none of the 532 sanctioned addresses moved. That is the
correct result for ordinary traffic with no seeds in it. The live "first relay" IP is the collector's peer (a handful
of relaying nodes), not the sender; many connected peers over hours are needed before first-spy attribution means
anything. The models are trained on synthetic data; real alerts need seeds from a case, or the analyst verdicts
that `beans score` learns from.

The dashboard's **Live Monitor** page shows both processes: collector peers and throughput, the watch folder's
progress, transactions stored per minute, newest alerts and ingested files. Both write a heartbeat (`collector.status`,
`watch.status`) into the folder every few seconds; point the server at it with `LIVE_INBOX=data/inbox` (the default).

## Investigator tools

- **Review Queue:** open alerts ranked by how unsure the model is (probability near 0.5, low confidence), then wallets
  that scored just under the alert threshold, where a missed criminal would hide. *Illicit* / *Legitimate* verdicts are
  stored as training feedback; *Retrain now* re-scores with them.
- **Case summary** (alert drawer): a local model writes a short paragraph from a numbered fact sheet of BEANS's own
  findings, citing the facts after every sentence. A sentence is removed if it cites a missing fact, uses a number not in
  its facts, is mostly not about its facts, or speculates; if too little survives, the fact sheet itself is shown. The
  model runs through [Ollama](https://ollama.com) on the same machine (`ollama pull llama3.2`); nothing leaves it.
  `OLLAMA_MODEL=mistral NARRATIVE_TIMEOUT_S=300` writes better text but is slower on a CPU; `NARRATIVE_ENGINE=template`
  disables the model. Stored summaries go into case evidence packs, labelled with the model that wrote them.
- **Global search:** Ctrl+K (⌘K) finds wallets, transactions, IPs, alerts, entity clusters and cases by prefix.
- **Cross-chain exits:** give swap services and bridges `entity_type` `SWAP` or `BRIDGE` in the attribution list
  (`beans known-entities swaps.csv`). Funds traced to one get the `CROSS_CHAIN_EXIT` directive: a Bitcoin freeze no longer
  reaches them, so the next step is the service's records and the destination chain. No list of real services is bundled.

## Users and approvals

With no users, BEANS runs in single-user mode (no login), which is what `make demo` uses. Creating the first user with
`beans user add NAME --role admin` switches login on for the dashboard and API. Roles: **VIEWER** (read only),
**ANALYST** (triage, cases, watchlist, legal drafts), **SUPERVISOR** (approves drafts, webhooks, attribution list),
**ADMIN** (users). Section 94 and freeze drafts are filed as *pending* and must be approved by a supervisor other than
the drafter (four-eyes) before an "approved for issue" copy exists. Every action is written to the audit trail under
the user's name. Passwords: salted PBKDF2-SHA256; sessions: HttpOnly cookie, 12 h; 5 wrong passwords lock an account
for 5 minutes. An administrator can reset a password (the user's open sessions end).

| Action | Minimum role |
|---|---|
| Read alerts, graph, cases, model card | VIEWER |
| Triage, cases, watchlist, seeds (add), ingest files, legal drafts | ANALYST |
| Approve / reject legal drafts (four-eyes), webhooks, attribution list, remove seeds, re-run model evaluation, **read the audit trail** | SUPERVISOR |
| Users and passwords, regenerate the demo dataset (wipes data) | ADMIN |

**Tamper-evident audit trail.** Every audit entry stores the SHA-256 of the entry before it, so editing or deleting a
row breaks the chain. The **Audit Trail** page (supervisors) filters by user and action and verifies the chain
(`GET /api/audit/verify`). Refused requests are recorded too (`ACCESS_DENIED`). The chain proves that nothing *inside*
it was changed. To also detect entries cut off the end, write the chain head shown on that page into the case diary.

## Evaluation

Measured on the synthetic demo dataset (4,032 transactions, 13,542 wallets, 6.6 % illicit across 30 criminal entities; only 9 entities revealed as seeds). Fusion metrics are out-of-fold, grouped by entity. Full details are on the dashboard's **Model Card** page and in [`docs/TECHNICAL_WRITEUP.md`](docs/TECHNICAL_WRITEUP.md).

| | |
|---|---|
| Fused risk PR-AUC (random = 0.066) | **0.977**; without network-layer features 0.921 |
| Illicit entities alerted | **100 %** (30 of 30) with 141 alerts (4.7 per entity); 94 % of alerts are illicit, top 10: 100 % |
| Typology correct (grouped CV / on alerts) | 100 % / 100 % with the typology corpus (86 % / 91 % without); see the caveat below |
| Clustering: never mixes two actors / keeps an actor together | **1.00** / 0.79 |
| Seed propagation: hidden wallets of seeded actors reached | 77 % (legitimate wallets reached: 8 %) |
| E3 transaction-shape classifier macro-F1 | 0.993 |
| Calibration error (ECE) | 0.004 |
| End-to-end run (ingest + 5 engines + training) | 14 s on a laptop · **980,803 rows loaded and scored in 286 s, 5.3 GB peak** ([1M benchmark](docs/BENCHMARK_1M.md), [small-scale](docs/BENCHMARK.md)) |

**Across 6 independently generated datasets** (`scripts/evaluate_seeds.py --seeds 42 7 123 2024 99 555`), mean:

| | start | + context features, clustering, E4 fixes | + E5 GNN | + repeated calibration (now) |
|---|---|---|---|---|
| PR-AUC / recall at P ≥ 0.5 | 0.940 / 0.844 | 0.954 / 0.905 | 0.967 / 0.935 | **0.981 / 0.951** |
| Alert precision / precision at P ≥ 0.5 | | | 0.891 / 0.960 | **0.927 / 0.989** |
| Typology accuracy (grouped CV) / on alerts | 0.773 / 0.798 | 0.831 / 0.834 | 0.845 / 0.883; **0.997 / 0.988 with the corpus** | 0.997 / 0.988 with the corpus |
| E1 completeness (homogeneity) | 0.580 (0.999) | 0.744 (1.000) | 0.744 (1.000) | 0.744 (1.000) |
| E4 reach inside seeded actors / legitimate reached | 0.533 / 0.169 | 0.861 / 0.097 | 0.861 / 0.097 | 0.861 / 0.097 |
| Illicit entities alerted (alerts per entity) | 0.968 (9.9) | 0.962 (5.8) | 0.984 (5.8) | **0.984 (5.7)** |

**Typology corpus caveat.** `beans typology-corpus` adds the illicit wallets of 8 extra synthetic datasets (253 criminal
operations, seeds 1001-1008, never the evaluation seeds) to the typology model's training side. A label-shuffling control
drops accuracy to 0.48-0.61, so the gain is real, but near-perfect accuracy mainly shows that *synthetic* typologies are
separable once enough operations are seen. Expect less on real cases; the corpus is the mechanism for adding
confirmed real cases over time.

**Repeated calibration.** Each cross-validation fold used to calibrate on one 25 % slice of its training actors, only a
handful of criminal operations, so the isotonic curve had coarse steps. A step holding one illicit and one licit wallet
scores exactly 0.5, and across two datasets 12 of the 15 alerts at exactly 0.5 were innocent wallets. Each fold now fits
three fit/calibration splits and averages them (`CAL_REPEATS` in `beans/score/fuse.py`). Alert precision rose on
every one of the 6 datasets (mean 0.891 → 0.927) with no criminal operation lost; training takes ~10 s longer. The
Elliptic benchmark below calibrates on a held-out time window instead, so this change is not measured there.

**On real data (Elliptic, 203k real Bitcoin transactions):** BEANS's detector recipe reaches illicit F1 0.799 on the
standard temporal split, equal to the strongest published baseline (random forest 0.788; GCN 0.628), with calibration
error 0.018; revealing 30 % of illicit transactions as seeds lifts PR-AUC from 0.736 to 0.821. Elliptic is anonymised
(no addresses, amounts or IPs), so it validates the modelling approach, not the whole pipeline:
[`docs/VALIDATION_ELLIPTIC.md`](docs/VALIDATION_ELLIPTIC.md) (`beans validate-elliptic --download`).

Runs are deterministic: the same data gives the same scores and alerts every time.
Synthetic data is generated by us, so absolute numbers are optimistic. The ablation, the grouped evaluation and the
Elliptic validation below are the meaningful parts.

## Continuous integration

Every push and pull request runs [`.github/workflows/ci.yml`](.github/workflows/ci.yml):

| Job | Checks |
|---|---|
| Python tests | the full test suite on the exact versions in `constraints.txt`; the tests must not change files in the repository |
| Dashboard build | UI lint (errors fail), rebuild, and the committed `ui/dist` must match the source (FastAPI serves it as is) |
| Offline Docker image | on `penultimate`, `main` and pull requests: the image builds and serves the dashboard and API with `--network none` |

Run the same checks before pushing with `make ci` (and `make docker-offline-test` for the Docker job). Dependencies
are pinned in `constraints.txt` (`make install` and the Docker image use it too), so a new release of a library cannot
change results or break the build without a commit. After an intentional upgrade: `.venv/bin/pip freeze`, update
`constraints.txt`, and let CI confirm.

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
