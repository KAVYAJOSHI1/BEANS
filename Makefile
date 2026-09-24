# BEANS: Bitcoin Encryption, Analysis & Network Security
PY   ?= .venv/bin/python
BEANS = $(PY) -m beans.cli
NPM  ?= npm
N_TX ?= 5000

.PHONY: help install venv synth ingest pipeline serve demo test build-ui clean-db

help:
	@echo "make install    create .venv and install Python deps"
	@echo "make synth      generate a synthetic dataset (N_TX=$(N_TX)) into data/synth/demo"
	@echo "make ingest     ingest data/synth/demo/transactions.csv and run the ML pipeline"
	@echo "make pipeline   clean DB + synth + ingest"
	@echo "make serve      API + dashboard on http://127.0.0.1:8000"
	@echo "make demo       pipeline + serve (one command)"
	@echo "make test       run tests"
	@echo "make build-ui   rebuild ui/dist (needs Node >= 20.19)"

venv:
	python3 -m venv .venv && .venv/bin/pip install -U pip

install: venv
	.venv/bin/pip install -r requirements.txt

synth:
	$(BEANS) synth --n-tx $(N_TX) --out data/synth/demo

ingest:
	$(BEANS) ingest data/synth/demo/transactions.csv

clean-db:
	rm -f data/beans.duckdb data/beans.duckdb.wal

pipeline: clean-db synth ingest

serve:
	$(BEANS) serve --port 8000

demo: pipeline serve

test:
	$(PY) -m pytest -q

build-ui:
	cd ui && $(NPM) ci && $(NPM) run build
