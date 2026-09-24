# TASKS: Dhairya (final)

**Branch:** `dhairya` · **Deliver to:** `penultimate` · **Reference:** `MASTER_ROADMAP.md` (final) · Full team view: `TASKS_FINAL.md`

We continue from Dhairya's code, which is already in this branch. Extend and fix it; don't rewrite it. Work top to bottom by deadline: MUST (M) → SHOULD (S) → COULD (C, only after 20:30). Status: ✅ done · 🟡 partial · ❌ missing. Update the status as you finish.

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
> You are working in the BEANS repo on branch `dhairya`. Read `TASKS_DHAIRYA.md` (your task list), `MASTER_ROADMAP.md` sections 6, 7 and 13 (the final reference), `beans/schema.py` (`AlertRecord`) and `beans/store/duck.py`. The existing code in `beans/features`, `beans/engines`, `beans/score` and `beans/explain` is the base: extend and fix it, don't start over. Do the tasks in the table in order of their deadline. There must be no hard-coded explanation numbers and no silent rule fallbacks: SHAP values come from `shap.TreeExplainer` on a trained model, and the fused probability is isotonic-calibrated. Never use `labels_*`/typology columns as features; split train/test by entity_id. Only modify files under the folders listed as "Owns". Ask me before touching shared files. Everything must run offline on CPU with Python 3.12. After each task, run the tests, commit, and change its status to ✅ in `TASKS_DHAIRYA.md`.
