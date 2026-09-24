# BEANS: Bitcoin Encryption, Analysis & Network Security

Offline, Linux-native system for monitoring and analysing Bitcoin transaction traffic.
**Smart India Hackathon · PS 26146 · National Technical Research Organisation (NTRO)**

BEANS ingests bulk Bitcoin transaction and network metadata (CSV / JSON / XML). It enriches every IP offline with country and ASN, and links IPs, transactions and wallets in one graph. Four ML engines then run: **entity clustering, anomaly detection, peel-chain / mixing detection, and risk propagation from seed wallets**. The result is a ranked, explainable alert list, viewed in an investigator dashboard with link-analysis, timeline, map and case views.

- Vision, architecture, feature plan: [`MASTER_ROADMAP.md`](MASTER_ROADMAP.md) ([PDF](MASTER_ROADMAP.pdf))
- Team task split: [`TASKS_FINAL.md`](TASKS_FINAL.md)
- Interfaces: [`docs/CONTRACTS.md`](docs/CONTRACTS.md)

## Quickstart (Linux)

```bash
make install        # .venv + Python dependencies
make demo           # synthetic data → ingest → 4 ML engines → alerts → dashboard
# open http://127.0.0.1:8000
```

`make demo` runs fully offline. The dashboard is served from the pre-built `ui/dist/`, so Node.js is only needed to rebuild the UI (`make build-ui`, Node ≥ 20.19).

## CLI

```bash
.venv/bin/python -m beans.cli synth --n-tx 5000 --out data/synth/demo      # labelled synthetic dataset (CSV/JSON/XML)
.venv/bin/python -m beans.cli ingest data/synth/demo/transactions.xml      # ingest + enrich + graph + ML + alerts
.venv/bin/python -m beans.cli serve --port 8000                            # API (/api, docs at /docs) + dashboard
```

## Evaluation

Metrics are produced by the evaluation step on held-out synthetic data (labels are never used as model inputs) and shown on the **Model Card** page of the dashboard. Numbers will be added here once they're measured.

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
  engines/    E1 clustering · E2 anomaly · E3 peel/mix · E4 risk propagation
  score/      fusion + calibration → risk and confidence
  explain/    SHAP-based reasons
  report/     case evidence pack export
  api/        FastAPI routes
ui/           React + Vite + Tailwind + Cytoscape.js + ECharts (built into ui/dist)
data/geoip/   DB-IP Lite country + ASN databases (offline)
tests/        pytest suite
docs/         contracts, write-up, archived source docs
```

## Attribution

IP geolocation by [DB-IP](https://db-ip.com), licensed CC BY 4.0. All data in this repository is synthetic.
