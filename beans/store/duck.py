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
        """)
        conn.close()

    def insert_records(self, records: List[CanonicalRecord]):
        if not records:
            return
        conn = self.get_connection()
        for r in records:
            # Upsert transaction
            conn.execute("""
            INSERT OR REPLACE INTO transactions (
                txid, timestamp, input_addresses, input_amounts, output_addresses, output_amounts,
                total_input, total_output, fee, script_type, block_height, src_ip, src_port,
                dst_ip, dst_port, geo_country, geo_city, geo_lat, geo_lon, asn, asn_name, asn_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                r.txid, r.timestamp, r.input_addresses, r.input_amounts, r.output_addresses, r.output_amounts,
                r.total_input, r.total_output, r.fee, r.script_type, r.block_height, r.src_ip, r.src_port,
                r.dst_ip, r.dst_port, r.geo_country, r.geo_city, r.geo_lat, r.geo_lon, r.asn, r.asn_name, r.asn_type
            ])

            # Insert net observation
            obs_id = f"obs_{r.txid[:12]}_{r.src_ip}_{int(r.timestamp.timestamp())}"
            conn.execute("""
            INSERT OR REPLACE INTO net_observations (
                id, timestamp, txid, src_ip, src_port, dst_ip, dst_port,
                geo_country, geo_city, geo_lat, geo_lon, asn, asn_name, asn_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                obs_id, r.timestamp, r.txid, r.src_ip, r.src_port, r.dst_ip, r.dst_port,
                r.geo_country, r.geo_city, r.geo_lat, r.geo_lon, r.asn, r.asn_name, r.asn_type
            ])

        conn.close()

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
