# BEANS Next-Gen Implementation Plan (with "Alive" Dynamic Graph & Production UI)
**Objective:** Integrate the 4 strategic pillars, fine-tuned Laya Decision Engine (`NandhaKishorM/laya`), and a top-tier **production UI with living, physics-animated link graphs** on top of the latest `penultimate` branch.

---

## 🎨 Special Focus: "Alive" Cyber-Intelligence UI & Dynamic Graph

```
                            "ALIVE" DYNAMIC FORENSIC GRAPH
 ┌───────────────────────────────────────────────────────────────────────────┐
 │  🟢 Floating & Breathing Nodes (Organic physics forces with gentle drift) │
 │  ⚡ Animated Flow Particles on Edges (Visualizing real-time BTC movement) │
 │  🔴 Pulsing Threat Halos on Illicit Seeds & High-Risk Wallets             │
 │  🔺 Shimmering Geo-IP Triangles with live relay ping waves                │
 │  ✨ Neon-Glow Evidence Paths linking suspect wallets back to source seeds │
 └───────────────────────────────────────────────────────────────────────────┘
```

---

## 📌 Phase 0: Baseline Verification & Sync

- [ ] **Task 0.1: Pull & Verify Latest `penultimate` Commit**
  - Pull latest commit (`cc4cd73`+) from `origin/penultimate`.
  - Verify clean working tree and confirm `models/e3_txclass.joblib`, `models/fusion.joblib`, and `data/geoip/*.mmdb` are intact.
  - Run `pytest tests/ -v` to ensure 100% baseline green.

- [ ] **Task 0.2: Confirm DuckDB Engine Role**
  - **Yes, DuckDB is our core in-process analytical engine (`data/beans.duckdb`).**
  - DuckDB powers all multi-format transaction storage, quarantine logs, wallet risk profiles, and alert index tables at **3,300+ rows/sec**.

---

## 🧠 Phase 1: Fine-Tuning Laya Decision Engine (`NandhaKishorM/laya`)

- [ ] **Task 1.1: Environment & Checkpoint Integration**
  - Install local Laya engine runtime (ONNX / local PyTorch inference with zero cloud dependency).
  - Create `beans/decision/` module for sub-35ms non-autoregressive decision inference.

- [ ] **Task 1.2: Fine-Tuning Laya on Forensic & Legal Actions**
  - Fine-tune Laya's decision head on our synthetic + operational dataset across 5 critical decision categories:
    1. `IMMEDIATE_FREEZE_REQUISITION` (Exchange deposit within $\le 30\text{ min}$ of ransomware payout).
    2. `DISPATCH_SECTION_91_NOTICE` (Indian KYC exchange endpoint detected).
    3. `ESCALATE_TO_FIU_IND` (Cross-border layering $\ge 1\text{ BTC}$ via high-risk ASN).
    4. `PASSIVE_TAINT_MONITOR` (Unspent cold wallet hops).
    5. `FALSE_POSITIVE_DISMISS` (Known merchant change or mining pool payout).

- [ ] **Task 1.3: Pipeline & UI Action Card Integration**
  - Hook Laya inference into `beans/score/run.py` to tag every alert with a deterministic `recommended_action`.
  - Add **One-Click Action Cards** to the React `AlertTriage.jsx` component.

---

## 🌟 Phase 2: Production UI & "Alive" Dynamic Link Graph

- [ ] **Task 2.1: Living Physics Canvas & Floating Dynamics**
  - Upgrade Cytoscape canvas with smooth physics damping (Euler / CoSE-Bilkent) so nodes gently breathe, float, and drift organically instead of staying static.
  - Add floating triangles (IPs), floating circles (Wallets), and glowing diamonds (Transactions).

- [ ] **Task 2.2: Animated Flow Particles & Edge Energy**
  - Implement animated dashed particle streams or WebGL flow particles running along edges to visibly show the direction and velocity of Bitcoin funds.

- [ ] **Task 2.3: Pulsing Threat Halos & Shimmering Nodes**
  - Add radiating pulse animations (CSS / canvas shaders) on Seed nodes, Critical alerts, and Bulletproof ASNs.
  - Add interactive ripple shockwaves when a node is clicked or expanded.

- [ ] **Task 2.4: Production UI Design System Overhaul**
  - Refine typography with crisp Inter / JetBrains Mono font pairing.
  - Add frosted glass backdrop blurs, refined status badges, dark/light intelligence mode switch, and tactile card micro-interactions.
  - Canvas **Lasso Multi-Select Tool** to circle 10+ nodes and batch-assign to a Case File.

---

## 🚀 Phase 3: Pillar 1 — Advanced Graph AI & Privacy Bypass

- [ ] **Task 3.1: Taproot (P2TR) & PayJoin (BIP 78) Script Detectors**
  - Implement script-path branch recognition in `beans/features/extractors.py` to prevent false clustering on Taproot multi-sigs and PayJoin transactions.

- [ ] **Task 3.2: Cross-Chain Bridge & Swap Indicators**
  - Add signature detection for known decentralized bridge deposit protocols (Thorchain, FixedFloat, SideShift, BTC-XMR atomic swap contracts).

---

## 📡 Phase 4: Pillar 2 — Real-Time P2P Sniffer Daemon

- [ ] **Task 4.1: Lightweight P2P Mempool Listener (`beans/p2p/`)**
  - Build asynchronous P2P socket client connecting to 50+ public Bitcoin full nodes.
  - Listen for live `inv` (inventory) and `tx` broadcast packets, logging peer IP and microsecond arrival timestamps ($\Delta t$).

- [ ] **Task 4.2: Dandelion++ Stem/Fluff Origin Estimator**
  - Calculate diffusion asymmetry vectors to distinguish random stem forwarding from true broadcast origin.

---

## ⚖️ Phase 5: Pillar 3 — Indian Law Enforcement Notice Automation

- [ ] **Task 5.1: Section 91 CrPC / Section 94 BNSS Generator**
  - Implement `beans/report/legal_notices.py` to auto-populate standard requisition forms for Indian registered VASPs (WazirX, CoinDCX, CoinSwitch, ZebPay) and international exchanges (Binance).

- [ ] **Task 5.2: Automated FIU-IND Suspicious Transaction Report (STR)**
  - Add XML/JSON export formatted according to the Financial Intelligence Unit - India (FIU-IND) FINnet reporting gateway schema.

- [ ] **Task 5.3: RFC 3161 Cryptographic Timestamping**
  - Sign exported forensic evidence bundles with SHA-256 and local agency cryptographic timestamp tokens.

---

## ⚡ Phase 6: Pillar 4 — SIEM & Alert Webhooks

- [ ] **Task 6.1: SIEM / Wazuh Webhook Exporters**
  - Add background alert dispatcher pushing `CRITICAL` alerts to SIEM webhooks (Wazuh, Elastic, Splunk, MISP).

---

## ✅ Phase 7: Verification & Final Polish

- [ ] **Task 7.1: End-to-End Test Suite Execution**
  - Run `pytest tests/ -v` covering all new modules (Laya decisions, P2TR heuristics, legal templates, sniffer).
- [ ] **Task 7.2: UI 60 FPS Performance & Throughput Benchmark**
  - Verify 60 FPS fluid rendering on the alive graph with 1,000+ floating elements and throughput $\ge 3,000\text{ rows/sec}$.
