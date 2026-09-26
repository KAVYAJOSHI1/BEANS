# BEANS: Bitcoin Encryption, Analysis & Network Security
PY   ?= .venv/bin/python
BEANS = $(PY) -m beans.cli
NPM  ?= npm
N_TX ?= 5000

.PHONY: help install venv synth ingest pipeline serve demo test build-ui clean-db validate-elliptic

help:
	@echo "make install    create .venv and install Python deps"
	@echo "make synth      generate a synthetic dataset (N_TX=$(N_TX)) into data/synth/demo"
	@echo "make ingest     ingest data/synth/demo/transactions.csv and run the ML pipeline"
	@echo "make pipeline   clean DB + synth + ingest"
	@echo "make serve      API + dashboard on http://127.0.0.1:8000"
	@echo "make demo       pipeline + serve (one command)"
	@echo "make test       run tests"
	@echo "make build-ui   rebuild ui/dist (needs Node >= 20.19)"
	@echo "make validate-elliptic   external validation on the real Elliptic dataset (downloads once)"
	@echo "make docker-offline-test   build image and run it with --network none"
	@echo "make bundle     offline release tarballs in dist/ (needs internet once)"

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

validate-elliptic:
	$(BEANS) validate-elliptic --download --doc docs/VALIDATION_ELLIPTIC.md

build-ui:
	cd ui && $(NPM) ci && $(NPM) run build

# ---- offline packaging -------------------------------------------------------
.PHONY: docker docker-offline-test bundle
docker:
	docker build -t beans:dev .

docker-offline-test: docker   # proves the whole product runs with networking disabled
	docker rm -f beans-offline >/dev/null 2>&1 || true
	docker run -d --network none --name beans-offline -e N_TX=1000 beans:dev
	@echo "waiting for pipeline + server..."; for i in $$(seq 1 60); do docker logs beans-offline 2>&1 | grep -q "Uvicorn running" && break; sleep 5; done
	docker exec beans-offline python -c "import urllib.request as u; [print(p, u.urlopen('http://127.0.0.1:8000'+p).status) for p in ['/', '/api/health', '/api/alerts', '/api/graph/topology', '/api/geomap/origins']]"

bundle:
	scripts/build_offline_bundle.sh --docker
