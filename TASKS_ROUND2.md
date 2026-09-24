# Round 2: build on Dhairya's code (13:30 → 23:00)

Dhairya's branch is now the shared starting point, merged into `penultimate`. It runs end to end (`synth → ingest → 4 engines → alerts → API`) and has a full React UI, which is a big head start. Everyone now works **on top of it**.

## What I measured on the baseline (5,000-tx synthetic run)

| Check | Result | Why it matters to judges |
|---|---|---|
| Pipeline runs end to end | ✅ yes | — |
| Own tests (`tests/test_all.py`) | 7/8 pass (`test_offline_enrichment` fails) | "Tests passing" badge in the README is false |
| Illicit wallets in synthetic data | **15 of ~5,000 (0.3%)** | Too few for any model to learn anything; metrics would be meaningless |
| Transactions linked through spent outputs | almost none: **15,015 "clusters" from 5,000 txs** | CIOH clustering, peel chains and PageRank all need a connected money graph |
| Seeds loaded into DB | **0** (`seeds.csv` has different columns; pipeline falls back to "pick anomalous wallets as seeds") | E4 "propagate from seed wallets" is the PS requirement, and right now it propagates from made-up seeds |
| Seed names | "LockBit", "Bybit", "CHAINALYSIS_TRACKER" | Real incidents/companies attached to fake data. Use neutral synthetic names |
| Speed | **75 s for 5,000 txs** | 200k-row demo would take ~50 min. Needs vectorising |
| E3 peel/mix | RandomForest, but falls back to **if/else rules** when it can't train | "Not just rules" requirement |
| SHAP | **hard-coded numbers** (`"impact": "+0.32"` if a flag is set) | Judges asked for an "explainability method". This is the biggest risk: an expert will spot it in 10 seconds |
| Fusion / confidence | fixed weighted formula, no trained model, no calibration | "Confidence score" isn't calibrated |
| UI | Complete components; data comes via `App.jsx`; `ui/dist` not built | Needs checking page by page against real data |
| Repo hygiene | duplicate `backend/` app (unused), `approach (1).md`/`setup.md` duplicated at root, `docs/CONTRACTS.md` + `tests/test_contracts.py` describe the old skeleton | Confusing for judges reading the repo |

(I already untracked the committed `__pycache__`/`.pyc`/`.duckdb` files and restored the full `MASTER_ROADMAP.md` on `penultimate`.)

**Rule for round 2:** same folder ownership as before. Shared files (`beans/schema.py`, `beans/store/duck.py`, `beans/cli.py`, `beans/config.py`, `requirements.txt`) need a heads-up in the group chat first.

---

## 🟦 Dharmik: make the data real and fast

**Owns:** `beans/synth/` `beans/ingest/` `beans/enrich/` `beans/graph/` `data/intel/` `data/synth/`

1. **[by 15:00] Rewrite the generator around a real UTXO ledger.** Every input must spend an earlier output. Money has to *flow* through wallets so CIOH can merge addresses, peel chains are actual chains, and PageRank has paths to walk.
   - Illicit share **3–5% of wallets**, spread over ALL typologies: RANSOMWARE, PEEL_CHAIN (5–50 hops), COINJOIN (equal denominations), DARKNET_MARKET, HACK_LAUNDERING, FAN_OUT_SMURF, ROUND_TRIP, DUSTING. Legit: retail with change, exchanges (consolidation + batch payouts), merchants, miners.
   - Several entities per typology (e.g. 8 ransomware operators, 20 peel chains), not 1–2 hard-coded examples.
   - Hardness knobs: legit CoinJoin users, exchange payouts that look like smurfing, 1–2% label noise, ~15% of illicit txs where the origin IP was missed.
   - Outputs: `labels_address.csv` (address, typology, entity_id, is_illicit), `labels_tx.csv` (txid, tx_class, typology, is_illicit), `seeds.csv` (address,label,source) = **random 20% of illicit addresses**, neutral names like `SYNTH-RANSOM-03`, source `SYNTHETIC_SEED`.
   - Presets: `--preset tiny` (~5k rows), `demo` (~100–200k rows), `bench` (1M).
2. **[by 16:00] Seeds + labels actually reach the DB.** Ingest loads `seeds.csv` and the labels next to the input file. Remove the "pick anomalous wallets as seeds" fallback, or make it loudly logged and off by default.
3. **[by 17:30] Speed.** Profile `ingest` (`python -m cProfile -o prof.out -m beans.cli ingest …`). Replace per-record pydantic/Python loops with pandas/DuckDB vectorised steps. Validate in bulk and quarantine bad rows. **Target: 100k rows ingest+graph < 90 s.**
4. **[by 18:30]** Fix `test_offline_enrichment`. Add tests: UTXO consistency (no output spent twice), illicit share within 3–5%, all 3 formats give identical tx tables.
5. **[after]** `--mapping` for unfamiliar column names; generate a second dataset with another `--seed` for the "unseen data" test; `docs/DATA_FORMATS.md`.

**Hand-off:** as soon as step 1 works, merge to `penultimate` and message Dhairya. His models are only as good as this data.

---

## 🟩 Dhairya: make the ML real (no fake numbers anywhere)

**Owns:** `beans/features/` `beans/engines/` `beans/score/` `beans/explain/` `models/`

1. **[by 14:00] Fix the contract layer for your schema:** rewrite `docs/CONTRACTS.md` and `tests/test_contracts.py` so they describe `CanonicalRecord` / `AlertRecord` and the tables in `beans/store/duck.py`. `make test` must be green again.
2. **[by 15:30] Real SHAP.** `pip install shap lightgbm` (add them to requirements.txt). Train the fusion model (§3), use `shap.TreeExplainer` for per-alert contributions, and build the English reasons from the *actual* top SHAP features. Delete the hard-coded impact table.
3. **[by 16:30] Trained fusion + calibration.** Build a wallet-level matrix (E2 anomaly, E3 class probabilities aggregated per wallet, E4 PPR/taint/hops, E1 cluster size/cluster risk, network features). Target = `labels_address.is_illicit`. **Split train/test by entity_id.** LightGBM → `CalibratedClassifierCV(method="isotonic")`. risk = 100·p; confidence = certainty + engine agreement + evidence completeness (see `TASKS_DHAIRYA.md`).
4. **[by 17:30] E3 without rule fallback.** The structural checks (equal outputs, peel ratio, chain length, fan-out) become **features**. Train LightGBM on `labels_tx.tx_class` (Dharmik's new labels). If a model file is missing, train it; never silently switch to if/else.
5. **[by 18:30] E1 + E4 on the connected data.** CIOH excluding predicted CoinJoins, plus embeddings (SVD/node2vec) and HDBSCAN suggestions. E4 = personalised PageRank from the *real* 20% seeds, taint with decay, `hops_to_seed`, path to seed for evidence.
6. **[by 20:00] `evaluate` → model card with real numbers:** per-engine metrics, recall of the *hidden* 80% illicit wallets, PR-AUC, precision@50, calibration (ECE + reliability bins), and the **ablation with vs without network features**. Store them where `ModelCard.jsx` reads from.
7. **Leakage check (test):** no `labels_*` / typology columns in any feature matrix.

---

## 🟥 Kavya: product, integration, release

**Owns:** `beans/api/` `ui/` `beans/report/` `Makefile` `README.md` `docs/` packaging, and merges into `penultimate`/`main`

1. **[by 14:30] Clean the repo** (on `kavya`, merge to penultimate):
   - Delete the unused `backend/` folder. Verify first with `grep -rn "backend" beans ui/src`, which should find nothing.
   - Delete the duplicate root `approach (1).md`, `setup.md` and `prototype_plan.md` (the originals are in `docs/archive/`).
   - `Makefile`: use `.venv/bin/python`; add `install`, `synth-tiny`, `pipeline-tiny`, `demo` targets.
   - README: remove the claims that aren't true yet ("Tests 8/8 passing", "court-admissible", MIT license unless you add a LICENSE file).
2. **[by 16:00] UI on real data, page by page.** `cd ui && npm install && npm run dev`, backend on :8000. Walk Overview → Alerts → Entity → Graph → Timeline → Map → Cases → Model → Ingest. For each page: does it load real API data, and does it handle empty states and errors? Fix the API route or the component. Use a relative `API_BASE` (`/api`) so the built UI works when served by FastAPI.
3. **[by 17:30] Serve the built UI from FastAPI** (`npm run build` → commit `ui/dist`; FastAPI mounts it at `/` with SPA fallback). Check there are no CDN fonts or scripts: `grep -rn "https://" ui/src ui/index.html`.
4. **[by 19:00] Evidence pack + seeds upload + ingest upload** work end to end from the UI.
5. **[20:30–22:30] Integration + offline test:** after each merge from Dharmik/Dhairya, run the smoke test (below). Then `docker build` → `docker run --network none -p 8000:8000` → full demo works with no internet.
6. **[21:00–22:30] Write-up + README screenshots + demo rehearsal** (roadmap §12, §14). Get the metric numbers from Dhairya's model card.
7. **[23:00] Release:** `penultimate → main`, tag `v1.0`.

---

## Getting everyone onto the new base (do this now)

```bash
git fetch origin
git checkout <your-name>
git merge origin/penultimate        # brings in Dhairya's code + cleanup + this file
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m beans.cli synth --n-tx 2000 --out data/synth/demo
.venv/bin/python -m beans.cli ingest data/synth/demo/transactions.csv
.venv/bin/python -m beans.cli serve     # http://127.0.0.1:8000/docs
```
Dhairya: `git checkout dhairya && git merge origin/penultimate` too, since penultimate now has the cleanup.

## Smoke test (Kavya runs it on penultimate after every merge)
```bash
.venv/bin/python -m pytest -q
rm -f data/beans.duckdb && .venv/bin/python -m beans.cli synth --preset tiny && .venv/bin/python -m beans.cli ingest data/synth/tiny/transactions.csv
.venv/bin/python -c "import duckdb;c=duckdb.connect('data/beans.duckdb');print(c.sql('select severity,count(*) from alerts group by 1'));print(c.sql('select count(*) from seeds'))"
```
Pass = tests green, alerts across several severities, `seeds` count > 0.

## Checkpoints (unchanged)
**15:00** data v2 lands · **17:30** real SHAP + calibrated fusion + UI on real data · **20:30** feature freeze · **23:00** release.
