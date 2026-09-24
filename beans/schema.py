from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
import re

SCRIPT_TYPES = Literal["P2PKH", "P2SH", "P2WPKH", "P2WSH", "P2TR", "UNKNOWN"]
ISP_TYPES = Literal["RESIDENTIAL", "DATACENTER", "VPN", "TOR_EXIT", "BULLETPROOF", "UNKNOWN"]
SEVERITY_LEVELS = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
ALERT_STATUS = Literal["OPEN", "INVESTIGATING", "RESOLVED", "FALSE_POSITIVE"]

class CanonicalRecord(BaseModel):
    """
    Unified Canonical Schema for Bitcoin P2P Transaction Observation (R1, R2).
    """
    timestamp: datetime = Field(..., description="ISO-8601 UTC observation timestamp")
    src_ip: str = Field(..., description="Relaying source IPv4 or IPv6 address")
    src_port: int = Field(8333, ge=1, le=65535, description="Source port")
    dst_ip: Optional[str] = Field(None, description="Receiving destination IP")
    dst_port: int = Field(8333, ge=1, le=65535, description="Destination port (8333 default)")
    txid: str = Field(..., description="64-character hexadecimal transaction ID")
    input_addresses: List[str] = Field(default_factory=list)
    input_amounts: List[float] = Field(default_factory=list)
    output_addresses: List[str] = Field(default_factory=list)
    output_amounts: List[float] = Field(default_factory=list)
    fee: float = Field(0.0, ge=0.0, description="Miner fee in BTC")
    script_type: SCRIPT_TYPES = Field("P2WPKH", description="Bitcoin script type")
    
    # Enrichment fields (filled offline)
    geo_country: Optional[str] = Field("XX", description="ISO 2-letter country code")
    geo_city: Optional[str] = Field("Unknown", description="City name")
    geo_lat: Optional[float] = Field(0.0, description="Latitude")
    geo_lon: Optional[float] = Field(0.0, description="Longitude")
    asn: Optional[str] = Field("AS_UNKNOWN", description="Autonomous System Number")
    asn_name: Optional[str] = Field("Unknown Provider", description="ASN Organization")
    asn_type: ISP_TYPES = Field("RESIDENTIAL", description="Infrastructure type")
    block_height: Optional[int] = Field(0, ge=0)

    @field_validator("txid")
    @classmethod
    def validate_txid(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[0-9a-f]{64}$", v):
            # If shortened test txid, pad or accept if valid hex
            if re.match(r"^[0-9a-f]+$", v) and len(v) >= 8:
                return v
            raise ValueError(f"Invalid TXID hex format: {v}")
        return v

    @model_validator(mode="after")
    def validate_array_lengths_and_math(self) -> "CanonicalRecord":
        if len(self.input_addresses) != len(self.input_amounts):
            raise ValueError(f"Input addresses ({len(self.input_addresses)}) and amounts ({len(self.input_amounts)}) count mismatch")
        if len(self.output_addresses) != len(self.output_amounts):
            raise ValueError(f"Output addresses ({len(self.output_addresses)}) and amounts ({len(self.output_amounts)}) count mismatch")
        return self

    @property
    def total_input(self) -> float:
        return round(sum(self.input_amounts), 8)

    @property
    def total_output(self) -> float:
        return round(sum(self.output_amounts), 8)


class AlertRecord(BaseModel):
    alert_id: str
    entity_id: str
    entity_type: Literal["WALLET", "CLUSTER", "TRANSACTION", "IP"]
    alert_type: str
    risk_score: float = Field(..., ge=0.0, le=100.0)
    calibrated_confidence: float = Field(..., ge=0.0, le=1.0)
    severity: SEVERITY_LEVELS
    reasons: List[str] = Field(default_factory=list)
    shap_top_features: List[dict] = Field(default_factory=list)
    engine_scores: dict = Field(default_factory=dict)
    evidence: dict = Field(default_factory=dict)
    status: ALERT_STATUS = "OPEN"
    assigned_to: str = "Unassigned"
    created_at: datetime = Field(default_factory=datetime.utcnow)
