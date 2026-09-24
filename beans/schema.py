"""Shared contracts between the three workstreams.

SHARED FILE: changing anything here affects Dharmik, Dhairya and Kavya. Tell the team before you
change it, and change it on `penultimate` so everyone gets it on their next merge.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

TXID_RE = re.compile(r"^[0-9a-f]{64}$")
BTC_P2P_PORTS = {8333, 18333, 38333, 18444}  # mainnet, testnet, signet, regtest


class ScriptType(str, Enum):
    P2PKH = "P2PKH"
    P2SH = "P2SH"
    P2WPKH = "P2WPKH"
    P2WSH = "P2WSH"
    P2TR = "P2TR"
    UNKNOWN = "UNKNOWN"


class AsnType(str, Enum):
    RESIDENTIAL = "RESIDENTIAL"
    MOBILE = "MOBILE"
    HOSTING = "HOSTING"
    VPN = "VPN"
    TOR = "TOR"
    UNKNOWN = "UNKNOWN"


class Typology(str, Enum):
    """Ground-truth wallet/entity labels produced by the synthetic generator."""
    NORMAL = "NORMAL"
    EXCHANGE = "EXCHANGE"
    MERCHANT = "MERCHANT"
    MINER = "MINER"
    RANSOMWARE = "RANSOMWARE"
    PEEL_CHAIN = "PEEL_CHAIN"
    COINJOIN = "COINJOIN"
    DARKNET_MARKET = "DARKNET_MARKET"
    HACK_LAUNDERING = "HACK_LAUNDERING"
    FAN_OUT_SMURF = "FAN_OUT_SMURF"
    ROUND_TRIP = "ROUND_TRIP"
    DUSTING = "DUSTING"


ILLICIT_TYPOLOGIES = {
    Typology.RANSOMWARE, Typology.PEEL_CHAIN, Typology.DARKNET_MARKET, Typology.HACK_LAUNDERING,
    Typology.FAN_OUT_SMURF, Typology.ROUND_TRIP, Typology.DUSTING,
}
# COINJOIN is privacy-seeking, not illicit by itself: it is a risk *signal*, not a label of guilt.


class TxClass(str, Enum):
    """Transaction-shape classes predicted by engine E3."""
    NORMAL = "normal"
    PEEL = "peel"
    COINJOIN = "coinjoin"
    FAN_OUT = "fan_out"
    FAN_IN = "fan_in"
    ROUND_TRIP = "round_trip"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


def severity_for(risk: float) -> Severity:
    if risk >= 85:
        return Severity.CRITICAL
    if risk >= 65:
        return Severity.HIGH
    if risk >= 40:
        return Severity.MEDIUM
    return Severity.LOW


class AlertType(str, Enum):
    RANSOMWARE_PATTERN = "RANSOMWARE_PATTERN"
    PEEL_CHAIN = "PEEL_CHAIN"
    MIXING = "MIXING"
    SEED_PROXIMITY = "SEED_PROXIMITY"
    ANOMALOUS_FLOW = "ANOMALOUS_FLOW"
    NETWORK_ANOMALY = "NETWORK_ANOMALY"
    CLUSTER_LINK = "CLUSTER_LINK"


class AlertStatus(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    CONFIRMED = "CONFIRMED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    CLOSED = "CLOSED"


class EntityType(str, Enum):
    WALLET = "wallet"
    CLUSTER = "cluster"
    TX = "tx"
    IP = "ip"


def alert_id_for(entity_type: str, entity_id: str) -> str:
    """Deterministic, so investigator status/notes survive a re-score."""
    return f"A-{entity_type[:1].upper()}-{hashlib.sha1(entity_id.encode()).hexdigest()[:10]}"


# ---------------------------------------------------------------- input record (one network observation)

class RawRecord(BaseModel):
    timestamp: datetime
    src_ip: str
    dst_ip: str
    src_port: int = Field(ge=0, le=65535)
    dst_port: int = Field(ge=0, le=65535)
    txid: str
    input_addresses: list[str]
    output_addresses: list[str]
    input_amounts: list[float]
    output_amounts: list[float]
    fee: float | None = None
    script_type: ScriptType = ScriptType.UNKNOWN
    geo_country: str | None = None
    asn: int | None = None
    block_height: int | None = None

    @field_validator("txid")
    @classmethod
    def _txid(cls, v: str) -> str:
        v = v.strip().lower()
        if not TXID_RE.match(v):
            raise ValueError("txid must be 64 hex chars")
        return v

    @model_validator(mode="after")
    def _lengths(self) -> "RawRecord":
        if len(self.input_addresses) != len(self.input_amounts):
            raise ValueError("input_addresses and input_amounts length mismatch")
        if len(self.output_addresses) != len(self.output_amounts):
            raise ValueError("output_addresses and output_amounts length mismatch")
        if not self.output_addresses:
            raise ValueError("transaction has no outputs")
        if any(a < 0 for a in self.input_amounts + self.output_amounts):
            raise ValueError("negative amount")
        return self


# ---------------------------------------------------------------- alert (what the API/UI consume)

class ShapItem(BaseModel):
    feature: str
    value: float | str | None
    impact: float  # signed contribution to the fused log-odds / probability


class Evidence(BaseModel):
    txids: list[str] = []
    addresses: list[str] = []
    ips: list[str] = []
    seed: str | None = None                 # nearest seed wallet, if any
    path_to_seed: list[str] | None = None   # ordered addresses from entity to seed
    peel_chain: list[str] | None = None     # ordered txids of the peel chain
    subgraph_center: str | None = None      # "wallet:<addr>" | "tx:<txid>" | "ip:<ip>" | "cluster:<id>"


class Alert(BaseModel):
    alert_id: str
    rank: int
    entity_type: EntityType
    entity_id: str
    alert_type: AlertType
    title: str
    risk: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    severity: Severity
    reasons: list[str]
    shap_top: list[ShapItem] = []
    engine_scores: dict[str, float] = {}
    evidence: Evidence = Evidence()
    member_count: int = 1
    created_at: datetime
