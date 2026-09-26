# BEANS: Interface Contracts (read this before writing code)

Three people and their AI agents build in parallel. They connect only through the items below.
**If you need to change a contract, tell the other two first, then change it on `penultimate`.**

| Contract | Where | Producer → Consumer |
|---|---|---|
| Input record format (CSV/JSON/XML) | §1, `data/samples/sample.*`, `beans/schema.py::RawRecord` | Dharmik's synth → Dharmik's ingest (and NTRO's data) |
| DuckDB tables | `beans/store/ddl.sql` | Dharmik writes data/graph tables → Dhairya writes score tables → Kavya reads all, writes investigator tables |
| Python entry points | §3 | Kavya's `pipeline` / API call Dharmik's and Dhairya's functions |
| Alert JSON | `beans/schema.py::Alert`, `data/samples/mock_alerts.json` | Dhairya → Kavya |
| Subgraph JSON | §4, `data/samples/mock_subgraph.json` | Dharmik (`beans.graph.subgraph`) → Kavya |
| REST API | §5 | Kavya → UI |

`tests/test_contracts.py` must pass on every branch at all times.

---

## 1. Input format (one row = one network observation of one transaction)

The same `txid` may appear in several rows (relayed by several peers). The earliest `src_ip` per txid is the **first-spy** origin candidate.

| field | type | notes |
|---|---|---|
| timestamp | ISO-8601 UTC | `2026-03-01T10:00:00Z` |
| src_ip, dst_ip | str | IPv4/IPv6 |
| src_port, dst_port | int | 8333 = BTC P2P |
| txid | 64 lowercase hex | |
| input_addresses, output_addresses | list[str] | CSV: `;`-joined in one cell (a JSON-array string is also accepted) |
| input_amounts, output_amounts | list[float BTC] | same length as the address lists |
| fee | float BTC | optional; if missing, it's computed as sum(in) - sum(out) |
| script_type | P2PKH/P2SH/P2WPKH/P2WSH/P2TR | |
| geo_country, asn | optional | we fill them from GeoIP when missing |

JSON = an array of objects **or** NDJSON. XML layout: see `data/samples/sample.xml`.
Unknown column names must be mappable via `--mapping mapping.yaml` (`{their_name: our_name}`).

Synthetic dataset folder layout (`beans synth` output, and what `beans ingest` looks for next to the input):
```
data/synth/<preset>/transactions.csv | .json | .xml
                    labels_address.csv   address,typology,entity_id,is_illicit
                    labels_tx.csv        txid,tx_class,typology,is_illicit
                    seeds.csv            address,label,source      (~20% of illicit addresses)
                    manifest.json        seed, params, counts, sha256 of each file
```

## 2. Table ownership (`beans/store/ddl.sql`)

- **Dharmik writes:** ingest_log, quarantine, net_obs, tx, tx_input, tx_output, wallet, ip, tx_first_spy, wallet_ip, flow_edge, seeds, labels_address, labels_tx
- **Dhairya writes:** cluster, cluster_suggest, tx_scores, wallet_scores, alert, model_card
- **Kavya writes:** alert_status, case_file, case_alert, audit_log

Rules:
- `labels_*` are ground truth. **Never use them as model features.** Use them only as training targets and for evaluation. Anything else is leakage, and judges will catch it.
- `beans score` fully replaces Dhairya's tables. Investigator state lives in `alert_status`, keyed by the **deterministic** `alert_id_for(entity_type, entity_id)`, so it survives re-scoring.
- JSON columns (`alert.reasons`, `shap_top`, `engine_scores`, `evidence`, `model_card.value`) are VARCHAR JSON text.
- DuckDB allows a single writer process. Stop `beans serve` before running the CLI pipeline, or trigger it via `POST /api/pipeline/run`.

## 3. Python entry points (signatures are fixed; the bodies are yours)

```python
beans.synth.generate(preset, out_dir, seed=42, formats=("csv","json","xml")) -> Path   # Dharmik
beans.ingest.ingest_files(con, paths, mapping=None, reset=False) -> dict               # Dharmik
beans.graph.build(con) -> dict                                                          # Dharmik
beans.graph.subgraph(con, center, hops=2, min_risk=0.0, limit=300) -> dict              # Dharmik
beans.score.run_all(con, train=True) -> dict                                            # Dhairya
beans.score.evaluate(con) -> dict                                                       # Dhairya
beans.report.case_pdf(con, case_id | alert_id, out_path) -> Path                        # Kavya
```
`con` is a `duckdb.DuckDBPyConnection` from `beans.store.db.connect()`.

## 4. Subgraph JSON (`beans.graph.subgraph`, example: `data/samples/mock_subgraph.json`)

```json
{ "center": "wallet:<addr>",
  "nodes": [ {"id":"wallet:<addr>","type":"wallet","label":"bc1q…","risk":93,"is_seed":false,"cluster_id":"C-1"},
             {"id":"tx:<txid>","type":"tx","label":"9f2c…","risk":80,"tx_class":"peel"},
             {"id":"ip:<ip>","type":"ip","label":"185.220.101.4","risk":68,"country":"DE","asn_type":"TOR"},
             {"id":"asn:<n>","type":"asn","label":"AS60729","risk":50} ],
  "edges": [ {"source":"wallet:…","target":"tx:…","type":"IN","amount":1.2,"ts":"…"},
             {"source":"tx:…","target":"wallet:…","type":"OUT","amount":1.1,"ts":"…"},
             {"source":"ip:…","target":"tx:…","type":"FIRST_SEEN|RELAYED","ts":"…","delta_s":1.8},
             {"source":"ip:…","target":"asn:…","type":"IN_ASN"} ] }
```
`risk` is taken from `wallet_scores` / `tx_scores` when present (LEFT JOIN), otherwise 0.

## 5. REST API (Kavya; FastAPI on 127.0.0.1:8000, all under `/api`)

| Method | Path | Returns |
|---|---|---|
| GET | /health | `{status, db, mock}` |
| GET | /stats/overview | counts (tx, wallets, ips, clusters, alerts by severity/type), alerts over time, top countries/ASNs |
| GET | /alerts?severity=&type=&status=&q=&limit=&offset= | `{total, items:[Alert + status]}` |
| GET | /alerts/{id} | Alert + status + notes |
| PATCH | /alerts/{id} | body `{status?, notes?, feedback_label?, assignee?}` → audit_log |
| GET | /entity/wallet/{addr} · /entity/ip/{ip} · /entity/cluster/{id} · /entity/tx/{txid} | profile + scores + linked entities + tx list |
| GET | /graph/subgraph?center=&hops=&min_risk=&limit= | §4 |
| GET | /timeline?center=&hops= | ordered flow events for the timeline view |
| GET | /geo?min_risk= | per-IP points (country centroid, risk) + impossible-travel arcs |
| POST | /seeds (csv upload) | re-runs E4 + fusion |
| POST | /ingest (file upload) | job id; runs ingest → graph → score in-process |
| GET | /jobs/{id} | progress |
| GET | /model/card | model_card as JSON |
| POST/GET | /cases, /cases/{id}, /cases/{id}/export?fmt=pdf\|json | case management + evidence pack |
| GET | /audit | audit log |
| GET | /alerts?action= | filter by recommended action; every alert carries `recommended_action {action, title, rule, legal_basis, facts, shap_support, vasp_exposure, also_matched}` (`beans/decision/actions.py`) |
| GET | /actions/summary | the directive rulebook + counts |
| POST | /alerts/{id}/legal/{section94\|freeze}?fmt=json\|html\|pdf | legal request draft for the IO, sealed (SHA-256 + RFC 3161) |
| GET | /alerts/{id}/referral?fmt=json\|html\|pdf | FIU-IND intelligence referral pack, sealed |
| GET/POST | /known-entities, /known-entities/upload | attribution list (exchanges / mining pools) |
| GET/POST/PATCH/DELETE | /webhooks, /webhooks/{id}, /webhooks/{id}/test, /webhooks/dispatch, /webhooks/log | SIEM delivery |
| GET/POST | /tsa, /tsa/{tsa_ca.pem\|tsa.pem}, /tsa/verify | local RFC 3161 TSA |
| GET/POST/DELETE | /watchlist, /watchlist/{address}, /cases/{id}/watch | wallets whose next spend raises a movement event |
| GET/PATCH | /watch-events?status=, /watch-events/{id} | movement events (OPEN / ACKNOWLEDGED) |
| GET | /config | thresholds from `beans/config.py` + whether the loaded data is synthetic |
| POST/GET | /auth/login, /auth/logout, /auth/me, /auth/password | session cookie; login required once a user exists |
| GET/POST/PATCH | /users, /users/{name} | user management (ADMIN) |
| GET | /legal-requests?status=, /legal-requests/{id}?fmt=json\|html\|pdf | filed legal drafts with approval state |
| POST | /legal-requests/{id}/decision | APPROVE / REJECT (SUPERVISOR, not the drafter) |

`BEANS_MOCK=1` makes the API serve `data/samples/mock_*.json`, so the UI can be built before real data exists.
