# TASKS: Kavya (final)

**Branch:** `kavya` · **Deliver to:** `penultimate` · **Reference:** `MASTER_ROADMAP.md` (final) · Full team view: `TASKS_FINAL.md`

We continue from Dhairya's code, which is already in this branch. Extend and fix it; don't rewrite it. Work top to bottom by deadline: MUST (M) → SHOULD (S) → COULD (C, only after 20:30). Status: ✅ done · 🟡 partial · ❌ missing. Update the status as you finish.

## 🟥 Kavya: Product, UI/API, Packaging, Release (+ integration)
**Owns:** `beans/api/` `ui/` `beans/report/` `Makefile` `README.md` `docs/TECHNICAL_WRITEUP.md` `Dockerfile` `scripts/` + merges to `penultimate` / `main`

| # | Feature (roadmap) | Status | What to do | By |
|---|---|---|---|---|
| — | Repo cleanup | ❌ | Delete the unused `backend/` (check `grep -rn backend beans ui/src` first), root `approach (1).md` / `setup.md` / `prototype_plan.md`; Makefile uses `.venv`; README without false claims | **14:30** |
| M11 | Dashboard: alerts, entity evidence, link graph (§8) | 🟡 components exist | Check each page against real API data; relative `API_BASE="/api"`; empty and error states | **16:00** |
| M13 | Offline, one-command demo (§10.1) | 🟡 | `npm run build` → FastAPI serves `ui/dist` with SPA fallback; no CDN/remote fonts; `make demo`; `docker run --network none` test | 17:30 |
| S7 | Graph filters + expand + path/peel highlight | 🟡 | Min-risk/typology/country/ASN filters; click to expand; highlight path-to-seed and peel chain | 18:00 |
| S1 | Timeline + peel-chain replay | 🟡 component exists | Wire to real flow data | 18:30 |
| S2 | Geo map + impossible-travel arcs | 🟡 component exists | Offline world GeoJSON; wire to API | 18:30 |
| S3/S4 | Cases + evidence pack PDF/JSON with SHA-256 | 🟡 `pdf_export.py` exists | End to end from the UI; include SHAP, reasons, evidence, input hash | 19:30 |
| S8 | Seed upload → live re-propagation | 🟡 route exists | UI upload + progress + refreshed alerts | 20:00 |
| M14 | Technical write-up (§12) + README | ❌ | 6–8 pages; metrics from Dhairya's model card; screenshots; export PDF | 22:00 |
| — | Demo rehearsal (§14) with Wi-Fi off | ❌ | Twice | 22:30 |
| C6 | Login with analyst/supervisor roles | ❌ | Only if everything else is done | after 20:30 |
| C3 | Local LLM narrative report | ❌ | Skip unless there's spare time (large offline model) | optional |

**Integration:** after every merge into `penultimate`, run the smoke test below. **23:00:** `penultimate → main`, tag `v1.0`.

---

## Sync & workflow
```bash
git fetch origin && git checkout <your-name> && git merge origin/penultimate   # start from the shared base
# work, commit small, push your branch
git checkout penultimate && git pull && git merge <your-name> && .venv/bin/python -m pytest -q && git push
git checkout <your-name> && git merge penultimate
```
Shared files (`beans/schema.py`, `beans/store/duck.py`, `beans/cli.py`, `beans/config.py`, `requirements.txt`): post in the group chat before editing.

## Smoke test (after every merge to penultimate)
```bash
.venv/bin/python -m pytest -q
rm -f data/beans.duckdb && .venv/bin/python -m beans.cli synth --preset tiny && .venv/bin/python -m beans.cli ingest data/synth/tiny/transactions.csv
.venv/bin/python -c "import duckdb;c=duckdb.connect('data/beans.duckdb');print(c.sql('select severity,count(*) from alerts group by 1'));print(c.sql('select count(*) from seeds'))"
```
Pass = tests green, alerts in several severities, seeds > 0.

## Checkpoints
| Time | Must be true on `penultimate` |
|---|---|
| **15:00** | New generator merged (connected data, all typologies, seeds + labels) · contracts test green · repo cleaned |
| **17:30** | Real SHAP + calibrated fusion · UI shows real data · built UI served by FastAPI |
| **20:30** | **Feature freeze:** all MUST + SHOULD done, model card has real metrics, offline Docker test passes |
| **22:30** | Write-up, README, rehearsal done |
| **23:00** | `main` updated, tagged `v1.0` |

## Prompt to paste into your AI agent
> You are working in the BEANS repo on branch `kavya`. Read `TASKS_KAVYA.md` (your task list), `MASTER_ROADMAP.md` sections 8, 9, 10.1, 12 and 14 (the final reference), `beans/api/`, `ui/src/` and `beans/report/`. The existing API and React UI are the base: extend and fix them, don't start over. Do the tasks in the table in order of their deadline. The UI must use a relative API base (`/api`), be built into `ui/dist` and served by FastAPI, and load nothing from the internet (no CDN scripts or remote fonts). Only modify files under the folders listed as "Owns". Ask me before touching shared files. After each task, run the tests, commit, and change its status to ✅ in `TASKS_KAVYA.md`.
