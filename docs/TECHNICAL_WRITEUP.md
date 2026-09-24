# BEANS: Technical Write-up
**Bitcoin Encryption, Analysis & Network Security** · SIH 2026 · Problem Statement 26146 (NTRO)
*AI-Powered Monitoring & Analysis of Bitcoin Transaction Traffic*

> Status: 24 Sep, 17:00. Every number below was measured by the pipeline itself (`models/model_card.json`, regenerated on each run). Fusion and classifier metrics are out-of-fold, grouped by entity.

---

## 1. Problem and approach

Bitcoin is pseudonymous. Illicit actors (ransomware, darknet markets, extortion, laundering) move value through freshly generated addresses, mixing and peel chains. Blockchain analysis alone shows *what moved where*. The network layer shows *who broadcast it, from where, and when*. The problem statement asks for an **offline** system that joins those two layers, applies ML (not only rules) and produces **ranked, explainable, confidence-scored leads**.

BEANS answers this with one pipeline:

```
CSV / JSON / XML ──► ingest + validate ──► offline GeoIP/ASN enrichment ──► DuckDB
      ──► heterogeneous graph (IP ↔ TX ↔ wallet) + first-spy attribution
      ──► E1 clustering · E2 anomaly · E3 peel/mix · E4 seed risk propagation
      ──► fusion → risk (0–100) + confidence + SHAP reasons ──► ranked alerts
      ──► dashboard (alerts · link graph · timeline · geo map · entity 360 · cases) + PDF evidence packs
```

Design principles:
1. **Rules produce features and models decide.** Structural signatures (equal-value outputs, peel ratios, impossible travel) are inputs to trained models, not verdicts.
2. **Every flag is explained.** Each alert carries its engine scores, top feature contributions and the underlying evidence (transaction, first-relaying IP, path to a seed wallet).
3. **Fully offline.** No runtime network access. GeoIP databases, the UI build and all dependencies ship with the release (§7).

## 2. Data

### 2.1 Input schema
One record = one network observation of one transaction:
`timestamp, src_ip, src_port, dst_ip, dst_port, txid, input_addresses[], input_amounts[], output_addresses[], output_amounts[], fee, script_type` (+ `geo_country`/`asn`, filled by enrichment when absent). The same TXID may appear several times, relayed by different peers.
All three formats (CSV with `;`-joined arrays, JSON array/NDJSON, XML) are parsed by streaming readers into one canonical schema (`beans/schema.py::CanonicalRecord`). Invalid rows go to quarantine with a reason instead of stopping the run.

### 2.2 Enrichment
Offline IP → country and IP → ASN from **DB-IP Lite** (`.mmdb`, CC BY 4.0, bundled). ASNs are typed (residential / datacenter / VPN / Tor exit / bulletproof) from offline snapshot lists. Because the free country database has no coordinates, the map uses country centroids.

### 2.3 Synthetic dataset
The PS provides no dataset ("Dataset Link: Nil"), so BEANS includes a labelled generator (`beans synth`). It simulates legitimate actors (retail users with change outputs, exchanges with consolidations and batch payouts) and illicit typologies (ransomware collection → split → mix, peel chains, CoinJoin-like equal-denomination transactions, fan-out structuring and others), each with network behaviour (hosting/Tor/VPN relays, off-hours broadcasting). The generator writes ground-truth labels and a **seed list containing only a fraction of the illicit wallets**. The rest stay hidden so propagation can be evaluated on wallets the model was never told about.
Generator v2 (`beans/synth/sim.py`) is an event-driven simulation with a real UTXO ledger: every input spends an earlier output, so flows form a connected graph. Legitimate actors are miners, exchanges (withdrawal batches, deposit sweeps, cold→hot refills), merchants, retail users and privacy users who use CoinJoin legitimately. Illicit actors cover seven typologies. IPs are sampled from real prefixes of the bundled DB-IP databases per ASN type, and each transaction is seen by 1–4 relaying peers. Hardness settings: exchange payouts look like smurfing fan-outs, legitimate users also CoinJoin, 15% of illicit transactions have their origin IP unobserved, and some residential IPs are shared behind NAT.

Demo dataset (`--n-tx 5000 --seed 42`): 4,032 transactions, 11,897 network observations, 13,542 wallets, of which 891 (6.6%) are illicit, belonging to 30 illicit entities (6 ransomware operators, 8 peel-chain operators, 3 hack launderers, a darknet market with 3 vendors, 3 smurfers, 4 round-trippers, 2 dusters). Seeds: 17 addresses from 9 of the 30 illicit entities. The other 21 entities are never revealed to the model. Transaction shapes: 464 peel hops, 225 fan-out, 109 fan-in, 45 round-trip, 37 CoinJoin, 3,152 normal.

## 3. Correlation: linking the network layer to wallets

- **First-spy attribution:** for each TXID, the earliest relaying IP is the most likely originator. Confidence grows with the gap to the second relay. The originating IP is linked to the transaction's **input** wallets (the spender).
- **Network features per wallet:** number of distinct relaying IPs, countries and ASNs; share of Tor/VPN/hosting relays; **geo-velocity** (consecutive broadcasts of the same wallet's spends from locations further apart than 900 km/h allows = impossible travel); non-standard ports; off-hours ratio.
- **Limits, stated openly:** first-spy is probabilistic. Dandelion++ and Tor relaying weaken it, so it's a weighted feature with a confidence value, never proof of identity.

## 4. Models (the four PS focus areas)

| PS focus area | BEANS engine | Method |
|---|---|---|
| Entity clustering (common-input-ownership + graph embeddings) | E1 | CIOH union-find over transaction inputs, **excluding transactions E3 classifies as CoinJoin** (otherwise unrelated participants merge) + conservative change heuristic (single full-precision output) + peel-chain change heuristic (inside chains of ≥ 3 linked peel hops the large output is change); truncated-SVD embeddings of the normalised cluster flow graph + behaviour → HDBSCAN merge *suggestions* |
| Anomaly detection | E2 | Isolation Forest on transaction and wallet features (unsupervised, needs no labels) |
| Peeling-chain / mixing detection | E3 | Structural features (equal-output groups, peel ratio and chain length, fan-in/out, time-to-respend) → LightGBM multiclass (normal / peel / coinjoin / fan-out / fan-in / round-trip), no rule fallback |
| Risk scoring propagated from seed wallets | E4 | Personalised PageRank from seed wallets on the value-weighted flow graph + decayed taint; path to nearest seed kept as evidence |

**Fusion.** Engine outputs and network features feed a combined model that outputs P(illicit). Risk = 100 · P. Confidence reflects calibration, engine agreement and evidence completeness. Severity bands: CRITICAL ≥ 85, HIGH ≥ 65, MEDIUM ≥ 40. The fusion model is LightGBM over 40 wallet features (behaviour, E2 anomaly, E3 probabilities aggregated per wallet and per cluster, E4 PPR/taint/hops, network features). It uses 5-fold StratifiedGroupKFold by entity. Inside each fold, a model is fitted on 75% of the training entities and **isotonic calibration** on the other 25%. The five calibrated fold models are persisted and averaged for data without labels. A second LightGBM assigns the typology shown on each alert. Alerts are raised per CIOH cluster (its riskiest wallet) when calibrated P ≥ 0.4.

**Leakage control.** Ground-truth labels are used only as training targets and for evaluation, never as features. Train/test splits are made by entity, so one actor's wallets never appear on both sides.

## 5. Explainability

For every alert BEANS stores and shows:
- **Why flagged:** plain-English reasons generated from the strongest contributing features (e.g. *"Participated in a CoinJoin-like transaction with 10 equal-value outputs"*, *"Relayed through a Tor exit in CH"*).
- **Feature contributions:** per-alert SHAP values from `shap.TreeExplainer` on the fusion model (log-odds), shown as signed bars (red = raises risk, green = lowers it). Reason sentences are generated only from features with positive contributions.
- **Engine scores:** the contribution of each engine.
- **Evidence:** the transaction, the first-relaying IP with its confidence, and the path to the nearest seed wallet. The link graph highlights this path.
- **Model card:** global metrics and feature importance. The dashboard shows only measured values and states plainly when no evaluation has run.

## 6. Investigator workflow (dashboard)

Overview KPIs → ranked **alert triage** (filters, search, verdicts) → **Entity 360** (flows, relaying IPs, cluster members) → **link graph** (expand around any wallet/TX/IP, risk filter, evidence-path highlight) → **timeline** (follow one wallet's transactions in order) → **geo map** (relay locations, impossible-travel arcs) → **cases** (group entities, export evidence packs).
Analyst verdicts (*confirmed* / *false positive*) are stored as labelled feedback for the next training run. New seed lists can be uploaded and risk re-propagated over the whole dataset without losing analyst verdicts. Every action is written to an audit log.

**Evidence packs** (PDF / JSON / Markdown) contain the case, all findings with reasons, SHAP values and evidence, the SHA-256 of every ingested source file, the audit trail, and a SHA-256 computed over the evidence itself so the pack can be verified later.

## 7. Offline deployment (Linux)

| Path | How | Verified |
|---|---|---|
| Docker | `docker build` once online → `docker run --network none -p 8000:8000 beans` | ✅ `make docker-offline-test`: image started with only a loopback interface; demo data generated and scored, all API routes + dashboard served, PDF export works, outbound internet blocked |
| Bare metal | `make bundle` once online → copy `beans-offline-<ver>.tar.gz` → `./install_offline.sh && make demo` | ✅ installed from the bundled wheelhouse and ran the pipeline in a clean container with `--network none` |

Stack: Python 3.12, DuckDB (embedded, single file), NetworkX, scikit-learn, FastAPI, React + Cytoscape.js + ECharts (pre-built into `ui/dist`, so no Node.js is needed to run), WeasyPrint for PDF. The world map ships inside the UI bundle (Natural Earth outlines); no CDN or remote fonts.

## 8. Results (demo dataset, measured)

All numbers are reproducible bit-for-bit: inputs are explicitly ordered and LightGBM runs in deterministic mode.

| Engine | Metric | Value | Reference |
|---|---|---|---|
| Fusion | PR-AUC, out-of-fold by entity | **0.931** | random ranking = 0.066 |
| Fusion | ROC-AUC | 0.987 | |
| Fusion | Precision@50 | **0.98** | |
| Fusion | Recall of illicit wallets at P ≥ 0.5 | 0.708 | |
| Fusion | Expected calibration error | **0.013** | |
| **Ablation** | PR-AUC **without** network-layer features | 0.898 | with = 0.931 → the network ↔ chain correlation adds value |
| Alert list | Alerts that are illicit | **95 %** (285/300) | top 10: 100 % |
| Alert list | Illicit entities with ≥ 1 alert | **100 %** (30/30) | |
| E3 | Macro-F1, grouped CV | **0.993** | peel · CoinJoin · round-trip · fan-in/out all ≥ 0.97 |
| E1 | Homogeneity (no cluster mixes two actors) | 1.00 | all wallets: 0.9985 |
| E1 | Completeness (an actor's wallets in one cluster) | 0.58 | was 0.47 before the peel-chain change heuristic |
| E4 | Hidden (non-seed) illicit wallets reached from seeds | 0.18 | legitimate wallets reached: 0.10 |
| Typology | Accuracy on illicit wallets, grouped CV | 0.69 | |
| Throughput | Ingest + all engines + training, 11.9k observations | **11 s** | scoring ≈ 3,300 rows/s, linear up to 117k rows / 1.4 GB (docs/BENCHMARK.md) |

Most important features (mean |SHAP|): cluster share of Tor/VPN/bulletproof relays, wallet share of risky relays, round-trip probability, cluster size, anomaly score, fan-out probability, equal-output share, reverse PPR to seeds.

**What we tried and rejected.** Cluster-level seed features ("shares a cluster with a seed", cluster taint) raised entity coverage but cut alert precision from 95 % to 87–90 %, because the model over-trusted cluster membership. They are used only for evidence and the E4 metric.

**Reading these numbers honestly.** The data is synthetic and generated by the same team, so absolute scores are optimistic. The meaningful signals are *relative*: the network-layer ablation (+0.033 PR-AUC), the grouped (by entity) evaluation, calibration, and the weaker engines, which we report rather than hide (E1 completeness, E4 reach, typology).

## 8b. Operational features

- **Unfamiliar files:** a YAML column mapping (CLI `--mapping`, API and UI upload) handles renamed columns, epoch times, satoshi amounts and nested input/output objects. Rows missing required fields are quarantined, never filled with placeholders (docs/DATA_FORMATS.md).
- **Analyst feedback loop:** *Confirm* / *False positive* verdicts override labels in the next training run. On unlabelled operational data they are added to the saved training set (weight 5) and the models retrain.
- **Monitoring mode:** `beans watch <folder>` ingests and scores every new file dropped in.
- **Exports:** Neo4j bulk-import CSVs and a STIX 2.1 bundle of wallet and first-relay-IP indicators.

## 9. Limitations and responsible use

- Trained and evaluated on **synthetic** data only. Real-world performance must be re-established on labelled operational data.
- CIOH is broken by CoinJoin and PayJoin. BEANS excludes detected CoinJoins, but will miss undetected ones.
- First-spy attribution is a probabilistic lead, not identification.
- Outputs are **investigative leads for analyst review**, not determinations of guilt. Analyst verdicts and the audit log are part of the design.

## 10. How to run

```bash
make install && make demo        # http://127.0.0.1:8000
make test                         # pytest suite
make docker-offline-test          # proves the product runs with networking disabled
```

## References

The methods, datasets and tools cited in this write-up are listed with verified links in [`docs/REFERENCES.md`](REFERENCES.md).
