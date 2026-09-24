# TASKS: Dharmik · Data, Synthetic Generator, Ingestion, Enrichment, Graph

**Branch:** `dharmik` · **Merge target:** `penultimate` · **Deadline:** CP3 at 20:30
**You own:** `beans/synth/` `beans/ingest/` `beans/enrich/` `beans/graph/` `beans/cli_data.py` `data/intel/` `data/geoip/` `scripts/fetch_geoip.sh` `docs/DATA_FORMATS.md` `tests/test_data_*.py`
**You write these tables:** ingest_log, quarantine, net_obs, tx, tx_input, tx_output, wallet, ip, tx_first_spy, wallet_ip, flow_edge, seeds, labels_address, labels_tx
**Read first:** `docs/CONTRACTS.md`, `beans/schema.py`, `beans/store/ddl.sql`, `MASTER_ROADMAP.md` §5 and §1.2

Why your part matters: the PS says **"Dataset Link: Nil"**, so the synthetic generator *is* the dataset. Every ML metric and every demo screen depends on your data being realistic, labelled and hard enough. Your other job is the network ↔ blockchain correlation (first-spy), which is the NTRO-specific differentiator.

---

## CP1 (by 14:30): data flows end to end
- [ ] **D1 `beans.synth.generate()` v1** (`beans/synth/`: `ledger.py`, `actors.py`, `typologies.py`, `ipgen.py`, `writer.py`)
  - Real **UTXO ledger**: every input spends an earlier output, so the graph is connected and realistic. A funding "genesis/miner" actor bootstraps coins.
  - Address formats by script type: P2PKH `1…`, P2SH `3…`, P2WPKH `bc1q…`(42 chars), P2WSH `bc1q…`(62), P2TR `bc1p…`. Random but valid-looking base58/bech32 charset is enough.
  - Legit actors: retail (1–3 in, payment + change), exchange (deposit addresses → weekly consolidation; hot-wallet batch payouts 1→50–200).
  - Illicit v1: **PEEL_CHAIN**, **COINJOIN** (equal denominations 0.01/0.05/0.1 + change), **RANSOMWARE** (fresh wallet → large inflow → hold 24–48 h → split 5–20 → coinjoin → exchange deposit).
  - Network rows: each tx gets 1–4 observation rows. The first comes from the actor's origin IP; the others come from relay peers 0.5–6 s later. `dst_port` is mostly 8333.
  - IPs: each entity gets an IP pool from an **ASN type that fits** (retail → residential; ransomware → Tor/VPN/hosting; exchange → hosting). Sample real IPs so GeoIP resolves: keep a list of ~40 CIDR prefixes per ASN type in `data/intel/ip_pools.csv` and verify each with the mmdb.
  - Writes `transactions.csv/.json/.xml` (exact format of `data/samples/sample.*`), `labels_address.csv`, `labels_tx.csv`, `seeds.csv` (**20%** of illicit addresses, random), `manifest.json` (seed, params, counts, sha256).
  - `tiny` preset in < 5 s, deterministic for a given `--seed`.
- [ ] **D2 `beans.ingest.ingest_files()`**: `csv_reader.py` (pyarrow/pandas chunks), `json_reader.py` (auto-detect array vs NDJSON; `ijson` streaming for arrays), `xml_reader.py` (`lxml.etree.iterparse`, clear elements as you go).
  - Normalise everything into `RawRecord`-shaped dicts. Validate (use `RawRecord` or a faster vectorised equivalent, but apply the same rules). Invalid rows go to `quarantine` with a reason; never crash on a bad row.
  - Load into `net_obs`; derive `tx` (dedupe per txid; `ts_first_seen` = min ts; fee = given or sum(in)-sum(out)), `tx_input`, `tx_output`, `wallet` (aggregates), `ip` (aggregates).
  - Batch inserts: build pandas/arrow frames and use `con.register` + `INSERT … SELECT`. No row-by-row inserts.
  - If `labels_address.csv`, `labels_tx.csv`, `seeds.csv` sit next to the input file, load them.
  - `ingest_log` row per file with sha256.
- [ ] **D3 GeoIP enrichment** (`beans/enrich/geoip.py`): `maxminddb` readers for `data/geoip/dbip-*-lite.mmdb` (already in the repo), with an LRU cache per IP. Fill `src_country, src_asn, src_asn_org` and `ip.country/asn/asn_org`.
  - `asn_type` via `data/intel/asn_types.csv` (asn,type,note). Build it by hand now: ~30 hosting ASNs (AWS 16509/14618, GCP 396982/15169, Azure 8075, DigitalOcean 14061, OVH 16276, Hetzner 24940, Linode 63949, Vultr 20473, Contabo 51167, Scaleway 12876…), VPN-heavy ASNs (M247 9009, Datacamp 60068, …), residential/mobile (Jio 55836, Airtel 24560/45609, BSNL 9829, Comcast 7922, DTAG 3320, China Telecom 4134, Verizon 701, BT 2856…). Anything else is `UNKNOWN`.
  - `data/intel/tor_exits.csv`: an offline snapshot (download once from `https://check.torproject.org/torbulkexitlist`, note the date in the header). `is_tor_exit` → asn_type `TOR`.
- [ ] Unit tests `tests/test_data_ingest.py`: the 3 sample files → identical `tx` table; a bad row is quarantined, not a crash.
- [ ] **Merge to penultimate** and tell Dhairya the tiny DB is ready (`make pipeline-tiny` gets as far as ingest).

## CP2 (by 17:30): full typologies + graph
- [ ] **D4 synth v2**: add DARKNET_MARKET (fan-in 100+ buyers, daily seller withdrawals, 2-of-3 P2WSH), HACK_LAUNDERING (large inflow → consolidate → multi-hop dispersal; 1 datacenter IP for 24 h then geo-hopping), FAN_OUT_SMURF (structuring below a threshold), ROUND_TRIP (A→B→C→A), DUSTING; plus MERCHANT, MINER legit actors.
  - **Hardness knobs** (so ML isn't trivially 100%): legit CoinJoin users (privacy, not crime), exchange batch payouts that look like fan-out, 1–2% label noise, ~15% of illicit txs with the origin IP missed (first relay is a random peer), clock jitter ±2 s, shared NAT IPs across retail users.
  - Actor time zones → diurnal broadcast patterns. Ransomware operators are active off-hours relative to their victims.
  - `demo` preset ≈ 200k observation rows, ~3–5% illicit wallets. Generation < 2 min.
- [ ] **D5 `beans.graph.build()`**
  - `tx_first_spy`: per txid, the earliest-seen `src_ip`, `delta_to_second_s` (confidence: large gap = strong), `n_relays`.
  - `wallet_ip`: link each *input* address of a tx to its first-spy IP; `n_tx`, `weight = Σ confidence`.
  - `flow_edge`: for each tx, input address → output address with amount = in_amt × out_amt / total_out. Skip self-edges (change back to the same address). For huge txs (n_in × n_out > 2500), aggregate through a virtual node or keep only the top edges by value.
- [ ] **D6 `beans.graph.subgraph()`** + `beans/graph/load.py`
  - `load_flow_graph(con) -> networkx.DiGraph` (weight = amount) for Dhairya's E4. Also add an igraph variant if networkx is too slow on `demo`.
  - `subgraph(con, center, hops, min_risk, limit)` returns exactly the JSON in CONTRACTS §4. It covers wallet ↔ tx ↔ wallet hops, IP nodes via `tx_first_spy`/net_obs, and ASN nodes. LEFT JOIN `wallet_scores`/`tx_scores` for `risk` if the tables have rows. Always cap at `limit` nodes (keep the highest risk/value).
  - `path(con, src_addr, dst_addr, max_hops=6)` → ordered addresses (used for "path to seed").
- [ ] **D7 `--mapping mapping.yaml`**: rename arbitrary incoming columns/XML attributes to ours. Test it with a CSV whose headers are renamed (e.g. `time, source_ip, tx_hash, inputs, …`). NTRO may bring their own file at the finale.

## CP3 (by 20:30): robustness, performance, docs
- [ ] `bench` preset (1M rows): ingest + graph.build time measured and printed. Target: 200k rows < 60 s, 1M < 5 min on the 8-core laptop.
- [ ] Edge cases: IPv6, empty input list (coinbase), duplicate rows, amounts as strings, `Z` vs `+05:30` timestamps, BOM in CSV, gzip input (`.csv.gz`).
- [ ] `docs/DATA_FORMATS.md`: formats, mapping file, generator typologies table (what each looks like on-chain and on the network), and the knobs.
- [ ] Tests: `tests/test_data_synth.py` (determinism, label counts, UTXO consistency: no output spent twice), `tests/test_data_graph.py`.

## After CP3: support integration
Fix data bugs that Dhairya or Kavya report. Generate a second demo dataset with a different `--seed` for the "generalises to unseen data" test.

---

## Definition of done
```bash
make install && make test
.venv/bin/python -m beans.cli synth --preset demo
.venv/bin/python -m beans.cli ingest data/synth/demo/transactions.xml --reset
.venv/bin/python -m beans.cli graph
# counts in tx, wallet, ip, flow_edge, tx_first_spy are all > 0; quarantine small; GeoIP coverage > 95%
```

## Prompt to paste into your AI agent
> You are working in the BEANS repo on branch `dharmik`. Read `TASKS_DHARMIK.md`, `docs/CONTRACTS.md`, `beans/schema.py`, `beans/store/ddl.sql` and `MASTER_ROADMAP.md` sections 1.2 and 5. Implement the tasks in `TASKS_DHARMIK.md` in checkpoint order (CP1 first). Only create or modify files under the paths listed as "You own". Never change shared files (`beans/schema.py`, `beans/store/*`, `beans/cli.py`, `beans/config.py`, `docs/CONTRACTS.md`) without asking me. Keep the function signatures in `docs/CONTRACTS.md` §3 exactly. Everything must run fully offline on Linux with Python 3.12. Use vectorised pandas/DuckDB, not row loops, for anything that touches all rows. After each task, run `make test`, commit with a clear message, and tick the checkbox in `TASKS_DHARMIK.md`.
