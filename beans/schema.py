from datetime import datetime
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
import re

SCRIPT_TYPES = Literal["P2PKH", "P2SH", "P2WPKH", "P2WSH", "P2TR", "UNKNOWN"]
ISP_TYPES = Literal["RESIDENTIAL", "DATACENTER", "VPN", "TOR_EXIT", "BULLETPROOF", "UNKNOWN"]
SEVERITY_LEVELS = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
ALERT_STATUS = Literal["OPEN", "INVESTIGATING", "RESOLVED", "FALSE_POSITIVE"]

class CanonicalRecord(BaseModel):
    """
    Unified Canonical Schema for Bitcoin P2P Transaction Observation (R1, R2).
    """
    model_config = ConfigDict(extra="ignore")

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
            if re.match(r"^[0-9a-f]+$", v) and len(v) >= 8:
                return v
            raise ValueError(f"Invalid TXID hex format: {v}")
        return v

    @property
    def total_input(self) -> float:
        return round(sum(self.input_amounts), 8)

    @property
    def total_output(self) -> float:
        return round(sum(self.output_amounts), 8)


class Alert(BaseModel):
    """
    Contract-compatible Alert model (R6).
    """
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    alert_id: str
    entity_type: str = "cluster"
    entity_id: str
    alert_type: str
    title: Optional[str] = None
    risk: float = Field(default=50.0, ge=0.0, le=100.0)
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    severity: str = "HIGH"
    reasons: List[str] = Field(default_factory=list)
    shap_top: List[Dict[str, Any]] = Field(default_factory=list)
    engine_scores: Dict[str, Any] = Field(default_factory=dict)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    rank: Optional[int] = None
    member_count: Optional[int] = None
    status: str = "OPEN"
    assigned_to: Optional[str] = "Unassigned"
    created_at: Optional[Any] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if "risk_score" in values and "risk" not in values:
                values["risk"] = values["risk_score"]
            if "calibrated_confidence" in values and "confidence" not in values:
                values["confidence"] = values["calibrated_confidence"]
            if "shap_top_features" in values and "shap_top" not in values:
                values["shap_top"] = values["shap_top_features"]
        return values

    @property
    def risk_score(self) -> float:
        return self.risk

    @property
    def calibrated_confidence(self) -> float:
        return self.confidence

    @property
    def shap_top_features(self) -> List[Dict[str, Any]]:
        return self.shap_top


# Contract Aliases
RawRecord = CanonicalRecord
AlertRecord = Alert
