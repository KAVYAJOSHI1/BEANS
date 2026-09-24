from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.app.db.database import get_db
from backend.app.models.schema import Transaction
from backend.app.services.ingestion import IngestionPipeline
from backend.app.schemas.pydantic_schemas import BatchTransactionPayload

router = APIRouter(prefix="/transactions", tags=["Transactions"])

@router.get("")
def list_transactions(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    txs = db.query(Transaction).order_by(Transaction.timestamp.desc()).limit(limit).all()
    return [
        {
            "txid": t.txid,
            "timestamp": t.timestamp.isoformat(),
            "input_addresses": t.get_input_addrs(),
            "output_addresses": t.get_output_addrs(),
            "input_amounts": t.get_input_amts(),
            "output_amounts": t.get_output_amts(),
            "total_input": t.total_input,
            "total_output": t.total_output,
            "fee": t.fee,
            "script_type": t.script_type,
            "block_height": t.block_height,
            "observed_ips": t.get_observed_ips()
        }
        for t in txs
    ]

@router.get("/{txid}")
def get_transaction(txid: str, db: Session = Depends(get_db)):
    tx = db.query(Transaction).filter(Transaction.txid == txid).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {
        "txid": tx.txid,
        "timestamp": tx.timestamp.isoformat(),
        "input_addresses": tx.get_input_addrs(),
        "output_addresses": tx.get_output_addrs(),
        "input_amounts": tx.get_input_amts(),
        "output_amounts": tx.get_output_amts(),
        "total_input": tx.total_input,
        "total_output": tx.total_output,
        "fee": tx.fee,
        "script_type": tx.script_type,
        "block_height": tx.block_height,
        "observed_ips": tx.get_observed_ips()
    }

@router.post("/ingest")
def ingest_transactions(payload: BatchTransactionPayload, db: Session = Depends(get_db)):
    raw_list = [t.dict() for t in payload.transactions]
    result = IngestionPipeline.ingest_transactions(db, raw_list)
    return result
