# Blockchain Forensics Intelligence Framework – Approach Document

**Version:** 1.0  
**Last Updated:** September 2026  
**Platform:** Linux (Ubuntu 20.04+)  
**Purpose:** Investigator-led financial crime detection using Bitcoin transaction + network metadata correlation

---

## Executive Summary

This framework enables financial crime investigators to correlate blockchain-layer data (wallet addresses, transactions, amounts) with network-layer observations (IP addresses, ports, geolocation, timing) to detect and prioritize suspicious entities and transactions.

**Core Philosophy:** Intelligence-led investigation, not algorithmic automation. Tools support human reasoning, capture domain expertise, and produce audit-trail evidence suitable for law enforcement handoff.

---

## Part 1: Problem Domain

### 1.1 Threat Landscape

**Bitcoin's Criminal Use:**
- Ransomware payments (LockBit, Cl0p, BlackCat)
- Darknet marketplace proceeds (silk road successors)
- Extortion & kidnapping payoffs
- Theft laundering (exchange hacks, private key compromises)
- Sanctions evasion, sanctions-connected networks

**Why Detection Fails:**
- Pseudonymous by design (no built-in KYC)
- Mixing services obscure transaction flow (CoinJoin, Tornado.cash)
- Rapid wallet churn (new addresses generated per transaction)
- Geographically distributed transactions (hard to track via traditional banking rails)
- Script obfuscation (multisig, timelocks, covenant scripts)

### 1.2 Investigation Gap

Law enforcement has blockchain data but **lacks correlated context**:
- See transaction TXIDs, wallet addresses, amounts ✓
- No systematic way to link wallets to IPs, ASNs, geolocation ✗
- No pattern library of known threat actors ✗
- No temporal analysis (when do bad actors move funds?) ✗
- No structured triage (which 100 flagged wallets to investigate first?) ✗

**This framework fills that gap.**

---

## Part 2: Architecture

### 2.1 Data Layers

#### Layer 1: Blockchain Data
**Source:** CSV/JSON export from blockchain explorer (Blockchair, blockchain.com) or live node scrape

**Fields:**
```
{
  "timestamp": "2024-01-15T14:32:00Z",
  "txid": "abc123...",
  "input_addresses": ["1A1z7agoat...", "1A1z7agoat..."],
  "output_addresses": ["1A1z7agoat...", "1A1z7agoat..."],
  "input_amounts": [0.5, 1.2],
  "output_amounts": [1.5, 0.2],
  "fee": 0.01,
  "script_type": "P2PKH|P2WPKH|P2WSH|P2SH",
  "block_height": 829640
}
```

#### Layer 2: Network Data
**Source:** P2P node traffic capture, ISP logs, or simulated metadata

**Fields:**
```
{
  "timestamp": "2024-01-15T14:32:00Z",
  "src_ip": "203.45.67.89",
  "dst_ip": "185.21.100.1",
  "src_port": 54321,
  "dst_port": 8333,  # Bitcoin P2P port
  "src_asn": "AS12345",
  "src_country": "CN",
  "dst_asn": "AS54321",
  "dst_country": "DE",
  "bytes_in": 1024,
  "bytes_out": 2048,
  "protocol": "TCP"
}
```

#### Layer 3: Correlation Metadata
**Source:** Manual investigation, OSINT, threat intelligence feeds

**Fields:**
```
{
  "wallet_address": "1A1z7agoat...",
  "associated_ips": ["203.45.67.89", "..."],
  "first_seen": "2024-01-01T00:00:00Z",
  "confidence": 0.8,
  "threat_classification": "RANSOMWARE|MIXING|EXCHANGE|UNKNOWN",
  "linked_incident": "LOCKBIT_2024_JAN",
  "notes": "Matches LockBit payment collection pattern",
  "source": "OSINT|LE_TIP|PREVIOUS_INVESTIGATION"
}
```

### 2.2 System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    INGESTION LAYER                          │
├─────────────────────────────────────────────────────────────┤
│  CSV/JSON Parsers → Blockchain Validator → Data Normalizer  │
│  (Timestamps, addresses, amounts, geolocation)              │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   STORAGE LAYER                             │
├─────────────────────────────────────────────────────────────┤
│  PostgreSQL                │  Neo4j (Graph DB)              │
│  ├─ Transactions           │  ├─ Wallet nodes              │
│  ├─ Network observations   │  ├─ IP nodes                  │
│  ├─ Wallet profiles        │  ├─ Transaction edges         │
│  └─ Correlation metadata   │  └─ Relationships (own/mixes) │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                  CORRELATION ENGINE                         │
├─────────────────────────────────────────────────────────────┤
│  ├─ Entity Clustering (wallets w/ same behavior)           │
│  ├─ Timeline Analysis (transaction sequencing)              │
│  ├─ Pattern Matching (known threat signatures)              │
│  ├─ Geolocation Tracking (IP jumps, behavioral anomalies)   │
│  └─ OSINT Integration (threat feeds, arrest records)        │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   SCORING & TRIAGE                          │
├─────────────────────────────────────────────────────────────┤
│  Investigator Confidence Scoring                            │
│  ├─ Pattern match score (0-100)                             │
│  ├─ Behavioral anomaly score (0-100)                        │
│  ├─ OSINT evidence count                                    │
│  └─ Final Risk Rating (CRITICAL|HIGH|MEDIUM|LOW)            │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    INVESTIGATION UI                         │
├─────────────────────────────────────────────────────────────┤
│  ├─ Alert Dashboard (ranked flags, evidence)                │
│  ├─ Network Graph (wallets, IPs, relationships)             │
│  ├─ Timeline View (transaction sequence, events)            │
│  ├─ Entity Card (wallet profile, linked entities)           │
│  └─ Case File (grouped incidents, annotations)              │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 Core Data Structures

#### Transaction Graph Node
```python
class Transaction:
    txid: str
    timestamp: datetime
    input_addresses: List[str]
    output_addresses: List[str]
    input_amounts: List[float]
    output_amounts: List[float]
    fee: float
    script_type: str
    block_height: int
    observed_ips: List[str]  # IPs that broadcast this tx
    risk_flags: List[str]
```

#### Entity Node
```python
class Entity:
    id: str
    type: "WALLET" | "IP" | "ASN"
    addresses: List[str]  # for wallets
    ips: List[str]  # for IP nodes
    first_seen: datetime
    last_seen: datetime
    transaction_count: int
    total_volume: float
    threat_score: float (0-100)
    classification: "RANSOMWARE" | "MIXING" | "EXCHANGE" | "UNKNOWN"
    linked_entities: List[str]
    osint_findings: List[dict]
```

#### Investigation Alert
```python
class Alert:
    id: str
    entity_id: str
    alert_type: "NEW_WALLET" | "RAPID_MOVEMENT" | "MIXING_DETECTED" | "GEO_ANOMALY"
    timestamp: datetime
    reason: str  # Human-readable explanation
    evidence: List[dict]  # Supporting data
    investigator_confidence: float (0-1)
    status: "OPEN" | "INVESTIGATING" | "RESOLVED" | "FALSE_POSITIVE"
    assigned_to: str (investigator name)
```

---

## Part 3: Investigative Methodology

### 3.1 Intelligence Categories

#### A. SIGINT (Signal Intelligence) – Network Layer
**What we track:**
- IP address churn (wallet broadcasts from multiple IPs over time)
- Geographic inconsistencies (wallet in US at 2 UTC, then CN at 3 UTC)
- ASN clustering (multiple suspicious wallets from same datacenter ASN)
- VPN/Proxy signatures (known VPN provider ASNs, datacenter markers)
- Port patterns (standard Bitcoin port 8333 vs. non-standard ports = suspicious)

**Detection logic:**
```
IF wallet_broadcast_from_N_different_countries_in_M_hours THEN geo_anomaly_flag
IF wallet_broadcast_from_known_vpn_asn THEN privacy_seeking_flag
IF wallet_broadcast_from_bulletproof_hoster THEN high_risk_flag
IF transaction_broadcast_only_from_exchange_ip THEN exchange_controlled_flag
```

**Investigator action:** Look up ASN reputation, cross-reference with known bad actor infrastructure, note timing patterns.

---

#### B. OSINT (Open Source Intelligence)
**What we correlate:**
- Blockchain explorer history (when first seen, total volume, mixing participation)
- Known threat actor databases:
  - Public seizure records (FBI, Europol announcements)
  - Ransomware payment trackers (Chainalysis, Elliptic public data)
  - Darknet marketplace archives (public forum scrapes)
  - Academic research (wallet clustering papers)
- Wallet naming conventions (exchange deposit patterns, CoinJoin signatures)
- Timeline correlation (did wallet activate during known ransomware campaign?)

**Detection logic:**
```
IF wallet_address_found_in_lockbit_payment_tracker THEN confirmed_ransomware
IF wallet_matches_tornado_cash_signature THEN mixing_detected
IF wallet_address_mentioned_in_arrest_record THEN connected_to_prosecution
```

**Investigator action:** Search threat intel databases, correlate with incident timelines, build attribution case.

---

#### C. Structural Analysis – Transaction Patterns
**What we analyze:**
- **Wallet clustering:** Which wallets always transact together? (likely same entity)
  - Input co-occurrence (same wallet inputs to multiple transactions)
  - Output co-occurrence (same wallet receives from multiple sources)
  - Timing synchronization (transactions in bursts)

- **Mixing signatures:**
  - CoinJoin participants (equal-value outputs, multiple inputs from unrelated sources)
  - Tornado.cash pattern (fixed denomination deposits, time-delayed withdrawals)
  - Chain mixing (A→B→C→D, breaking transaction history)

- **Circular flows:**
  - Wallet A sends to B, B sends to C, C sends back to A
  - Indicates coordination or self-laundering

- **Script type anomalies:**
  - Multisig wallets (2-of-3) suddenly becoming single-sig (change of control?)
  - Timelocks (delayed spending = suspicious custody arrangement?)

**Detection logic:**
```
IF wallet_participates_in_equal_value_transaction_splits THEN likely_coinjoin
IF transaction_inputs_all_different_sources_outputs_many_wallets THEN mixing_operation
IF transaction_circular_flow_detected THEN self_coordination_flag
```

---

#### D. Behavioral Pattern Recognition
**Known patterns by threat type:**

**Ransomware (e.g., LockBit):**
- Pattern: Initial hold (24-48h) → rapid subdivision → immediate mixing
- Timing: Transactions clustered during non-UTC business hours (actor time zone)
- Volume: Matches ransom demand (e.g., $50k demand → $50k tx)
- Mixing: Aggressive mixing within 6 hours (not typical hodler behavior)
- Cash-out: Sudden exchange deposits after holding

**Money Laundering (Traditional Wash):**
- Pattern: Placement (small test tx) → Layering (mixing, splitting) → Integration (exchange deposit)
- Timeline: Weeks-long operation
- Volume: Progressive size increases
- Geography: Hops through multiple jurisdictions

**Exchange Consolidation (Legitimate):**
- Pattern: Many small outputs → single large deposit
- Timing: Regular, predictable (weekly/monthly sweeps)
- Mixing: Absent
- Script type: Consistent patterns

**Investigator Action:** Match observed behavior to known patterns, score likelihood, escalate matches.

---

### 3.2 Investigation Workflow

#### Stage 1: Automated Flagging (Rule-Based)
```
For each new transaction:
  IF amount > threshold AND wallet_age < 24h THEN Flag_NEW_WHALE
  IF wallet_broadcasts_from_N_countries_in_6h THEN Flag_GEO_ANOMALY
  IF transaction_participates_in_mixing_signature THEN Flag_MIXING
  IF wallet_address_in_threat_intel_feed THEN Flag_THREAT_INTEL_HIT
  
Alert dashboard updated in real-time
```

---

#### Stage 2: Investigator Triage
```
Investigator opens Alert Dashboard:
  1. Review flagged transactions (sorted by risk score)
  2. Read automated reason for flag
  3. Check if false positive (exchange sweep, known legitimate entity)
  4. If suspicious → Open Case File
```

---

#### Stage 3: Manual Investigation
```
For each flagged entity:
  
  Step 1: OSINT Lookup
    - Search wallet address in blockchain explorer
    - Search in threat intelligence feeds
    - Cross-reference with arrest records, incident reports
    - Note findings in Case File
  
  Step 2: Timeline Correlation
    - Extract all transactions for wallet
    - Plot on timeline (when active?)
    - Correlate with known incident dates
    - Check if timing matches ransomware campaign, theft date
  
  Step 3: Pattern Matching
    - Overlay wallet behavior against known actor playbooks
    - Score match against 7 key indicators:
      ✓ Mixing behavior
      ✓ Speed to cash-out
      ✓ Transaction amount signature
      ✓ Timing patterns
      ✓ Geographic clustering
      ✓ Script type consistency
      ✓ Initial fund source
  
  Step 4: Entity Clustering
    - Check Network Graph for connected wallets
    - Are they co-owned? (same funding source, same mixing pattern)
    - Expand investigation to clusters
  
  Step 5: Evidence Chain
    - Document findings:
      * Which pattern matched?
      * What OSINT evidence found?
      * Timeline correlation?
      * Risk score justification
    - Generate formatted report for law enforcement
```

---

#### Stage 4: Confidence Scoring
```
Investigator assigns confidence (0-100):
  0-20:   False positive (legitimate behavior)
  21-40:  Low confidence (one pattern matched)
  41-60:  Medium confidence (multiple indicators, inconclusive)
  61-80:  High confidence (strong pattern match, OSINT corroboration)
  81-100: Critical (multiple patterns + confirmed threat intel)

Alert ranked in dashboard by confidence score
Investigators prioritize high-confidence alerts
```

---

### 3.3 Pattern Library (Known Threat Signatures)

#### Pattern 1: Ransomware Payment Collection
**Indicators:**
- New wallet (< 1 day old)
- Receives $50k+ from single source
- Broadcasts from non-residential IP
- Within 2-6 hours: funds split to 5-20 addresses
- All split addresses participate in mixing immediately
- After 12-24h: addresses consolidate to exchange deposit addresses

**Risk Score:** 90-100  
**Confidence:** 95%

---

#### Pattern 2: CoinJoin/Tornado.cash Mixing
**Indicators:**
- Inputs: 10-50 addresses, unrelated history
- Outputs: Equal-value amounts (e.g., 1 BTC each)
- Transaction fee: Suspiciously high (indicates urgency)
- Timing: Multiple mixing cycles (tx → mixer → new wallet → mixer again)
- Output addresses: Used only once (privacy-seeking)

**Risk Score:** 60-75  
**Confidence:** 85%

---

#### Pattern 3: Exchange Consolidation (Legitimate)
**Indicators:**
- Inputs: 50-500 addresses, known as output recipients (hodlers)
- Outputs: 1-2 large addresses (exchange deposit wallets)
- Timing: Regular, predictable (weekly Monday, monthly 1st)
- Script type: Consistent P2PKH/P2WPKH
- No mixing participation
- No geographic anomalies

**Risk Score:** 5-15  
**Confidence:** 95%

---

#### Pattern 4: Darknet Marketplace Withdrawal
**Indicators:**
- Wallet receives from 100+ sources (marketplace escrow payouts)
- Outputs: Small, regular amounts (daily seller withdrawals)
- Timing: Regular 24h cycles (daily settlement)
- Script type: Multisig 2-of-3 (marketplace custody)
- No rapid consolidation (typical marketplace pattern)

**Risk Score:** 40-60 (depends on marketplace reputation)  
**Confidence:** 80%

---

#### Pattern 5: Theft Laundering (Exchange Hack)
**Indicators:**
- Receives large amount instantly (hack proceeds)
- Immediately consolidates (no waiting)
- Broadcasts from single datacenter IP for first 24h
- Then rapid geolocation changes (using VPNs)
- Mixes heavily within 12h
- Exchanges to altcoins then back to BTC (chain-hopping)

**Risk Score:** 85-95  
**Confidence:** 90%

---

### 3.4 Evidence Chain for Law Enforcement Handoff

**Document structure for each alert:**

```markdown
## Investigation Report: [Wallet Address]

### Summary
- Wallet: 1A1z7agoat...
- First Seen: 2024-01-15
- Total Volume: $250,000
- Threat Classification: RANSOMWARE
- Confidence: 85%

### Timeline
2024-01-15 14:32: Receives $250k from single source
2024-01-15 14:45: Splits to 15 addresses
2024-01-15 15:00: All recipients join CoinJoin pool
2024-01-15 22:00: Consolidated to exchange deposit
2024-01-16 08:00: Withdrew from exchange (2 BTC remaining)

### Pattern Matches
✓ New wallet (< 24h) receiving large amount
✓ Rapid subdivision within 2 hours
✓ Immediate mixing participation
✓ Speed to cash-out matches LockBit signature
✓ Transaction amount ($250k) matches LockBit ransom demand

### OSINT Findings
- Wallet address found in Chainalysis public ransomware tracker
- Linked to LockBit 2024 campaign (15 victims)
- IP broadcast from AS12345 (known bulletproof hoster in NL)
- Same IP range used in 3 other LockBit payment collections

### Network Intelligence
- Broadcast from 203.45.67.89 (geoloc: Rotterdam, NL)
- AS12345 (Bulletproof Hosting Ltd, WHOIS private)
- IP last seen broadcasting LockBit payments 2024-01-10

### Conclusion
High confidence this wallet is part of LockBit ransomware campaign.
Recommend coordination with law enforcement for exchange subpoena.
```

---

## Part 4: Technical Implementation

### 4.1 Data Ingestion Pipeline

```python
# pseudo-code flow
def ingest_blockchain_data(csv_file):
    for tx in parse_csv(csv_file):
        tx_obj = normalize_transaction(tx)
        store_in_postgres(tx_obj)
        update_graph_db(tx_obj)  # Add wallet nodes, tx edges
        trigger_correlation_engine(tx_obj)

def ingest_network_data(csv_file):
    for obs in parse_csv(csv_file):
        obs_obj = normalize_network_observation(obs)
        store_in_postgres(obs_obj)
        correlate_with_wallets(obs_obj)  # Link IPs to wallets
        update_geolocation_profile(obs_obj)

def ingest_threat_intel(feed_url):
    data = fetch_threat_feed(feed_url)
    for entity in data:
        store_in_postgres(entity)
        flag_existing_wallets(entity)  # Mark if in database
```

### 4.2 Correlation Engine

```python
def run_correlation_cycle():
    # Called every hour or on-demand
    
    # 1. Entity clustering (wallet ownership inference)
    clusters = cluster_wallets_by_behavior()
    
    # 2. Timeline analysis (sequence detection)
    patterns = detect_transaction_patterns()
    
    # 3. Pattern matching (against known signatures)
    matches = match_against_pattern_library()
    
    # 4. Geolocation anomaly detection
    geo_anomalies = detect_geo_anomalies()
    
    # 5. OSINT correlation
    intel_hits = correlate_with_threat_feeds()
    
    # 6. Score and alert
    for alert in generate_alerts():
        store_alert(alert)
        notify_investigators(alert)
```

### 4.3 Scoring Algorithm

```python
def calculate_risk_score(entity):
    score = 0
    
    # Pattern matching (0-40 points)
    pattern_match = match_patterns(entity)
    score += pattern_match.confidence * 40
    
    # OSINT evidence (0-30 points)
    osint_hits = query_threat_feeds(entity)
    score += min(osint_hits.count, 3) * 10
    
    # Behavioral anomalies (0-20 points)
    anomalies = detect_behavioral_anomalies(entity)
    score += anomalies.severity * 20
    
    # Temporal indicators (0-10 points)
    temporal_score = evaluate_temporal_indicators(entity)
    score += temporal_score
    
    return min(score, 100)
```

---

## Part 5: User Workflows

### 5.1 Investigator Dashboard

**View 1: Alert Ranking**
```
Rank | Entity      | Type    | Reason             | Risk | OSINT | Actions
-----|-------------|---------|--------------------|----|-------|----------
1    | 1A1z7a...  | Wallet  | Ransomware sig    | 92 | YES   | [Open] [Flag]
2    | AS12345    | ASN     | Bulletproof host  | 88 | YES   | [Open] [Flag]
3    | 1A1z7b...  | Wallet  | Mixing detected   | 75 | NO    | [Open] [Flag]
4    | 203.45...  | IP      | Geo anomaly       | 62 | NO    | [Open] [Flag]
```

**View 2: Case File**
```
Case: LockBit Campaign Jan 2024

Linked Entities:
  - Wallets: 15
  - IPs: 3
  - Incidents: 12 (12 ransomware victims)

Timeline:
  [Graph showing transaction flow over time]

Network Graph:
  [Visual showing wallet clusters and connections]

Evidence:
  - Pattern matches: 7/7 indicators
  - OSINT: 4 threat feeds
  - IP geolocation: All from NL datacenter
```

### 5.2 Entity Investigation Card

```
Wallet: 1A1z7agoat...

Profile:
  First Seen: 2024-01-15 14:32
  Last Seen: 2024-01-16 08:15
  Total Volume: $250,000
  Transaction Count: 8
  Mixing Participation: Yes (CoinJoin)

Linked Entities:
  - Funded by: Multiple addresses (likely exchange)
  - Funds sent to: 15 addresses (mixing pool)
  - IPs: 203.45.67.89 (AS12345, Rotterdam)

Risk Assessment:
  Pattern Scores:
    - Ransomware: 95%
    - Money Laundering: 60%
    - Legitimate: 5%
  
  OSINT:
    - Chainalysis ransomware tracker: YES
    - Linked incident: LockBit_2024_JAN
  
  Final Risk: 92/100 (CRITICAL)

Investigator Notes:
  [Text field for manual annotations]
```

---

## Part 6: Deployment & Operations

### 6.1 Infrastructure Requirements

```
CPU:      4+ cores
RAM:      16+ GB (32GB recommended for large datasets)
Storage:  500GB SSD minimum (1TB for production)
Database: PostgreSQL 12+, Neo4j 4.x
OS:       Ubuntu 20.04 LTS or later
```

### 6.2 Data Management

**Ingestion frequency:**
- Blockchain data: Daily (full export) or hourly (delta)
- Network data: Real-time (if available) or batch hourly
- Threat feeds: Daily

**Retention:**
- Transaction data: 12 months minimum (compliance)
- Correlation data: Unlimited (reference)
- Alerts: 24 months (investigation trail)

### 6.3 Audit & Compliance

**Log everything:**
- Data ingestion (source, timestamp, row count)
- Investigator actions (who opened case, when, what viewed)
- Scoring decisions (why flagged, confidence rationale)
- Manual overrides (investigator changed confidence, reason)

**Audit trail output:**
- Monthly: Cases investigated, entities flagged, false positives
- Quarterly: Pattern effectiveness, new threat detection, missed detections
- Annually: System accuracy, investigator feedback, model updates

---

## Part 7: Success Metrics

### 7.1 Investigation Effectiveness

- **Detection rate:** % of known threat actors detected within 24h of first transaction
- **False positive rate:** % of flagged entities that are legitimate
- **Time to alert:** Hours from transaction to investigator notification
- **Time to investigation:** Hours from alert to case opened

### 7.2 Operational Metrics

- **Throughput:** Transactions processed per hour
- **Database query latency:** Average time to return 1000 transaction query
- **Alert accuracy:** % of investigator-validated alerts that lead to actionable leads
- **Coverage:** % of Bitcoin transactions analyzed vs. total network volume

---

## Part 8: Future Enhancements

1. **Machine learning entity clustering** (graph neural networks for wallet ownership)
2. **Altcoin tracking** (cross-chain transaction tracing)
3. **Exchange API integration** (real-time deposit detection)
4. **Law enforcement collaboration API** (secure alert sharing)
5. **Sanctions list integration** (automatic OFAC flagging)
6. **Multilingual OSINT** (darknet forum monitoring in multiple languages)

---

## Appendix: Key Terminology

| Term | Definition |
|------|-----------|
| TXID | Transaction ID (hash) on blockchain |
| Wallet | Public address receiving/sending funds |
| Input | Funds being spent in a transaction |
| Output | Funds resulting from a transaction |
| UTXO | Unspent transaction output (spendable balance) |
| CoinJoin | Privacy protocol mixing multiple inputs/outputs |
| Mixing | Obscuring transaction history via multiple hops |
| Consolidation | Combining many inputs into fewer outputs |
| Subdivision | Splitting one input to many outputs |
| ASN | Autonomous System Number (IP network identifier) |
| OSINT | Open Source Intelligence (public data investigation) |
| SIGINT | Signal Intelligence (network behavior analysis) |

