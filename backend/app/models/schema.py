from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, Text
from datetime import datetime
import json
from backend.app.db.database import Base

class Transaction(Base):
    __tablename__ = "transactions"

    txid = Column(String(64), primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    input_addresses = Column(Text, nullable=False)  # JSON string of List[str]
    output_addresses = Column(Text, nullable=False) # JSON string of List[str]
    input_amounts = Column(Text, nullable=False)   # JSON string of List[float]
    output_amounts = Column(Text, nullable=False)  # JSON string of List[float]
    total_input = Column(Float, default=0.0)
    total_output = Column(Float, default=0.0)
    fee = Column(Float, default=0.0)
    script_type = Column(String(50), default="P2WPKH")
    block_height = Column(Integer, default=0)
    observed_ips = Column(Text, default="[]")       # JSON string of List[str]
    created_at = Column(DateTime, default=datetime.utcnow)

    def get_input_addrs(self):
        try:
            return json.loads(self.input_addresses) if self.input_addresses else []
        except Exception:
            return []

    def get_output_addrs(self):
        try:
            return json.loads(self.output_addresses) if self.output_addresses else []
        except Exception:
            return []

    def get_input_amts(self):
        try:
            return json.loads(self.input_amounts) if self.input_amounts else []
        except Exception:
            return []

    def get_output_amts(self):
        try:
            return json.loads(self.output_amounts) if self.output_amounts else []
        except Exception:
            return []

    def get_observed_ips(self):
        try:
            return json.loads(self.observed_ips) if self.observed_ips else []
        except Exception:
            return []


class NetworkObservation(Base):
    __tablename__ = "network_observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    src_ip = Column(String(45), nullable=False, index=True)
    dst_ip = Column(String(45), nullable=True)
    src_port = Column(Integer, default=8333)
    dst_port = Column(Integer, default=8333)
    src_asn = Column(String(30), default="AS_UNKNOWN")
    src_asn_name = Column(String(100), default="Unknown ASN")
    src_country = Column(String(10), default="XX")
    src_city = Column(String(100), default="Unknown")
    src_lat = Column(Float, default=0.0)
    src_lon = Column(Float, default=0.0)
    dst_asn = Column(String(30), default="AS_UNKNOWN")
    dst_country = Column(String(10), default="XX")
    bytes_in = Column(Integer, default=0)
    bytes_out = Column(Integer, default=0)
    protocol = Column(String(10), default="TCP")
    isp_type = Column(String(30), default="RESIDENTIAL")  # BULLETPROOF, VPN, TOR_EXIT, RESIDENTIAL, DATACENTER
    created_at = Column(DateTime, default=datetime.utcnow)


class ThreatIntel(Base):
    __tablename__ = "threat_intelligence"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(30), nullable=False, default="WALLET") # WALLET, IP, ASN
    entity_id = Column(String(256), nullable=False, index=True)
    source = Column(String(100), nullable=False) # OFAC, CHAINALYSIS, FBI_BULLETIN, LE_TIP, CERT_ALERT
    threat_type = Column(String(100), nullable=False) # RANSOMWARE, MIXING, SANCTIONS, THEFT_HACK, DARKNET
    incident_name = Column(String(256), nullable=False)
    confidence = Column(Float, default=0.9) # 0.0 to 1.0
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class WalletProfile(Base):
    __tablename__ = "wallet_profiles"

    address = Column(String(64), primary_key=True, index=True)
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    transaction_count = Column(Integer, default=0)
    total_received = Column(Float, default=0.0)
    total_sent = Column(Float, default=0.0)
    balance = Column(Float, default=0.0)
    mixing_participation = Column(Boolean, default=False)
    risk_score = Column(Float, default=0.0, index=True)
    threat_classification = Column(String(50), default="UNKNOWN") # RANSOMWARE, MIXING, THEFT_HACK, DARKNET, EXCHANGE, UNKNOWN
    cluster_id = Column(String(64), nullable=True, index=True)
    tags = Column(Text, default="[]") # JSON list of string tags
    associated_ips = Column(Text, default="[]") # JSON list of IPs
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_tags(self):
        try:
            return json.loads(self.tags) if self.tags else []
        except Exception:
            return []

    def get_associated_ips(self):
        try:
            return json.loads(self.associated_ips) if self.associated_ips else []
        except Exception:
            return []


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(30), nullable=False, default="WALLET") # WALLET, TRANSACTION, IP
    entity_id = Column(String(256), nullable=False, index=True)
    alert_type = Column(String(100), nullable=False) # RANSOMWARE_SIG, MIXING_DETECTED, THEFT_LAUNDERING, GEO_ANOMALY, BULLETPROOF_IP, RAPID_SUBDIVISION
    severity = Column(String(20), default="HIGH", index=True) # CRITICAL, HIGH, MEDIUM, LOW
    reason = Column(Text, nullable=False)
    evidence_breakdown = Column(Text, default="[]") # JSON list of strings/objects
    score_components = Column(Text, default="{}")   # JSON dict of score sub-values
    automated_score = Column(Float, default=0.0, index=True)
    investigator_confidence = Column(Float, default=0.0) # 0 to 100
    status = Column(String(30), default="OPEN", index=True) # OPEN, INVESTIGATING, RESOLVED, FALSE_POSITIVE
    assigned_to = Column(String(100), default="Unassigned")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_evidence(self):
        try:
            return json.loads(self.evidence_breakdown) if self.evidence_breakdown else []
        except Exception:
            return []

    def get_score_components(self):
        try:
            return json.loads(self.score_components) if self.score_components else {}
        except Exception:
            return {}


class CaseFile(Base):
    __tablename__ = "case_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_name = Column(String(256), nullable=False, index=True)
    incident_type = Column(String(100), nullable=False)
    suspect_entities = Column(Text, default="[]") # JSON list of wallet addresses or IPs
    linked_txids = Column(Text, default="[]")     # JSON list of txids
    notes = Column(Text, default="")
    investigator = Column(String(100), default="Senior Investigator")
    status = Column(String(30), default="OPEN") # OPEN, IN_PROGRESS, REFERRED_TO_LE, CLOSED
    priority = Column(String(20), default="HIGH")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_entities(self):
        try:
            return json.loads(self.suspect_entities) if self.suspect_entities else []
        except Exception:
            return []

    def get_txids(self):
        try:
            return json.loads(self.linked_txids) if self.linked_txids else []
        except Exception:
            return []


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(100), nullable=False)
    investigator = Column(String(100), default="System")
    entity_type = Column(String(30), nullable=True)
    entity_id = Column(String(256), nullable=True)
    details = Column(Text, default="{}") # JSON dict
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class SystemConfig(Base):
    __tablename__ = "system_config"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
