# BEANS — Production Hardening & Advanced Forensics Master Plan

**Objective:** Implement the real-world validation, operational monitoring, investigator ergonomics, and advanced AI features to make BEANS an indisputable, production-grade intelligence standard for NTRO.

---

```
                                  MASTER EXPANSION ARCHITECTURE
 ┌────────────────────────────────────────────────────────────────────────────────────────────────┐
 │                                   1. REAL-WORLD DATA VALIDATION                                │
 │  • Elliptic Dataset (MIT/IBM 203k TXs) Ingestion & Evaluation Benchmark (Roadmap C7)          │
 ├───────────────────────────────┬────────────────────────────────┬───────────────────────────────┤
 │     2. CONTINUOUS MONITORING  │      3. INVESTIGATOR & LEGAL   │      4. DEEP ML & AI ENGINES  │
 │  • Taint-Watch Re-Alerting    │  • Analyst/Supervisor Roles    │  • E5: GraphSAGE + GNNExplain │
 │  • SIEM Webhook Dispatch      │  • Section 94 Supervisor Sign  │  • Wallet Software Fingerprint│
 │  • Cross-Case Watchlists      │  • Graph Snapshot in PDF Dossier│ • Multi-Dataset Typology Pool│
 │  • Standalone Mempool Sniffer │  • Hindi BNSS Legal Drafts     │  • Counterfactual XAI Reasons │
 └───────────────────────────────┴────────────────────────────────┴───────────────────────────────┘
```

---

## 📋 High-Level Work Breakdown & Sprints

### 🟢 Sprint 1: Real-World Data (Elliptic) & Taint-Watch Monitoring *(Highest Priority)*
1. **Elliptic Dataset Ingestion & Validation Benchmark (Roadmap C7):**
   - Loader for the Kaggle/MIT Elliptic Bitcoin dataset (`elliptic_txs_classes.csv`, `elliptic_txs_edgelist.csv`, `elliptic_txs_features.csv`).
   - Run E3 typology & Fusion evaluation on the 203,769 real transactions; report out-of-fold PR-AUC and illicit detection rate in Model Card.
2. **Active Taint-Watch Re-Alerting Engine (`beans/alerting/watchdog.py`):**
   - When a wallet is tagged `PASSIVE_TAINT_MONITOR`, store in DuckDB `watched_wallets`.
   - When `beans watch` ingests new transaction batches, immediately check for movements from watched wallets and raise high-priority `"DORMANT_TAINT_MOVED"` alerts.
   - Automatically dispatch re-alert notifications to configured SIEM webhooks (Wazuh / Splunk / Elastic).

---

### ⚖️ Sprint 2: Roles, Supervisor Sign-Off & Legal Evidence Packaging
3. **Analyst & Supervisor Roles + Audit Sign-Off (Roadmap C6):**
   - Simple, offline role-based access (`ANALYST`, `SUPERVISOR`, `ADMIN`).
   - Two-step legal draft approval: Analyst drafts a Section 94 BNSS or Freeze request $\rightarrow$ Supervisor reviews, approves, and cryptographically signs it before export.
4. **Visual Graph Snapshot in PDF Evidence Packs & BNSS Drafts:**
   - Server-side Matplotlib/Graphviz headless SVG/PNG snapshot generation for the evidence subgraph.
   - Embed the visual money trail diagram directly into the WeasyPrint PDF evidence dossier and legal notice drafts.
5. **Bilingual Support: Hindi Section 94 BNSS Notice Drafts:**
   - Standard Hindi legal draft templates (*भारतीय नागरिक सुरक्षा संहिता, 2023 की धारा 94 के तहत अधियाचन सूचना*) for domestic Indian state cyber cells.

---

### 🧠 Sprint 3: Deep AI Engines (GraphSAGE, Fingerprinting, Counterfactual XAI)
6. **E5 Engine: GraphSAGE Neural Network + GNNExplainer (Roadmap C1):**
   - Lightweight, CPU-friendly PyTorch Geometric / GraphSAGE inductive graph convolutional model.
   - Outputs graph structural embeddings capturing complex non-linear laundering topology.
7. **Wallet Software Fingerprinting (`beans/features/fingerprint.py`):**
   - Group unlinked addresses by wallet implementation habits:
     - Specific fee-rate estimation patterns (e.g. Electrum vs. Core vs. Wasabi).
     - Output index shuffle behavior and change address script-type preference (e.g. P2WPKH vs. P2TR).
     - Round amount heuristics ($\text{modulo } 0.001\text{ BTC}$).
   - Clusters Tor-hopping syndicates that change IPs but use the same client software.
8. **Multi-Dataset Typology Pooling:**
   - Combine synthetic runs with diverse Darknet/Ransomware/Hack topologies in `fusion_training_set.parquet` to push E3 Macro-F1 $\ge 0.90$.
9. **Counterfactual Explainability ("What-If" Analysis):**
   - Compute minimum feature perturbation required to lower risk below 65 (e.g. *"Risk would drop to 42 if funds were not relayed through a Bulletproof ASN"*).

---

### ⚡ Sprint 4: Scale, Cross-Case Watchlists & Live Mempool Collector
10. **Cross-Case Watchlist Linker:**
    - Detect when an entity in a new alert is already part of an existing active Case File; alert investigators of syndicate overlap.
11. **1M-Row Ingestion Chunking:**
    - Streaming batching in `ForensicPipeline` (50k rows per chunk) with garbage collection to ingest 1,000,000+ rows under 4 GB RAM.
12. **Standalone Live Mempool Sniffer (`tools/mempool_sniffer.py`):**
    - Standalone Python asyncio script connecting to live Bitcoin P2P nodes, saving microsecond timestamped observations to `data/inbox/transactions_<timestamp>.csv` (keeping core BEANS 100% offline).

---

## 🛠️ Detailed Component Changes

### 1. Real Data Ingestion & Benchmark (`beans/ingest/elliptic.py`, `scripts/evaluate_elliptic.py`)
```python
# [NEW] beans/ingest/elliptic.py
class EllipticLoader:
    """Ingests and converts MIT/IBM Elliptic Bitcoin dataset to CanonicalRecord format."""
    @staticmethod
    def load_and_evaluate(elliptic_dir: Path, store: DuckStore) -> Dict[str, float]:
        # Maps 203k txs, creates edge flows, evaluates E3 and Fusion model
        ...
```

### 2. Taint Watchdog (`beans/alerting/watchdog.py`)
```python
# [NEW] beans/alerting/watchdog.py
class TaintWatchdog:
    """Monitors incoming transaction batches for movements of previously watched addresses."""
    @staticmethod
    def check_and_alert(records: List[CanonicalRecord], store: DuckStore) -> List[Alert]:
        # Queries DuckDB for addresses in watchlist
        # Generates DORMANT_TAINT_MOVED alert and triggers webhook dispatcher
        ...
```

### 3. Role-Based Sign-Off & Legal Generator (`beans/report/bnss.py`, `beans/api/routes/cases.py`)
```python
# [MODIFY] beans/report/bnss.py
def generate_bnss_draft(..., supervisor_signed: bool = False, supervisor_name: str = None, language: str = "en"):
    # Supports "en" and "hi" (Hindi)
    # Adds supervisor approval block and RFC 3161 digital signature seal
    ...
```

### 4. Graph Visual Snapshotter (`beans/report/graph_image.py`)
```python
# [NEW] beans/report/graph_image.py
class EvidenceGraphRenderer:
    """Renders high-resolution vector/PNG graph snapshots of suspect subgraphs for PDF inclusion."""
    @staticmethod
    def render_subgraph(nodes: List[Dict], edges: List[Dict], output_path: Path) -> Path:
        ...
```

---

## 🧪 Verification Plan

### Automated Test Suite:
```powershell
python -m pytest tests/ -v
```
- `tests/test_elliptic.py`: Tests Elliptic format ingestion and scoring parity.
- `tests/test_watchdog.py`: Tests `PASSIVE_TAINT_MONITOR` wallet movement detection and SIEM trigger.
- `tests/test_bnss_roles.py`: Tests supervisor approval gating, Hindi legal drafts, and graph snapshot embedding.
- `tests/test_fingerprint.py`: Tests software habit wallet clustering.

### Manual Verification:
1. Run demo with watched wallet and drop a transaction spending from it into `data/inbox/`. Verify that a `"DORMANT_TAINT_MOVED"` alert triggers.
2. In the UI, log in as Analyst, create a draft $\rightarrow$ verify Supervisor approval gate $\rightarrow$ export PDF containing the embedded Link Graph visual diagram.
3. Switch language toggle to Hindi on the legal draft and verify the Section 94 BNSS template formatting.

---

*Would you like to approve this implementation plan to begin execution?*
