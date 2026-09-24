# BEANS: Technical Write-up
**Bitcoin Encryption, Analysis & Network Security** · SIH 2026 · Problem Statement 26146 (NTRO)
*AI-Powered Monitoring & Analysis of Bitcoin Transaction Traffic*

> Status: draft (24 Sep, 14:40). Sections marked **⟨TO FILL⟩** are completed from the evaluation run (`models/model_card.json`) at the 20:30 feature freeze. No number appears in this document unless it was measured.

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
**⟨TO FILL: final typology table, dataset sizes, illicit share, hardness settings⟩**

## 3. Correlation: linking the network layer to wallets

- **First-spy attribution:** for each TXID, the earliest relaying IP is the most likely originator. Confidence grows with the gap to the second relay. The originating IP is linked to the transaction's **input** wallets (the spender).
- **Network features per wallet:** number of distinct relaying IPs, countries and ASNs; share of Tor/VPN/hosting relays; **geo-velocity** (consecutive broadcasts of the same wallet's spends from locations further apart than 900 km/h allows = impossible travel); non-standard ports; off-hours ratio.
- **Limits, stated openly:** first-spy is probabilistic. Dandelion++ and Tor relaying weaken it, so it's a weighted feature with a confidence value, never proof of identity.

## 4. Models (the four PS focus areas)

| PS focus area | BEANS engine | Method |
|---|---|---|
| Entity clustering (common-input-ownership + graph embeddings) | E1 | CIOH union-find over transaction inputs, **excluding transactions E3 classifies as CoinJoin** (otherwise unrelated participants merge) + conservative change heuristic; graph embeddings for merge suggestions **⟨TO FILL: embedding method⟩** |
| Anomaly detection | E2 | Isolation Forest on transaction and wallet features (unsupervised, needs no labels) |
| Peeling-chain / mixing detection | E3 | Structural features (equal-output groups, peel ratio and chain length, fan-in/out, time-to-respend) → supervised classifier **⟨TO FILL: final model⟩** |
| Risk scoring propagated from seed wallets | E4 | Personalised PageRank from seed wallets on the value-weighted flow graph + decayed taint; path to nearest seed kept as evidence |

**Fusion.** Engine outputs and network features feed a combined model that outputs P(illicit). Risk = 100 · P. Confidence reflects calibration, engine agreement and evidence completeness. Severity bands: CRITICAL ≥ 85, HIGH ≥ 65, MEDIUM ≥ 40. **⟨TO FILL: fusion model + calibration method⟩**

**Leakage control.** Ground-truth labels are used only as training targets and for evaluation, never as features. Train/test splits are made by entity, so one actor's wallets never appear on both sides.

## 5. Explainability

For every alert BEANS stores and shows:
- **Why flagged:** plain-English reasons generated from the strongest contributing features (e.g. *"Participated in a CoinJoin-like transaction with 10 equal-value outputs"*, *"Relayed through a Tor exit in CH"*).
- **Feature contributions:** per-alert SHAP values, shown as signed bars (red = raises risk, green = lowers it). **⟨TO FILL: confirm TreeExplainer on the fusion model⟩**
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

## 8. Results

**⟨TO FILL from `models/model_card.json`⟩**

| Engine | Metric | Value |
|---|---|---|
| E1 clustering | Adjusted Rand Index vs ground-truth entities | |
| E2 anomaly | PR-AUC / precision@100 | |
| E3 peel/mix | macro-F1 | |
| E4 propagation | recall of hidden illicit wallets (seeds = 20 %) | |
| Fusion | PR-AUC, precision@50, calibration error | |
| Ablation | fusion PR-AUC with vs without network features | |
| Throughput | rows/s ingest + score on an 8-core laptop | |

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
