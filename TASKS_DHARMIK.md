# TASKS: Dharmik (final)

**Branch:** `dharmik` · **Deliver to:** `penultimate` · **Reference:** `MASTER_ROADMAP.md` (final) · Full team view: `TASKS_FINAL.md`

We continue from Dhairya's code, which is already in this branch. Extend and fix it; don't rewrite it. Work top to bottom by deadline: MUST (M) → SHOULD (S) → COULD (C, only after 20:30). Status: ✅ done · 🟡 partial · ❌ missing. Update the status as you finish.

## 🟦 Dharmik: Data, Ingestion, Graph
**Owns:** `beans/synth/` `beans/ingest/` `beans/enrich/` `beans/graph/` `data/intel/` `data/synth/` `docs/DATA_FORMATS.md`

| # | Feature (roadmap) | Status | What to do | By |
|---|---|---|---|---|
| M12 | Synthetic generator with ground-truth labels (§5.3) | 🟡 only 15 illicit of 5k wallets, txs not linked | Real UTXO ledger (inputs spend earlier outputs); 3–5% illicit across all 8 typologies with several entities each; legit exchanges/merchants/miners; hardness knobs; `labels_address.csv`, `labels_tx.csv`, `seeds.csv` (random 20% of illicit, neutral `SYNTH-…` names); presets tiny/demo/bench | **15:00** |
| M1/M2 | Ingest CSV/JSON/XML, array fields, fee check, quarantine (§5.1–5.2) | 🟡 works but slow (75 s / 5k) | Load seeds + labels next to the input file into the DB; vectorise validation + inserts (pandas/DuckDB). Target 100k rows < 90 s | 16:30 |
| M3 | Offline GeoIP + ASN type | 🟡 test now passes |  Tor-exit + hosting/VPN ASN lists in `data/intel/` (dated snapshot) | 17:00 |
| M4 | Graph + first-spy (§3, §6.0) | ✅/🟡 | Check first-spy confidence (Δt to 2nd relay), wallet↔IP weights, value-weighted flow edges on the new connected data | 17:30 |
| S9 | Benchmark 1M rows | ❌ | `bench` preset + timing printout for the Results slide | 19:00 |
| — | `--mapping` for unfamiliar column names (§5.2, finale risk) | 🟡 `mapping.py` exists | Test with a renamed-column CSV + XML | 20:00 |
| C4 | Watch-folder mode (`data/inbox/` auto-ingest) | ❌ | Only after the above | after 20:30 |
| C5 | Neo4j CSV export + STIX 2.1 indicator export | ❌ | `beans export --neo4j / --stix` | after 20:30 |

**Hand-off at 15:00:** merge the new generator to `penultimate` and tell Dhairya.

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
> You are working in the BEANS repo on branch `dharmik`. Read `TASKS_DHARMIK.md` (your task list), `MASTER_ROADMAP.md` sections 1.2, 5 and 6.0 (the final reference), `beans/schema.py` (`CanonicalRecord`) and `beans/store/duck.py`. The existing code in `beans/synth`, `beans/ingest`, `beans/enrich` and `beans/graph` is the base: extend and fix it, don't start over. Do the tasks in the table in order of their deadline. Only modify files under the folders listed as "Owns". Ask me before touching shared files (`beans/schema.py`, `beans/store/duck.py`, `beans/cli.py`, `beans/config.py`, `requirements.txt`). Everything must run offline on Linux with Python 3.12; use vectorised pandas/DuckDB, not per-row Python loops. After each task, run the tests, commit, and change its status to ✅ in `TASKS_DHARMIK.md`.
