from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

from backend.app.db.database import get_db
from backend.app.models.schema import WalletProfile, Transaction, ThreatIntel, Alert
from backend.app.schemas.pydantic_schemas import WalletProfileResponse

router = APIRouter(prefix="/entities", tags=["Entities"])

@router.get("/wallets", response_model=List[WalletProfileResponse])
def list_wallets(
    threat_class: Optional[str] = Query(None),
    min_score: Optional[float] = Query(0.0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    query = db.query(WalletProfile)
    if threat_class and threat_class != "ALL":
        query = query.filter(WalletProfile.threat_classification == threat_class)
    if min_score > 0:
        query = query.filter(WalletProfile.risk_score >= min_score)

    wallets = query.order_by(WalletProfile.risk_score.desc()).limit(limit).all()

    return [
        WalletProfileResponse(
            address=w.address,
            first_seen=w.first_seen,
            last_seen=w.last_seen,
            transaction_count=w.transaction_count,
            total_received=float(w.total_received or 0.0),
            total_sent=float(w.total_sent or 0.0),
            balance=float(w.balance or 0.0),
            mixing_participation=bool(w.mixing_participation),
            risk_score=float(w.risk_score or 0.0),
            threat_classification=w.threat_classification or "UNKNOWN",
            cluster_id=w.cluster_id,
            tags=w.get_tags(),
            associated_ips=w.get_associated_ips()
        )
        for w in wallets
    ]

@router.get("/wallet/{address}")
def get_wallet_360_profile(address: str, db: Session = Depends(get_db)):
    wallet = db.query(WalletProfile).filter(WalletProfile.address == address).first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet profile not found")

    # Get all transactions involving this wallet
    all_txs = db.query(Transaction).all()
    wallet_txs = []
    for tx in all_txs:
        ins = tx.get_input_addrs()
        outs = tx.get_output_addrs()
        if address in ins or address in outs:
            wallet_txs.append({
                "txid": tx.txid,
                "timestamp": tx.timestamp.isoformat(),
                "role": "SENDER" if address in ins else "RECIPIENT",
                "total_value": tx.total_output,
                "fee": tx.fee,
                "input_count": len(ins),
                "output_count": len(outs),
                "script_type": tx.script_type,
                "observed_ips": tx.get_observed_ips()
            })

    # Sort chronological
    wallet_txs.sort(key=lambda x: x["timestamp"])

    # Threat intel matches
    threats = db.query(ThreatIntel).filter(ThreatIntel.entity_id == address).all()
    # Alerts
    alerts = db.query(Alert).filter(Alert.entity_id == address).all()

    return {
        "profile": {
            "address": wallet.address,
            "first_seen": wallet.first_seen.isoformat(),
            "last_seen": wallet.last_seen.isoformat(),
            "transaction_count": wallet.transaction_count,
            "total_received": float(wallet.total_received or 0.0),
            "total_sent": float(wallet.total_sent or 0.0),
            "balance": float(wallet.balance or 0.0),
            "mixing_participation": wallet.mixing_participation,
            "risk_score": float(wallet.risk_score or 0.0),
            "threat_classification": wallet.threat_classification,
            "cluster_id": wallet.cluster_id,
            "tags": wallet.get_tags(),
            "associated_ips": wallet.get_associated_ips()
        },
        "transactions": wallet_txs,
        "osint_matches": [
            {
                "source": t.source,
                "threat_type": t.threat_type,
                "incident_name": t.incident_name,
                "confidence": t.confidence,
                "notes": t.notes
            }
            for t in threats
        ],
        "alerts": [
            {
                "id": a.id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "reason": a.reason,
                "automated_score": a.automated_score,
                "status": a.status,
                "evidence": a.get_evidence()
            }
            for a in alerts
        ]
    }
