from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# --- Ingestion Schemas ---
class TransactionInput(BaseModel):
    txid: str
    timestamp: datetime
    input_addresses: List[str]
    output_addresses: List[str]
    input_amounts: List[float]
    output_amounts: List[float]
    fee: float = 0.0
    script_type: str = "P2WPKH"
    block_height: Optional[int] = 0
    observed_ips: Optional[List[str]] = []

class BatchTransactionPayload(BaseModel):
    transactions: List[TransactionInput]

class NetworkObservationInput(BaseModel):
    timestamp: datetime
    src_ip: str
    dst_ip: Optional[str] = None
    src_port: int = 8333
    dst_port: int = 8333
    src_asn: Optional[str] = "AS_UNKNOWN"
    src_asn_name: Optional[str] = "Unknown Provider"
    src_country: Optional[str] = "XX"
    src_city: Optional[str] = "Unknown"
    src_lat: Optional[float] = 0.0
    src_lon: Optional[float] = 0.0
    protocol: Optional[str] = "TCP"
    isp_type: Optional[str] = "RESIDENTIAL" # BULLETPROOF, VPN, TOR_EXIT, RESIDENTIAL, DATACENTER

class BatchNetworkPayload(BaseModel):
    observations: List[NetworkObservationInput]

class ThreatIntelInput(BaseModel):
    entity_type: str = "WALLET"
    entity_id: str
    source: str
    threat_type: str
    incident_name: str
    confidence: float = 0.95
    notes: Optional[str] = ""

class BatchThreatIntelPayload(BaseModel):
    threat_entities: List[ThreatIntelInput]

# --- Response Schemas ---
class AlertResponse(BaseModel):
    id: int
    entity_type: str
    entity_id: str
    alert_type: str
    severity: str
    reason: str
    evidence_breakdown: List[Any]
    score_components: Dict[str, Any]
    automated_score: float
    investigator_confidence: float
    status: str
    assigned_to: str
    created_at: datetime

class AlertStatusUpdate(BaseModel):
    status: str
    investigator_confidence: Optional[float] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = None

class WalletProfileResponse(BaseModel):
    address: str
    first_seen: datetime
    last_seen: datetime
    transaction_count: int
    total_received: float
    total_sent: float
    balance: float
    mixing_participation: bool
    risk_score: float
    threat_classification: str
    cluster_id: Optional[str]
    tags: List[str]
    associated_ips: List[str]

class CaseCreate(BaseModel):
    case_name: str
    incident_type: str
    suspect_entities: List[str]
    linked_txids: Optional[List[str]] = []
    notes: Optional[str] = ""
    investigator: Optional[str] = "Senior Investigator"
    priority: Optional[str] = "HIGH"

class CaseUpdate(BaseModel):
    case_name: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    suspect_entities: Optional[List[str]] = None
    linked_txids: Optional[List[str]] = None

class ScoringConfigUpdate(BaseModel):
    weight_pattern: float
    weight_osint: float
    weight_sigint_geo: float
    weight_temporal_velocity: float
    geo_velocity_threshold: float
    fan_out_threshold: float
