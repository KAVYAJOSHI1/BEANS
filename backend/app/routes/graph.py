from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from backend.app.db.database import get_db
from backend.app.services.graph_engine import ForensicsGraphEngine

router = APIRouter(prefix="/graph", tags=["Forensic Graph"])

@router.get("/topology")
def get_graph_topology(
    center_node: Optional[str] = Query(None, description="Center address or txid"),
    max_hops: int = Query(2, ge=1, le=5),
    limit_nodes: int = Query(100, ge=10, le=300),
    db: Session = Depends(get_db)
):
    """
    Returns multi-layer forensic graph (Wallets, Transactions, IPs) 
    compatible with Cytoscape.js and React visualizer.
    """
    return ForensicsGraphEngine.build_subgraph(
        db=db,
        center_node=center_node,
        max_hops=max_hops,
        limit_nodes=limit_nodes
    )
