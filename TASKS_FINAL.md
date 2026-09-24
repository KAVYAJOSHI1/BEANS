# Final Task Split: continue from Dhairya's code, follow MASTER_ROADMAP.md

**`MASTER_ROADMAP.md` is the final reference.** Feature IDs (M1–M14, S1–S9, C1–C7) are from roadmap §4.
We build on the code already on `penultimate` (Dhairya's pipeline + UI). Nothing gets rewritten from scratch; we extend and fix it.
**Order rule (roadmap §4):** finish your MUST items → then SHOULD → then COULD. No COULD work before 20:30 unless all your MUST and SHOULD items are done.

Status key: ✅ done · 🟡 partial (exists, needs finishing) · ❌ missing. The status comes from my test run of the current code.

---

## 🟦 Dharmik: Data, Ingestion, Graph
**Owns:** `beans/synth/` `beans/ingest/` `beans/enrich/` `beans/graph/` `data/intel/` `data/synth/` `docs/DATA_FORMATS.md`

| # | Feature (roadmap) | Status | What to do | By |
|---|---|---|---|---|
| M12 | Synthetic generator with ground-truth labels (§5.3) | 🟡 only 15 illicit of 5k wallets, txs not linked | Real UTXO ledger (inputs spend earlier outputs); 3–5% illicit across all 8 typologies with several entities each; legit exchanges/merchants/miners; hardness knobs; `labels_address.csv`, `labels_tx.csv`, `seeds.csv` (random 20% of illicit, neutral `SYNTH-…` names); presets tiny/demo/bench | **15:00** |
| M1/M2 | Ingest CSV/JSON/XML, array fields, fee check, quarantine (§5.1–5.2) | 🟡 works but slow (75 s / 5k) | Load seeds + labels next to the input file into the DB; vectorise validation + inserts (pandas/DuckDB). Target 100k rows < 90 s | 16:30 |
| M3 | Offline GeoIP + ASN type | 🟡 `test_offline_enrichment` fails | Fix test; Tor-exit + hosting/VPN ASN lists in `data/intel/` (dated snapshot) | 17:00 |
| M4 | Graph + first-spy (§3, §6.0) | ✅/🟡 | Check first-spy confidence (Δt to 2nd relay), wallet↔IP weights, value-weighted flow edges on the new connected data | 17:30 |
| S9 | Benchmark 1M rows | ❌ | `bench` preset + timing printout for the Results slide | 19:00 |
| — | `--mapping` for unfamiliar column names (§5.2, finale risk) | 🟡 `mapping.py` exists | Test with a renamed-column CSV + XML | 20:00 |
| C4 | Watch-folder mode (`data/inbox/` auto-ingest) | ❌ | Only after the above | after 20:30 |
| C5 | Neo4j CSV export + STIX 2.1 indicator export | ❌ | `beans export --neo4j / --stix` | after 20:30 |

**Hand-off at 15:00:** merge the new generator to `penultimate` and tell Dhairya.

---

## 🟩 Dhairya: ML Engines, Scoring, Explainability
**Owns:** `beans/features/` `beans/engines/` `beans/score/` `beans/explain/` `models/` `docs/CONTRACTS.md` `tests/test_contracts.py`

| # | Feature (roadmap) | Status | What to do | By |
|---|---|---|---|---|
| — | Contracts match your schema | ❌ `test_contracts.py` fails | Rewrite `docs/CONTRACTS.md` + test for `CanonicalRecord`/`AlertRecord`/`duck.py` tables | **14:00** |
| M10 | SHAP "why flagged" (§7) | ❌ impacts are hard-coded | Real `shap.TreeExplainer` on the fusion model; reasons generated from the actual top SHAP features; add a counterfactual line | **15:30** |
| M9 | Fusion → risk + **calibrated** confidence (§6.5) | 🟡 fixed formula | LightGBM on the wallet matrix → isotonic calibration; train/test split **by entity_id**; confidence = certainty + agreement + evidence completeness | 16:30 |
| M7 | E3 peel/mix classifier (§6 E3) | 🟡 falls back to if/else | Structural checks become features; LightGBM on `labels_tx`; no silent rule fallback | 17:30 |
| M5 | E1 clustering: CIOH + embeddings (§6 E1) | 🟡 | CIOH excluding predicted CoinJoins + change heuristic; SVD/node2vec embeddings → HDBSCAN merge suggestions | 18:30 |
| M8 | E4 risk propagation from seeds (§6 E4) | 🟡 seeds not loaded | PPR + reverse PPR + decayed taint from the **real** 20% seeds; hops + path to seed for evidence | 18:30 |
| M6 | E2 anomaly | ✅ | Re-check on new data; add SHAP for anomaly-type alerts | 19:00 |
| S6 | Model card with real metrics (§13) | 🟡 UI exists, numbers don't | `evaluate`: per-engine metrics, recall of hidden 80% illicit, PR-AUC, P@50, ECE + reliability bins, **ablation with vs without network features**; also on a second-seed dataset | **20:00** |
| S5 | Investigator feedback → retrain | 🟡 `feedback` table exists | Confirmed/FP labels from the UI feed the next `train` run | 20:30 |
| — | Leakage test | ❌ | Test that no `labels_*`/typology column enters a feature matrix | 20:30 |
| C1 | GNN (GraphSAGE) + GNNExplainer | ❌ | Only after all of the above | after 20:30 |
| C7 | Validate on public Elliptic dataset | ❌ | Needs a one-time download; optional | after 20:30 |

---

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
