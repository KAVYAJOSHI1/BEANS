#!/bin/sh
# Generate + score a demo dataset on first start (if the DB is empty), then serve API + dashboard.
set -e
if [ ! -f data/beans.duckdb ] && [ "${SKIP_DEMO_DATA:-0}" != "1" ]; then
    python -m beans.cli synth --n-tx "$N_TX" --out data/synth/demo
    python -m beans.cli ingest data/synth/demo/transactions.csv
fi
exec python -m beans.cli serve --host 0.0.0.0 --port 8000
