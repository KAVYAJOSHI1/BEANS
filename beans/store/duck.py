import duckdb
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from beans.config import settings
from beans.schema import CanonicalRecord, AlertRecord

class DuckStore:
    """
    Embedded DuckDB storage layer for fast columnar analytics, wallet profile indexing, and alert storage.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or settings.DB_PATH)
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def get_connection(self):
        return duckdb.connect(self.db_path)

    def init_schema(self):
        conn = self.get_connection()
        conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            txid VARCHAR PRIMARY KEY,
            timestamp TIMESTAMP,
            input_addresses VARCHAR[],
            input_amounts DOUBLE[],
            output_addresses VARCHAR[],
            output_amounts DOUBLE[],
            total_input DOUBLE,
            total_output DOUBLE,
            fee DOUBLE,
            script_type VARCHAR,
            block_height BIGINT,
            src_ip VARCHAR,
            src_port INTEGER,
            dst_ip VARCHAR,
            dst_port INTEGER,
            geo_country VARCHAR,
            geo_city VARCHAR,
            geo_lat DOUBLE,
            geo_lon DOUBLE,
            asn VARCHAR,
            asn_name VARCHAR,
            asn_type VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS net_observations (
            id VARCHAR PRIMARY KEY,
            timestamp TIMESTAMP,
            txid VARCHAR,
            src_ip VARCHAR,
            src_port INTEGER,
            dst_ip VARCHAR,
            dst_port INTEGER,
            geo_country VARCHAR,
            geo_city VARCHAR,
            geo_lat DOUBLE,
            geo_lon DOUBLE,
            asn VARCHAR,
            asn_name VARCHAR,
            asn_type VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS wallet_profiles (
            address VARCHAR PRIMARY KEY,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            transaction_count INTEGER,
            total_received DOUBLE,
            total_sent DOUBLE,
            balance DOUBLE,
            risk_score DOUBLE,
            threat_classification VARCHAR,
            cluster_id VARCHAR,
            associated_ips VARCHAR[],
            tags VARCHAR[],
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS alerts (
            alert_id VARCHAR PRIMARY KEY,
            entity_id VARCHAR,
            entity_type VARCHAR,
            alert_type VARCHAR,
            risk_score DOUBLE,
            calibrated_confidence DOUBLE,
            severity VARCHAR,
            reasons VARCHAR[],
            shap_top_features JSON,
            engine_scores JSON,
            evidence JSON,
            status VARCHAR DEFAULT 'OPEN',
            assigned_to VARCHAR DEFAULT 'Unassigned',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS case_files (
            id INTEGER PRIMARY KEY,
            case_name VARCHAR,
            incident_type VARCHAR,
            suspect_entities VARCHAR[],
            linked_txids VARCHAR[],
            notes VARCHAR,
            investigator VARCHAR,
            status VARCHAR DEFAULT 'OPEN',
            priority VARCHAR DEFAULT 'HIGH',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY,
            action VARCHAR,
            investigator VARCHAR,
            entity_type VARCHAR,
            entity_id VARCHAR,
            details JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS seeds (
            address VARCHAR PRIMARY KEY,
            threat_type VARCHAR,
            incident_name VARCHAR,
            confidence DOUBLE,
            source VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY,
            alert_id VARCHAR,
            entity_id VARCHAR,
            user_label VARCHAR, -- TRUE_POSITIVE, FALSE_POSITIVE
            notes VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- attribution intel: addresses known to belong to exchanges (VASPs) / mining pools. Used by the action
        -- rules (beans/decision), never as a model feature.
        CREATE TABLE IF NOT EXISTS known_entities (
            address VARCHAR PRIMARY KEY,
            entity_name VARCHAR,
            entity_type VARCHAR,         -- VASP | MINING_POOL | MERCHANT | OTHER
            country VARCHAR,
            in_jurisdiction BOOLEAN,     -- operates in India / registered with FIU-IND → Section 94 BNSS applies
            source VARCHAR
        );

        CREATE TABLE IF NOT EXISTS webhooks (
            id INTEGER PRIMARY KEY,
            name VARCHAR,
            url VARCHAR,
            fmt VARCHAR,                 -- json | splunk_hec | elastic | stix
            min_severity VARCHAR DEFAULT 'CRITICAL',
            token VARCHAR,
            enabled BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS webhook_log (
            webhook_id INTEGER,
            alert_id VARCHAR,
            status VARCHAR,              -- SENT | FAILED | TEST
            http_status INTEGER,
            attempts INTEGER,
            error VARCHAR,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- watchlist: re-alert when these wallets spend (beans/alerting/watch.py)
        CREATE TABLE IF NOT EXISTS watchlist (
            address VARCHAR PRIMARY KEY,
            reason VARCHAR,              -- AUTO_TAINT_WATCH | ANALYST | CASE
            alert_id VARCHAR,
            case_id INTEGER,
            note VARCHAR,
            watched_from TIMESTAMP,      -- data time: spends after this raise an event
            balance_at_watch DOUBLE,
            active BOOLEAN DEFAULT TRUE,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS watch_events (
            event_id VARCHAR PRIMARY KEY,
            address VARCHAR, txid VARCHAR, ts TIMESTAMP, amount_btc DOUBLE, destinations JSON,
            first_spy_ip VARCHAR, first_spy_asn_type VARCHAR, first_spy_country VARCHAR,
            vasp VARCHAR, vasp_in_jurisdiction BOOLEAN, vasp_deposit_address VARCHAR, vasp_deposit_ts VARCHAR,
            minutes_since_move DOUBLE, watch_reason VARCHAR, alert_id VARCHAR, case_id INTEGER, recommended VARCHAR,
            status VARCHAR DEFAULT 'OPEN',   -- OPEN | ACKNOWLEDGED
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- users, sessions and legal-draft approvals (beans/api/auth.py)
        CREATE TABLE IF NOT EXISTS users (
            username VARCHAR PRIMARY KEY,
            display_name VARCHAR,
            role VARCHAR,                -- VIEWER | ANALYST | SUPERVISOR | ADMIN
            password_hash VARCHAR,
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash VARCHAR PRIMARY KEY, username VARCHAR, expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS legal_requests (
            id INTEGER PRIMARY KEY,
            alert_id VARCHAR, entity_id VARCHAR, kind VARCHAR, vasp VARCHAR,
            io JSON, annex JSON, evidence_sha256 VARCHAR, timestamp_token JSON, html VARCHAR,
            status VARCHAR DEFAULT 'PENDING_APPROVAL',   -- PENDING_APPROVAL | APPROVED | REJECTED
            created_by VARCHAR, decided_by VARCHAR, decision_comment VARCHAR, decided_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # migrations for databases created by earlier versions
        conn.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS recommended_action JSON")
        for col, typ in (("tx_version", "INTEGER"), ("locktime", "BIGINT"), ("rbf", "BOOLEAN")):
            conn.execute(f"ALTER TABLE transactions ADD COLUMN IF NOT EXISTS {col} {typ}")
        conn.close()

    def insert_records(self, records: List[CanonicalRecord]):
        """Bulk insert (Arrow). The first observation of a txid wins, so `transactions.src_ip` is the first-spy IP."""
        if not records:
            return
        import pyarrow as pa
        from datetime import timezone

        tx_rows, obs_rows = {}, []
        for r in records:
            ts = r.timestamp.astimezone(timezone.utc).replace(tzinfo=None) if r.timestamp.tzinfo else r.timestamp
            if r.txid not in tx_rows or ts < tx_rows[r.txid]["timestamp"]:
                tx_rows[r.txid] = {
                    "txid": r.txid, "timestamp": ts, "input_addresses": r.input_addresses,
                    "input_amounts": r.input_amounts, "output_addresses": r.output_addresses,
                    "output_amounts": r.output_amounts, "total_input": r.total_input, "total_output": r.total_output,
                    "fee": r.fee, "script_type": r.script_type, "block_height": r.block_height, "src_ip": r.src_ip,
                    "src_port": r.src_port, "dst_ip": r.dst_ip, "dst_port": r.dst_port, "geo_country": r.geo_country,
                    "geo_city": r.geo_city, "geo_lat": r.geo_lat, "geo_lon": r.geo_lon, "asn": r.asn,
                    "asn_name": r.asn_name, "asn_type": r.asn_type,
                    "tx_version": r.tx_version, "locktime": r.locktime, "rbf": r.rbf,
                }
            obs_rows.append({
                "id": f"obs_{r.txid[:12]}_{r.src_ip}_{int(ts.timestamp() * 1000)}", "timestamp": ts, "txid": r.txid,
                "src_ip": r.src_ip, "src_port": r.src_port, "dst_ip": r.dst_ip, "dst_port": r.dst_port,
                "geo_country": r.geo_country, "geo_city": r.geo_city, "geo_lat": r.geo_lat, "geo_lon": r.geo_lon,
                "asn": r.asn, "asn_name": r.asn_name, "asn_type": r.asn_type,
            })
        tx_tab = pa.Table.from_pylist(list(tx_rows.values()))
        obs_tab = pa.Table.from_pylist(obs_rows)
        conn = self.get_connection()
        tx_cols = ", ".join(tx_tab.column_names)
        obs_cols = ", ".join(obs_tab.column_names)
        conn.register("tx_in", tx_tab)
        conn.register("obs_in", obs_tab)
        conn.execute(f"INSERT OR IGNORE INTO transactions ({tx_cols}) SELECT {tx_cols} FROM tx_in")
        conn.execute(f"INSERT OR IGNORE INTO net_observations ({obs_cols}) SELECT {obs_cols} FROM obs_in")
        conn.close()

    def load_sidecar(self, table: str, path: Path, columns: List[str]):
        """Replace a ground-truth/seed table from a CSV next to the ingested file."""
        conn = self.get_connection()
        conn.execute(f"CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM read_csv_auto(?, all_varchar=true) LIMIT 0",
                     [str(path)])
        conn.execute(f"DELETE FROM {table}")
        conn.execute(f"INSERT INTO {table} SELECT * FROM read_csv_auto(?, all_varchar=true)", [str(path)])
        conn.close()

    def load_known_entities(self, path: Path) -> int:
        """Add/replace attribution rows (address, entity_name[, entity_type, country, in_jurisdiction, source])."""
        import csv as _csv
        with open(path, newline="") as fh:
            cols = {c.strip().lower() for c in (next(_csv.reader(fh), []) or [])}
        if not {"address", "entity_name"} <= cols:
            raise ValueError("known-entities CSV needs at least the columns: address, entity_name")
        col = lambda name, default: name if name in cols else default
        conn = self.get_connection()
        before = conn.execute("SELECT COUNT(*) FROM known_entities").fetchone()[0]
        conn.execute(f"""INSERT OR REPLACE INTO known_entities
            SELECT trim(address), entity_name, upper({col("entity_type", "'VASP'")}), upper({col("country", "'XX'")}),
                   COALESCE(TRY_CAST({col("in_jurisdiction", "NULL")} AS BOOLEAN), false), {col("source", "'INTEL_FILE'")}
            FROM read_csv_auto(?, all_varchar=true) WHERE address IS NOT NULL""", [str(path)])
        n = conn.execute("SELECT COUNT(*) FROM known_entities").fetchone()[0] - before
        conn.close()
        return n

    def get_all_transactions(self) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        res = conn.execute("SELECT * FROM transactions ORDER BY timestamp DESC").fetchdf()
        conn.close()
        return res.to_dict(orient="records")

    def get_all_alerts(self, limit: int = 200) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        res = conn.execute("SELECT * FROM alerts ORDER BY risk_score DESC, created_at DESC LIMIT ?", [limit]).fetchdf()
        conn.close()
        return res.to_dict(orient="records")
