from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.app.db.database import get_db
from backend.app.models.schema import NetworkObservation, ThreatIntel
from backend.app.services.ingestion import IngestionPipeline
from backend.app.schemas.pydantic_schemas import BatchNetworkPayload, BatchThreatIntelPayload

router = APIRouter(prefix="/network", tags=["Network & SIGINT"])

@router.get("/observations")
def list_network_observations(
    isp_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(NetworkObservation)
    if isp_type and isp_type != "ALL":
        query = query.filter(NetworkObservation.isp_type == isp_type)
    
    logs = query.order_by(NetworkObservation.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": l.id,
            "timestamp": l.timestamp.isoformat(),
            "src_ip": l.src_ip,
            "dst_ip": l.dst_ip,
            "src_port": l.src_port,
            "dst_port": l.dst_port,
            "src_asn": l.src_asn,
            "src_asn_name": l.src_asn_name,
            "src_country": l.src_country,
            "src_city": l.src_city,
            "src_lat": l.src_lat,
            "src_lon": l.src_lon,
            "isp_type": l.isp_type,
            "protocol": l.protocol
        }
        for l in logs
    ]

@router.get("/threat-intel")
def list_threat_intel(
    threat_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(ThreatIntel)
    if threat_type and threat_type != "ALL":
        query = query.filter(ThreatIntel.threat_type == threat_type)
    
    intel = query.order_by(ThreatIntel.created_at.desc()).limit(limit).all()
    return [
        {
            "id": i.id,
            "entity_type": i.entity_type,
            "entity_id": i.entity_id,
            "source": i.source,
            "threat_type": i.threat_type,
            "incident_name": i.incident_name,
            "confidence": i.confidence,
            "notes": i.notes,
            "created_at": i.created_at.isoformat()
        }
        for i in intel
    ]

@router.post("/ingest-network")
def ingest_network(payload: BatchNetworkPayload, db: Session = Depends(get_db)):
    raw_list = [o.dict() for o in payload.observations]
    return IngestionPipeline.ingest_network_observations(db, raw_list)

@router.post("/ingest-threat-intel")
def ingest_threats(payload: BatchThreatIntelPayload, db: Session = Depends(get_db)):
    raw_list = [t.dict() for t in payload.threat_entities]
    return IngestionPipeline.ingest_threat_intel(db, raw_list)
