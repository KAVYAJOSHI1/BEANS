# TASKS: Dhairya · Features, 4 ML Engines, Fusion, Explainability, Evaluation

**Branch:** `dhairya` · **Merge target:** `penultimate` · **Deadline:** CP3 at 20:30
**You own:** `beans/features/` `beans/engines/` `beans/score/` `beans/explain/` `beans/cli_ml.py` `models/` `notebooks/` `tests/test_ml_*.py`
**You write these tables:** cluster, cluster_suggest, tx_scores, wallet_scores, alert, model_card
**Read first:** `docs/CONTRACTS.md`, `beans/schema.py` (`Alert`, `Evidence`, `alert_id_for`, `severity_for`), `beans/store/ddl.sql`, `MASTER_ROADMAP.md` §6, §7 and §13

Why your part matters: the PS demands a **"working model, not just rules"** and an **"explainable alert list with a confidence score"**. Judges will check the 4 focus areas from the PS table: **Entity Clustering (CIOH + graph embeddings), Anomaly Detection, Peeling-Chain/Mixing Detection, Risk Scoring propagated from seed wallets.** Every one of them needs a model, a metric, and a visible explanation.

**Golden rule (leakage):** `labels_address` / `labels_tx` are **targets and evaluation only, never features.** `seeds` *is* allowed as input (it's the "known bad" intel). Split train/test **by entity_id** so an entity's wallets never end up on both sides.

**Don't wait for Dharmik:** until CP1, write `notebooks/mini_synth.py` that fills the ddl tables with ~2k txs, including a few peel chains, CoinJoins and a seed. Switch to `beans synth tiny` as soon as it lands on penultimate.

---

## CP1 (by 14:30): features + first model
- [ ] **F1 `beans/features/tx.py`**: `tx_features(con) -> DataFrame` indexed by txid: n_in, n_out, log total_in/out, fee, fee_rate proxy (fee / (n_in·148 + n_out·34)), **n_equal_outputs**, max equal-value group size, output value entropy, max/min output ratio, round-number output flag, has_change_guess, script_type one-hot, **UTXO age** of inputs (ts of tx − ts the input was created), **time-to-next-spend** of the largest output, hour-of-day, is_multisig.
- [ ] **F2 `beans/features/wallet.py`**: `wallet_features(con) -> DataFrame` indexed by address: degree in/out, unique counterparties, recv/sent volume, lifetime, **holding time**, % outputs spent < 1 h, fan-in/fan-out ratio, first-seen → first large inflow gap, share of txs that look like CoinJoin (after E3), address reuse.
- [ ] **F3 `beans/features/network.py`** (the network ↔ chain correlation): per wallet via `wallet_ip` + `ip`: # distinct first-spy IPs, # countries, # ASNs, share of Tor/VPN/hosting ASN, **geo-velocity** (max km/h between consecutive broadcasts, using country centroids in `beans/features/country_centroids.csv`), off-hours ratio, non-8333 port ratio, first-spy confidence mean, IP shared with seed wallets.
- [ ] **E2 anomaly** `beans/engines/e2_anomaly.py`: IsolationForest on wallet features (and one on tx features). Output percentile-normalised `anomaly` in [0,1]. Save with joblib to `models/e2_*.joblib`.

## CP2 (by 17:30): all 4 engines + fusion → alert table
- [ ] **E3 peel/mix** `beans/engines/e3_peelmix.py`
  - Structural extractors (features, not verdicts): peel-chain walker (1–2 in / 2 out, one output ≪ other, big output re-spent soon in the same shape → `peel_chain_id`, `peel_chain_pos`, chain length, mean peel ratio, mean hop interval); CoinJoin shape (n_equal_outputs, denomination match, n_in from distinct clusters); fan-in/out degree ratios; short cycles (bounded DFS ≤ 5 on flow_edge) for round-trip.
  - **LightGBM multiclass** over `TxClass` using `labels_tx.tx_class` as the target, with class weights. Write `tx_scores` (p_* for every class, `tx_class_pred`, `anomaly` from E2-tx, peel chain id/pos).
- [ ] **E1 clustering** `beans/engines/e1_cluster.py`
  - CIOH union-find over `tx_input` grouped by txid, **excluding txs E3 predicts as coinjoin** (otherwise strangers merge). Say this in the demo.
  - Conservative change heuristic: 2-output tx, one output address never seen before, non-round value, same script type as inputs → merge. Method = `CIOH+CHANGE`.
  - **Graph embeddings** (the PS asks for them explicitly): build the cluster-level flow graph; embed with node2vec if it installs cleanly, otherwise sklearn `TruncatedSVD` on the normalised adjacency (spectral embedding) concatenated with scaled behavioural features. Then `sklearn.cluster.HDBSCAN` → pairs of CIOH clusters in the same HDBSCAN group with cosine similarity > 0.9 go to `cluster_suggest`.
  - Write `cluster` (every address gets a cluster_id; singletons too).
- [ ] **E4 risk propagation** `beans/engines/e4_propagate.py`
  - Personalised PageRank on the value-weighted flow graph (`beans.graph.load.load_flow_graph`), with personalisation = seeds. Also run reverse PPR on the reversed graph (who funds bad actors). Use igraph `personalized_pagerank` if networkx is slow.
  - Decayed taint: taint(w) = Σ over inflow edges of (share of the edge's value) × taint(src) × λ, where λ = 0.9 per hop, iterated to convergence or 6 hops. `hops_to_seed` via BFS.
  - Optional (COULD): GraphSAGE via torch_geometric → `gnn` column. Skip unless everything else is done.
- [ ] **Fusion** `beans/score/fuse.py`
  - Wallet-level matrix: E2 anomaly, E4 ppr/ppr_reverse/taint/hops, max & mean of E3 p_peel/p_coinjoin/p_fan_out over the wallet's txs, cluster-level max risk signals, network features.
  - Target `labels_address.is_illicit`. **LightGBM (small)** or LogisticRegression, then **isotonic calibration** (`CalibratedClassifierCV(method="isotonic")`) → `fused_prob`. `risk = 100 × fused_prob`, `severity = severity_for(risk)`.
  - `confidence = 0.5·|2p−1| + 0.3·engine_agreement + 0.2·evidence_completeness` (agreement = share of engines above their own 90th percentile that agree with the decision; completeness = has network obs, cluster size > 1, has path to seed). Clip to [0,1].
- [ ] **Alerts** `beans/score/alerts.py`: one alert per cluster (best wallet as representative, `member_count` = cluster size), plus tx alerts for high-p CoinJoin/peel txs, plus IP alerts for first-spy IPs linked to ≥ 3 flagged clusters. `alert_type` = dominant signal. `alert_id = alert_id_for(entity_type, entity_id)`. Keep risk ≥ 40 or top 2000. Rank by risk × confidence. Every row must validate as `beans.schema.Alert` (see `data/samples/mock_alerts.json`).
- [ ] `beans.score.run_all(con, train=True)` runs everything in order: features → E3 → E1 → E2 → E4 → fusion → alerts.

## CP3 (by 20:30): explainability + evaluation
- [ ] **SHAP** `beans/explain/shap_explain.py`: TreeExplainer on the fusion model → top-5 `shap_top` per alert. Also explain IsolationForest scores for anomaly-type alerts.
- [ ] **Reasons** `beans/explain/reasons.py` + `templates.yaml`: map (feature, direction, value) to a plain-English sentence, e.g. `peel_chain_length: "Part of a {value:.0f}-hop peeling chain"`. Each alert gets 3–5 reasons; the first line is the strongest. Add one counterfactual line where possible: "Would drop to MEDIUM without the link to seed X."
- [ ] **Evidence**: `txids` (top 10 by value), `ips` (first-spy IPs), `seed` + `path_to_seed` (via `beans.graph.path`), `peel_chain` (ordered txids), `subgraph_center`.
- [ ] **`beans.score.evaluate(con)`** writes to `model_card` (key → JSON):
  - `e1`: ARI / homogeneity / completeness vs `labels_address.entity_id`, CIOH-only vs CIOH+embeddings
  - `e2`: PR-AUC, precision@100
  - `e3`: per-class precision/recall/F1, confusion matrix, **peel recall by chain length**
  - `e4`: recall@200 of *hidden* illicit wallets (illicit, not in seeds)
  - `fusion`: PR-AUC, precision@50, ECE, reliability-diagram bins, global feature importance
  - `ablation`: fusion PR-AUC **with vs without network features** (this is the headline "correlation helps" number)
  - `meta`: dataset name, counts, train/test sizes, timestamp
- [ ] Report the metrics on the **demo** preset AND on a second dataset generated with a different seed (train on one, score the other).
- [ ] Tests `tests/test_ml_pipeline.py`: `run_all` on the tiny DB populates every table; every alert validates as `Alert`; `labels_*` columns never appear in the feature matrices (assert on column names).

## After CP3: support integration
Tune thresholds so the top 20 alerts in the demo look convincing and varied (peel, ransomware, mixing, network, seed proximity). Fix bugs Kavya finds in the UI.

---

## Definition of done
```bash
make install && make test
make pipeline-tiny                      # runs ingest → graph → score → eval without errors
.venv/bin/python -c "import duckdb; c=duckdb.connect('data/beans.duckdb'); print(c.sql('select severity,count(*) from alert group by 1')); print(c.sql('select key from model_card'))"
```

## Prompt to paste into your AI agent
> You are working in the BEANS repo on branch `dhairya`. Read `TASKS_DHAIRYA.md`, `docs/CONTRACTS.md`, `beans/schema.py`, `beans/store/ddl.sql` and `MASTER_ROADMAP.md` sections 6, 7 and 13. Implement the tasks in `TASKS_DHAIRYA.md` in checkpoint order. Only create or modify files under the paths listed as "You own". Never change shared files without asking me. Keep `beans.score.run_all` and `beans.score.evaluate` signatures exactly. Never use `labels_address` / `labels_tx` columns as features: they are only targets and evaluation data, and you should split train/test by entity_id. Everything must run offline on CPU with Python 3.12 (scikit-learn, lightgbm, shap, networkx/igraph). Every alert row must validate against `beans.schema.Alert`. After each task, run `make test`, commit, and tick the checkbox in `TASKS_DHAIRYA.md`.
