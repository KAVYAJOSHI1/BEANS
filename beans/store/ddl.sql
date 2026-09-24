-- BEANS DuckDB schema. SHARED FILE: tell the team before changing it.
-- JSON-shaped columns are VARCHAR holding JSON text (keeps us independent of DuckDB extensions offline).
-- Owner of each block = the only person whose code WRITES those tables. Everyone may read everything.

-- ============================================================ DHARMIK: ingest / enrich / graph
CREATE TABLE IF NOT EXISTS ingest_log (
    file VARCHAR, fmt VARCHAR, sha256 VARCHAR, rows_ok BIGINT, rows_bad BIGINT,
    started_at TIMESTAMP, finished_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS quarantine (source_file VARCHAR, line_no BIGINT, reason VARCHAR, raw VARCHAR);

-- one row per network observation (a peer relaying a tx to our observer)
CREATE TABLE IF NOT EXISTS net_obs (
    obs_id BIGINT, ts TIMESTAMP, txid VARCHAR,
    src_ip VARCHAR, src_port INTEGER, dst_ip VARCHAR, dst_port INTEGER,
    src_country VARCHAR, src_asn INTEGER, src_asn_org VARCHAR, src_asn_type VARCHAR,
    dst_country VARCHAR, dst_asn INTEGER,
    source_file VARCHAR
);
-- unique per txid
CREATE TABLE IF NOT EXISTS tx (
    txid VARCHAR, ts_first_seen TIMESTAMP, fee DOUBLE, script_type VARCHAR,
    n_in INTEGER, n_out INTEGER, total_in DOUBLE, total_out DOUBLE, block_height BIGINT
);
CREATE TABLE IF NOT EXISTS tx_input  (txid VARCHAR, idx INTEGER, address VARCHAR, amount DOUBLE);
CREATE TABLE IF NOT EXISTS tx_output (txid VARCHAR, idx INTEGER, address VARCHAR, amount DOUBLE);
-- unique per address
CREATE TABLE IF NOT EXISTS wallet (
    address VARCHAR, addr_type VARCHAR, first_seen TIMESTAMP, last_seen TIMESTAMP,
    n_tx_in INTEGER, n_tx_out INTEGER, total_recv DOUBLE, total_sent DOUBLE
);
-- unique per ip
CREATE TABLE IF NOT EXISTS ip (
    ip VARCHAR, country VARCHAR, asn INTEGER, asn_org VARCHAR, asn_type VARCHAR, is_tor_exit BOOLEAN,
    n_obs BIGINT, n_tx_first_seen BIGINT, first_seen TIMESTAMP, last_seen TIMESTAMP
);
-- graph layer
CREATE TABLE IF NOT EXISTS tx_first_spy (txid VARCHAR, ip VARCHAR, ts TIMESTAMP, delta_to_second_s DOUBLE, n_relays INTEGER);
CREATE TABLE IF NOT EXISTS wallet_ip (address VARCHAR, ip VARCHAR, n_tx INTEGER, weight DOUBLE);
-- value-weighted wallet->wallet flow, proportional split of each tx's inputs over its outputs
CREATE TABLE IF NOT EXISTS flow_edge (src VARCHAR, dst VARCHAR, txid VARCHAR, ts TIMESTAMP, amount DOUBLE);
-- known-bad seed wallets (the only "intel" the models may use)
CREATE TABLE IF NOT EXISTS seeds (address VARCHAR, label VARCHAR, source VARCHAR);
-- GROUND TRUTH (synthetic only). Used ONLY for training targets and evaluation, NEVER as a feature.
CREATE TABLE IF NOT EXISTS labels_address (address VARCHAR, typology VARCHAR, entity_id VARCHAR, is_illicit BOOLEAN);
CREATE TABLE IF NOT EXISTS labels_tx (txid VARCHAR, tx_class VARCHAR, typology VARCHAR, is_illicit BOOLEAN);

-- ============================================================ DHAIRYA: features / engines / fusion
CREATE TABLE IF NOT EXISTS cluster (address VARCHAR, cluster_id VARCHAR, method VARCHAR);  -- method: CIOH | CIOH+CHANGE
CREATE TABLE IF NOT EXISTS cluster_suggest (cluster_a VARCHAR, cluster_b VARCHAR, similarity DOUBLE);  -- E1 embeddings
CREATE TABLE IF NOT EXISTS tx_scores (
    txid VARCHAR, anomaly DOUBLE, tx_class_pred VARCHAR,
    p_normal DOUBLE, p_peel DOUBLE, p_coinjoin DOUBLE, p_fan_out DOUBLE, p_fan_in DOUBLE, p_round_trip DOUBLE,
    peel_chain_id VARCHAR, peel_chain_pos INTEGER
);
CREATE TABLE IF NOT EXISTS wallet_scores (
    address VARCHAR, cluster_id VARCHAR,
    anomaly DOUBLE, ppr DOUBLE, ppr_reverse DOUBLE, taint DOUBLE, hops_to_seed INTEGER, gnn DOUBLE,
    fused_prob DOUBLE, risk DOUBLE, confidence DOUBLE, severity VARCHAR
);
CREATE TABLE IF NOT EXISTS alert (
    alert_id VARCHAR, rank INTEGER, entity_type VARCHAR, entity_id VARCHAR, alert_type VARCHAR, title VARCHAR,
    risk DOUBLE, confidence DOUBLE, severity VARCHAR,
    reasons VARCHAR, shap_top VARCHAR, engine_scores VARCHAR, evidence VARCHAR,  -- JSON text, see beans/schema.py Alert
    member_count INTEGER, created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS model_card (key VARCHAR, value VARCHAR);  -- value = JSON text

-- ============================================================ KAVYA: investigator state (survives re-scoring)
CREATE TABLE IF NOT EXISTS alert_status (
    alert_id VARCHAR, status VARCHAR, assignee VARCHAR, notes VARCHAR, feedback_label VARCHAR, updated_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS case_file (case_id VARCHAR, name VARCHAR, status VARCHAR, notes VARCHAR, created_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS case_alert (case_id VARCHAR, alert_id VARCHAR);
CREATE TABLE IF NOT EXISTS audit_log (ts TIMESTAMP, actor VARCHAR, action VARCHAR, target VARCHAR, details VARCHAR);
