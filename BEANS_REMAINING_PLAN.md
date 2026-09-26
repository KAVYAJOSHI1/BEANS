# BEANS — Remaining Implementation Plan (Post-Merge)

**Baseline Status:** ✅ **Task 1.1 Complete** — `origin/kavya` and `origin/penultimate` are synced at commit `3ecf0d2`.

**Status (2026-09-26): all sprints implemented on `kavya`.** 34 tests pass. Changes from the plan text:
- The attribution list (`known_entities`) was added. The freeze and Section 94 rules need to know which addresses belong to exchanges.
  Synthetic datasets ship `known_entities.csv`; real data needs an uploaded list (`beans known-entities FILE`, or the Rules & Integrations page).
- Rule 5 is `REVIEW_LIKELY_BENIGN`: it suggests a verdict; nothing is auto-dismissed. Directives cite the rule and its
  checked values; SHAP appears as "model support" (SHAP has no thresholds).
- The FIU layering rule measures BTC over the wallet's CIOH cluster (launderers split funds across many small wallets).
- The webhook module is `beans/alerting/webhooks.py`: `beans/export/` would shadow the existing `beans/export.py`.
- Motion on graphs above 300 nodes animates only the flows touching risk ≥ 65 wallets, at a lower tick rate.
  Measured in headless Chromium (software rendering): 60 fps on a 56-node view with motion or physics; 42 fps on the 839-node default view (60 with motion off).

---

## 📋 Remaining Sprints & Task Breakdown

```
 ┌───────────────────────────┐      ┌───────────────────────────┐      ┌───────────────────────────┐
 │ SPRINT 1: "ALIVE" GRAPH   │ ───► │ SPRINT 2: ACTION CARDS    │ ───► │ SPRINT 3: BNSS & FIU      │
 │  • Animated Edge Flows    │      │  • Deterministic Engine   │      │  • Sec 94 BNSS Requisition│
 │  • Pulsing Threat Halos   │      │  • One-Click Action Cards │      │  • FIU Referral Dossier   │
 │  • Optional Physics Toggle│      │  • Direct Rule Citations  │      │  • RFC 3161 Timestamps    │
 └───────────────────────────┘      └───────────────────────────┘      └───────────────────────────┘
                                                                                      │
                                                                       ┌──────────────▼────────────┐
                                                                       │ SPRINT 4: SIEM & DARK UI  │
                                                                       │  • SIEM/STIX 2.1 Webhooks │
                                                                       │  • Dark Mode & Lasso Tool │
                                                                       └───────────────────────────┘
```

---

### 🎨 Sprint 1: "Alive" Visual Link Graph *(High Visual Impact)*
- [x] **Task 1.2: Animated Edge Flow Particles (`ui/src/components/LinkGraph.jsx`)**
  - Implement dynamic `line-dash-offset` animation on Cytoscape directed edges to visualize the movement, direction, and velocity of Bitcoin funds.
- [x] **Task 1.3: Pulsing Threat Halos & Node Rings**
  - Add continuous animated Cytoscape `underlay` glow rings around known Seed wallets, Critical alerts, and Bulletproof ASNs (capped at $\le 300$ visible nodes for steady 60 FPS).
- [x] **Task 1.4: "Live Physics" Toggle**
  - Add a toggle button in the Link Graph controls (default: OFF so nodes remain stationary and easy to click for evidence review).

---

### 🧠 Sprint 2: Deterministic Action Directives & Action Cards *(Core Intelligence)*
- [x] **Task 2.1: Action Directives Engine (`beans/decision/actions.py`)**
  - Tag every alert with an explainable, legally defensible recommended action:
    1. `IMMEDIATE_FREEZE_DRAFT` (High-risk payout reaching exchange deposit $\le 30\text{ min}$).
    2. `DRAFT_SECTION_94_BNSS` (Known Indian KYC exchange endpoint detected).
    3. `FIU_REFERRAL_PACK` (Layering $\ge 1\text{ BTC}$ via bulletproof ASN).
    4. `PASSIVE_TAINT_MONITOR` (Unspent dormant hops).
    5. `BENIGN_CHANGE_DISMISS` (Change output / mining pool sweeps).
  - Every action directly cites the mathematical rule and SHAP threshold that triggered it.
- [x] **Task 2.2: One-Click Action Cards in Alert Triage (`ui/src/components/AlertTriage.jsx`)**
  - Add interactive action buttons to alert cards (e.g. `[ Draft Section 94 BNSS Notice ]`, `[ Export Referral Pack ]`).

---

### ⚖️ Sprint 3: Indian Law Enforcement Notices & Evidence Sealing *(Legal & Defense)*
- [x] **Task 3.1: Section 94 BNSS Notice Generator (`beans/report/bnss.py`)**
  - Auto-generate formatted requisition notice drafts under **Section 94 of the Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023** for the Investigating Officer (IO) to sign.
  - Templates for Indian registered VASPs (CoinDCX, CoinSwitch, ZebPay) and international exchanges.
- [x] **Task 3.2: FIU-IND Intelligence Referral Pack Exporter**
  - Export structured JSON / PDF referral dossiers ready for law enforcement transmission to FIU-IND.
- [x] **Task 3.3: RFC 3161 Cryptographic Evidence Timestamping**
  - Implement local `openssl ts` timestamp token generation alongside the existing SHA-256 canonical hash manifest.

---

### 🌐 Sprint 4: SIEM Integrations & Production UI Overhaul *(Final Polish)*
- [x] **Task 4.1: SIEM & STIX 2.1 Webhook Dispatcher (`beans/export/webhooks.py`)**
  - Background dispatcher pushing `CRITICAL` alerts to SIEM webhooks (Wazuh, Elastic, Splunk, MISP).
- [x] **Task 4.2: Dark / Light Intelligence Theme & Canvas Lasso**
  - Add dark mode styling toggle (`slate-900` / `slate-50`) and canvas lasso tool to multi-select nodes and batch-assign to a Case File.
