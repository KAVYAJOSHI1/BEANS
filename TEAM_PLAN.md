# BEANS: Team Plan for Tonight (24 Sep 2026)

**Goal:** a complete, offline, demo-ready product on `main` by **23:30**.
**Team:** Kavya (lead, app + integration) · Dharmik (data + graph) · Dhairya (ML + explainability). Everyone builds with AI agents.

| Doc | What it is |
|---|---|
| `MASTER_ROADMAP.md` / `.pdf` | Full vision, architecture, and the features in MUST/SHOULD/COULD order |
| `docs/CONTRACTS.md` | **The interfaces between the three of us. Read it first.** |
| `TASKS_KAVYA.md` / `TASKS_DHARMIK.md` / `TASKS_DHAIRYA.md` | Your personal task list (each is on your own branch) |

## Branches

```
main          ← final only. Merged from penultimate at 23:00 after the smoke test passes.
penultimate   ← integration + testing. Everyone merges their branch here at each checkpoint.
kavya         ← beans/api, ui/, beans/report, Makefile, README, write-up, packaging
dharmik       ← beans/synth, beans/ingest, beans/enrich, beans/graph, data/intel, data/geoip
dhairya       ← beans/features, beans/engines, beans/score, beans/explain, models/, notebooks/
```

**Folder ownership stops merge conflicts.** Only touch files you own. The shared files are `beans/schema.py`, `beans/store/*`, `beans/cli.py`, `beans/config.py`, `docs/CONTRACTS.md`, `requirements.txt` and `tests/test_contracts.py`. Tell the team before changing any of them. `requirements.txt` is append-only.

## Git workflow (copy-paste)

```bash
# first time
git clone git@github.com:KAVYAJOSHI1/BEANS.git && cd BEANS
git checkout <your-name>                   # kavya | dharmik | dhairya
make install                               # creates .venv and installs everything

# while working: commit small and often
git add -A && git commit -m "synth: peel chain typology" && git push

# at every checkpoint: deliver to penultimate
git checkout penultimate && git pull
git merge <your-name>                      # resolve conflicts only in your own files
make test                                  # must be green before you push
git push
git checkout <your-name> && git merge penultimate   # pick up everyone else's work
```

Final release (Kavya): `git checkout main && git merge penultimate && git tag v1.0 && git push --tags`.

## Timeline & checkpoints

| Time | Checkpoint | Dharmik | Dhairya | Kavya |
|---|---|---|---|---|
| 12:45 | **Kickoff** | pull, `make install`, hand `TASKS_DHARMIK.md` to your agent | same | same |
| **14:30** | **CP1: data flows** | `synth tiny` + `ingest` (all 3 formats) + GeoIP → DuckDB, merged to penultimate | features + E2 IsolationForest working on tiny DB | FastAPI with mock mode + UI shell + alert table on mock data |
| **17:30** | **CP2: models + real API** | `demo` preset (all typologies, noise), `graph.build`, `graph.subgraph`, quarantine, mapping | E1 CIOH+embeddings, E3 LightGBM, E4 PPR/taint, fusion → `alert` table | API on real DB, entity page, graph view, pipeline command |
| **20:30** | **CP3: feature freeze** | perf (200k rows < 60 s), 1M benchmark, tests | SHAP reasons, calibration, `evaluate` → model_card | timeline, map, cases, PDF export, model-card page, `make demo` |
| 20:30–22:30 | **Integration & testing on `penultimate`** | fix data bugs found by the others | fix scoring bugs, tune for hard preset | offline test (`docker --network none`), README, TECHNICAL_WRITEUP |
| 23:00 | **Release** | | | penultimate → main, tag v1.0, build roadmap PDF |

**Hard rule:** after CP3, bug fixes only. MUST items (roadmap §4) come before any SHOULD item.

## Unblocking each other (work in parallel from minute one)
- **Kavya** doesn't need real data yet. `BEANS_MOCK=1` plus `data/samples/mock_alerts.json` and `mock_subgraph.json` are enough.
- **Dhairya** doesn't need to wait for Dharmik. Until CP1, write a 50-line throwaway generator in `notebooks/` that fills the tables in `ddl.sql` (a few peel chains and CoinJoins), then switch to `beans synth` output.
- **Dharmik** only depends on the contracts. Check yourself against `data/samples/sample.{csv,json,xml}`.

## Integration smoke test (run on `penultimate` at each checkpoint)
```bash
make test
rm -f data/beans.duckdb && make pipeline-tiny     # ingest → graph → score → eval
.venv/bin/python -m beans.cli serve &              # then open http://127.0.0.1:8000
curl -s 127.0.0.1:8000/api/alerts?limit=3 | head
```
