.PHONY: help synth ingest train serve demo test build-ui

help:
	@echo "BEANS — AI-Powered Monitoring & Analysis of Bitcoin Transaction Traffic"
	@echo "Commands:"
	@echo "  make synth     Generate synthetic forensic datasets (CSV, JSON, XML)"
	@echo "  make ingest    Ingest dataset and execute full AI/ML pipeline"
	@echo "  make serve     Start FastAPI backend server on http://127.0.0.1:8000"
	@echo "  make demo      1-Click end-to-end demo execution"
	@echo "  make test      Run automated PyTest test suite"
	@echo "  make build-ui  Build React production static frontend bundle"

synth:
	python -m beans.cli synth --n-tx 2000 --out data/synth/demo

ingest:
	python -m beans.cli ingest data/synth/demo/transactions.csv

serve:
	python -m beans.cli serve --port 8000

demo:
	python -m beans.cli demo --n-tx 1000 --port 8000

test:
	python -m pytest tests/ -v

build-ui:
	cd ui && npm run build
