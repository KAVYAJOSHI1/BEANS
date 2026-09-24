# BEANS data formats

## 1. Input record

One row = one **network observation**: a peer relayed a transaction to one of our observer nodes. The same `txid` normally appears several times, once per relaying peer. BEANS treats the earliest row as the *first-spy* (likely originator) observation.

| Field | Required | Accepted values |
|---|---|---|
| `timestamp` | yes | ISO-8601 (`2026-09-01T10:02:11Z`, offsets allowed) or Unix epoch seconds / milliseconds |
| `txid` | yes | 64 hex characters (case-insensitive) |
| `src_ip` | yes | IPv4 / IPv6 of the relaying peer |
| `output_addresses` | yes | see *arrays* below |
| `output_amounts` | with addresses | BTC (or satoshis with `amount_unit: sat`) |
| `input_addresses`, `input_amounts` | no (empty = coinbase) | see *arrays* |
| `src_port`, `dst_ip`, `dst_port` | no | default port 8333 |
| `fee` | no | if missing: `sum(inputs) − sum(outputs)` |
| `script_type` | no | P2PKH, P2SH, P2WPKH, P2WSH, P2TR; anything else becomes `UNKNOWN` |
| `geo_country`, `asn` | no | always (re)computed offline from the bundled DB-IP databases |

**Arrays** may be given as `a;b;c`, `a,b,c`, a JSON list, or, for inputs/outputs, a list of objects:
`[{"address": "bc1q…", "value": 150000000}, …]` (`value`, `amount` or `btc`). Amounts then come from the objects.

Rows that fail validation go to `data/quarantine.csv` with the reason. BEANS never fills a missing required field with a placeholder. The ingest result reports `rows_read` and `rows_quarantined`.

## 2. File formats

**CSV** (header row, UTF-8, BOM tolerated)
```csv
timestamp,src_ip,src_port,dst_ip,dst_port,txid,input_addresses,input_amounts,output_addresses,output_amounts,fee,script_type
2026-09-01T10:00:00.198Z,129.212.204.114,8333,47.90.179.236,8333,85ab…a5,bc1qa…;bc1qb…,0.5;0.7,bc1qx…;bc1qy…,1.19;0.0095,0.0005,P2WPKH
```

**JSON**: an array of objects, or NDJSON (one object per line), with the same field names and real arrays.

**XML**
```xml
<transactions>
  <tx txid="85ab…a5" timestamp="2026-09-01T10:00:00.198Z" fee="0.0005" script_type="P2WPKH">
    <net src_ip="129.212.204.114" src_port="8333" dst_ip="47.90.179.236" dst_port="8333"/>
    <inputs><in address="bc1qa…" amount="0.5"/></inputs>
    <outputs><out address="bc1qx…" amount="1.19"/><out address="bc1qy…" amount="0.0095"/></outputs>
  </tx>
</transactions>
```
`<transaction>` / `<record>` elements and child-element variants (`<input><address>…`) are accepted too.

## 3. Unfamiliar files: column mapping

Common aliases are recognised automatically (`tx_hash`, `source_ip`, `vin`, `vout`, `inputs`, `outputs`, `fees`, …). For anything else, pass a YAML mapping:

```yaml
# their column: our field
seen_at_ms: timestamp
tx_hash: txid
peer_address: src_ip
peer_port: src_port
sensor: dst_ip
vin: input_addresses
vout: output_addresses
fee_sats: fee
amount_unit: sat          # amounts are satoshis
```
```bash
.venv/bin/python -m beans.cli ingest their_export.csv --mapping their_mapping.yaml
```
In the dashboard, the Ingest page upload accepts the same YAML (`POST /api/ingest/upload` with `file` + `mapping`).
Verified on a renamed-column export with epoch-millisecond times, satoshi amounts and nested input/output objects (`tests/test_all.py::test_unfamiliar_export_with_mapping`).

## 4. Sidecar files (optional, next to the input file)

| File | Columns | Used for |
|---|---|---|
| `seeds.csv` | `address` (+ `threat_type`/`label`, `incident_name`, `confidence`, `source`) | known illicit wallets → E4 risk propagation |
| `labels_address.csv` | `address, typology, entity_id, is_illicit` | **training targets and evaluation only** |
| `labels_tx.csv` | `txid, tx_class, typology, is_illicit, entity_id` | E3 training targets and evaluation only |

Without label files (operational data), the models saved by the last training run score the data. Analyst verdicts (Confirm / False positive) are added to the next training run.

## 5. Synthetic generator (`beans synth`)

`beans/synth/sim.py` is an event-driven simulation over 7 days with a real UTXO ledger, so every input spends an earlier output.

| Actor | Behaviour on-chain | Network behaviour |
|---|---|---|
| Retail users (NORMAL) | payments with change, exchange deposits; 12% also CoinJoin, 8% buy on a darknet market | residential ISP, stable IP (some behind shared NAT), diurnal |
| Exchanges | withdrawal batches (fan-out), deposit sweeps (fan-in), cold→hot refills | datacenter |
| Merchants, miners | daily sweeps; coinbase + pool payouts (fan-out) | datacenter |
| **RANSOMWARE** | victims pay fresh addresses → consolidation → split 5–12 → CoinJoin or short peel chains → exchanges | VPN/Tor/bulletproof, different IP per broadcast (impossible travel) |
| **PEEL_CHAIN** | 5–35 hops shaving 1–6% to exchanges/merchants, 3–35 min apart | VPN/Tor/bulletproof |
| **HACK_LAUNDERING** | steals from the richest exchange hot wallet → split 8–15 → peel hops → exchanges | one datacenter IP for 24 h, then VPN/Tor hopping |
| **DARKNET_MARKET** | buyer payments to P2WSH escrow → daily consolidation → vendor payouts → vendors cash out | Tor |
| **FAN_OUT_SMURF** | one amount split into 0.090–0.0999 BTC pieces, each deposited separately | several datacenter IPs |
| **ROUND_TRIP** | A→B→C→A cycles, 6–15 hops | VPN/Tor |
| **DUSTING** | 546-sat outputs to 80 existing retail addresses | bulletproof hosting |

Hardness: exchange payouts look like smurfing fan-outs, legitimate users also CoinJoin, the origin IP is missed for 15% of illicit transactions (5% legitimate), and 1–3 relay peers add noise to every transaction.
IPs come from real prefixes of the bundled DB-IP databases (`data/intel/ip_pools.json`), and Tor IPs from the dated exit-list snapshot, so enrichment behaves as it would on real traffic. Output is deterministic for a given `--seed`.

## 6. Exports

```bash
.venv/bin/python -m beans.cli export --neo4j out/neo4j      # CSVs for neo4j-admin import (see out/neo4j/IMPORT.md)
.venv/bin/python -m beans.cli export --stix alerts.json     # STIX 2.1 bundle: wallet + first-relay IP indicators
.venv/bin/python -m beans.cli watch data/inbox              # monitoring mode: ingest every new file dropped in
```
