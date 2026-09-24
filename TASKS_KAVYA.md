# TASKS: Kavya · API, Dashboard, Reports, Packaging, Integration (team lead)

**Branch:** `kavya` · **Merge target:** `penultimate` (you also do the final `penultimate → main`) · **Deadline:** CP3 at 20:30
**You own:** `beans/api/` `ui/` `beans/report/` `beans/cli_app.py` `Makefile` `README.md` `docs/TECHNICAL_WRITEUP.md` `scripts/build_offline_bundle.sh` `Dockerfile` `tests/test_api_*.py`
**You write these tables:** alert_status, case_file, case_alert, audit_log
**Read first:** `docs/CONTRACTS.md` (§5 is your API), `data/samples/mock_alerts.json`, `data/samples/mock_subgraph.json`, `MASTER_ROADMAP.md` §8, §9, §10.1, §12 and §14

Why your part matters: judges see the product only through your dashboard, and they grade **"dashboard showing flagged entities and evidence for each flag"** and **"workable complete offline solution for Linux"** directly. You're also the integrator: at each checkpoint you make sure `penultimate` runs end to end.

**Don't wait for data:** start in mock mode (`BEANS_MOCK=1`). The mock files already match the real contracts.

Machine notes: Node **18** is installed, so use **Vite 5** (`npm create vite@5`); Vite 6+ needs Node 20. No CDN fonts or scripts anywhere: everything is bundled so it works offline.

---

## CP1 (by 14:30): API + UI shell on mock data
- [ ] **K1 FastAPI app** `beans/api/main.py` (+ `routes/alerts.py`, `entity.py`, `graph.py`, `stats.py`, `cases.py`, `jobs.py`, `model.py`)
  - `create_app(db_path, mock)`: one DuckDB connection per process, guarded by a lock (DuckDB is single-writer).
  - Mock mode serves `data/samples/mock_*.json`. Real mode reads the tables. Alerts join `alert_status` (default `OPEN`).
  - Serves `ui/dist/` at `/` (SPA fallback to index.html) and the API under `/api`. Binds to 127.0.0.1.
  - Implement `beans serve` in `beans/cli_app.py` (uvicorn).
- [ ] **K2 UI scaffold** in `ui/`: Vite 5 + React 18 + TypeScript + Tailwind + react-router. Dark "investigator" theme, sidebar nav: Overview · Alerts · Graph · Timeline · Map · Cases · Model · Ingest. Footer: "IP geolocation by DB-IP (CC BY 4.0)". Vite dev proxy `/api → 127.0.0.1:8000`.
- [ ] **K3 Alerts page**: ranked table (rank, severity chip, entity, type, risk bar, confidence, top reason, status), filters (severity, type, status), search box (address/txid/IP), pagination. Click a row to open the alert detail.
- [ ] Merge to penultimate.

## CP2 (by 17:30): real data + core investigation views
- [ ] **K4 Alert / entity detail page**: header (entity, severity, risk, confidence), **"Why flagged"** reasons list, SHAP bar chart (ECharts; positive red, negative green), engine-scores radar, evidence lists (txids, addresses, IPs, path to seed, peel chain) where every item links to its entity page, and buttons *Confirm / False positive / Investigating / Add to case* plus a notes field (PATCH → audit_log).
- [ ] **K5 Link graph page**: `cytoscape` + `react-cytoscapejs` + `cytoscape-dagre` + `cytoscape-cose-bilkent`. Node shapes: wallet = ellipse, tx = diamond, ip = triangle, asn = rectangle. Colour by risk; red ring for seeds. Click a node → side panel + "expand" (re-query with the new center). Toggles: highlight path to seed, highlight peel chain; layout switch (cose ↔ dagre left-to-right for chains). Uses `/api/graph/subgraph` → Dharmik's `beans.graph.subgraph`.
- [ ] **K6 Overview page**: KPI tiles (txs, wallets, IPs, clusters, alerts by severity), alerts-by-type donut, alerts-over-time line, top countries/ASNs bars.
- [ ] **K7 Real-data API**: `/stats/overview`, `/alerts`, `/entity/*`, `/graph/subgraph`, `/model/card`. Switch the UI off mock and test against `make pipeline-tiny` output from penultimate.
- [ ] **K8 `beans pipeline`** command works on penultimate (already stubbed in `cli_app.py`), plus `POST /api/ingest` (upload → background job → ingest/graph/score) and `GET /api/jobs/{id}`.

## CP3 (by 20:30): the "wow" layer + offline
- [ ] **K9 Timeline page**: fund-flow swimlane (x = time, y = wallet) for a center entity; peel-chain replay slider (step through hops).
- [ ] **K10 Geo map page**: ECharts map with an **offline** world GeoJSON committed at `ui/src/assets/world.json` (download once). Points = IP country centroids sized by risk; arcs = impossible-travel pairs.
- [ ] **K11 Cases + evidence pack**: create case, add alerts, notes, status. Export **PDF** (`beans/report/pdf.py`, Jinja2 → HTML → WeasyPrint) + **JSON**. Include the SHA-256 of the ingested source files (from `ingest_log`), the reasons, SHAP, the evidence lists and a static graph image or table. Check `python -c "import weasyprint"` early; if system libs are missing, fall back to HTML export.
- [ ] **K12 Model card page**: renders `model_card`: metrics tables per engine, PR/reliability charts, ablation (with vs without network features), feature importance.
- [ ] **K13 Seeds + Ingest pages**: upload seeds.csv → `POST /api/seeds` → re-score; upload CSV/JSON/XML with progress and a quarantine summary.
- [ ] **K14 Offline packaging**: `npm run build` → commit `ui/dist/`; `scripts/build_offline_bundle.sh` (`pip download -r requirements.txt -d wheelhouse`, tar code + wheelhouse + dist + mmdb + models + demo data); `Dockerfile` (python:3.12-slim, install from wheelhouse). **Test:** `docker run --network none -p 8000:8000 beans` → full demo works.

## 20:30–23:00: integration, docs, release
- [ ] Integration smoke test on penultimate (see TEAM_PLAN.md) after each merge from Dharmik/Dhairya.
- [ ] `docs/TECHNICAL_WRITEUP.md` (roadmap §12 outline, 6–8 pages). Get the model-choice and metrics text from Dhairya and the data/generator text from Dharmik. Export to PDF.
- [ ] README: quickstart, screenshots (headless Chrome), architecture image, offline instructions.
- [ ] Rehearse the demo script (roadmap §14) with Wi-Fi off.
- [ ] 23:00: `git checkout main && git merge penultimate && git tag v1.0 && git push && git push --tags`.

---

## Definition of done
```bash
make install && make test
make pipeline-tiny && make serve        # http://127.0.0.1:8000 → every page works on real data
docker run --network none ...           # same, fully offline
```

## Prompt to paste into your AI agent
> You are working in the BEANS repo on branch `kavya`. Read `TASKS_KAVYA.md`, `docs/CONTRACTS.md` (section 5 is the API to build), `beans/schema.py`, `beans/store/ddl.sql`, `data/samples/mock_alerts.json`, `data/samples/mock_subgraph.json` and `MASTER_ROADMAP.md` sections 8, 9 and 10.1. Implement the tasks in `TASKS_KAVYA.md` in checkpoint order, starting in mock mode (`BEANS_MOCK=1`). Only create or modify files under the paths listed as "You own". Never change shared files without asking me. Backend: FastAPI + DuckDB, bound to 127.0.0.1. Frontend: Vite 5 (Node 18) + React 18 + TypeScript + Tailwind + cytoscape/react-cytoscapejs + echarts, dark investigator theme, **no CDN or remote fonts** (it must work offline). After each task, run `make test`, commit, and tick the checkbox in `TASKS_KAVYA.md`.
