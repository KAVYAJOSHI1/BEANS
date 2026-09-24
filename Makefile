# OWNER: Kavya (others: add targets for your own module at the bottom, one line each)
PY ?= .venv/bin/python
BEANS = $(PY) -m beans.cli
DB ?= data/beans.duckdb

.PHONY: venv install test lint synth-tiny synth-demo pipeline-tiny pipeline-demo serve serve-mock ui demo

venv:
	python3 -m venv .venv && .venv/bin/pip install -U pip

install: venv
	.venv/bin/pip install -r requirements.txt && .venv/bin/pip install -e . --no-deps

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check beans tests

synth-tiny:
	$(BEANS) synth --preset tiny

synth-demo:
	$(BEANS) synth --preset demo

pipeline-tiny: synth-tiny
	$(BEANS) pipeline data/synth/tiny/transactions.csv --db $(DB)

pipeline-demo: synth-demo
	$(BEANS) pipeline data/synth/demo/transactions.csv --db $(DB)

serve:
	$(BEANS) serve --db $(DB)

serve-mock:
	BEANS_MOCK=1 $(BEANS) serve

ui:
	cd ui && npm ci && npm run build

demo: pipeline-demo serve
