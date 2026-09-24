from fastapi import APIRouter, Query
from typing import Dict, Any, Optional
import networkx as nx
from beans.store.duck import DuckStore

router = APIRouter(prefix="/graph", tags=["Link Graph"])

@router.get("/topology")
def get_graph_topology(
    center: Optional[str] = Query(None),
    hops: int = Query(2, ge=1, le=4),
    min_risk: float = Query(0.0),
    limit: int = Query(100, ge=10, le=300)
) -> Dict[str, Any]:
    store = DuckStore()
    conn = store.get_connection()

    tx_df = conn.execute("SELECT * FROM transactions ORDER BY timestamp DESC LIMIT ?", [limit]).fetchdf()
    alert_df = conn.execute("SELECT entity_id, risk_score, alert_type, severity FROM alerts").fetchdf()
    seed_df = conn.execute("SELECT address FROM seeds").fetchdf()

    conn.close()

    risk_map = {row["entity_id"]: row for row in alert_df.to_dict(orient="records")}
    seed_set = set(seed_df["address"].tolist()) if not seed_df.empty else set()

    G = nx.MultiDiGraph()

    for r in tx_df.to_dict(orient="records"):
        txid = r["txid"]
        tx_node = f"tx_{txid[:10]}"
        
        G.add_node(
            tx_node,
            type="TRANSACTION",
            label=f"TX: {txid[:8]}",
            full_id=txid,
            fee=float(r.get("fee", 0.0)),
            value=float(r.get("total_output", 0.0)),
            timestamp=str(r.get("timestamp"))
        )

        # IP node
        src_ip = r.get("src_ip")
        if src_ip:
            ip_node = f"ip_{src_ip}"
            G.add_node(
                ip_node,
                type="IP",
                label=f"IP: {src_ip}",
                full_id=src_ip,
                country=r.get("geo_country"),
                asn=r.get("asn"),
                isp_type=r.get("asn_type")
            )
            G.add_edge(ip_node, tx_node, type="RELAYED", label="Relayed")

        # Inputs
        in_addrs = list(r.get("input_addresses")) if r.get("input_addresses") is not None else []
        for addr in in_addrs:
            w_node = f"w_{addr}"
            meta = risk_map.get(addr, {})
            is_seed = addr in seed_set
            G.add_node(
                w_node,
                type="WALLET",
                label=f"{addr[:6]}...{addr[-4:]}",
                full_id=addr,
                risk_score=float(meta.get("risk_score", 0.0)),
                alert_type=meta.get("alert_type", "NORMAL"),
                severity=meta.get("severity", "LOW"),
                is_seed=is_seed
            )
            G.add_edge(w_node, tx_node, type="INPUT", label="Spends")

        # Outputs
        out_addrs = list(r.get("output_addresses")) if r.get("output_addresses") is not None else []
        for addr in out_addrs:
            w_node = f"w_{addr}"
            meta = risk_map.get(addr, {})
            is_seed = addr in seed_set
            G.add_node(
                w_node,
                type="WALLET",
                label=f"{addr[:6]}...{addr[-4:]}",
                full_id=addr,
                risk_score=float(meta.get("risk_score", 0.0)),
                alert_type=meta.get("alert_type", "NORMAL"),
                severity=meta.get("severity", "LOW"),
                is_seed=is_seed
            )
            G.add_edge(tx_node, w_node, type="OUTPUT", label="Pays")

    # Filter center if provided
    if center:
        c_node = f"w_{center}" if not center.startswith("tx_") and not center.startswith("ip_") else center
        if c_node in G:
            sub_nodes = set([c_node])
            frontier = set([c_node])
            for _ in range(hops):
                nxt = set()
                for n in frontier:
                    nxt.update(G.predecessors(n))
                    nxt.update(G.successors(n))
                sub_nodes.update(nxt)
                frontier = nxt
            G = G.subgraph(list(sub_nodes))

    elements_nodes = [{"data": {"id": str(n), **data}} for n, data in G.nodes(data=True)]
    elements_edges = [
        {"data": {"id": f"e_{i}", "source": str(u), "target": str(v), **data}}
        for i, (u, v, k, data) in enumerate(G.edges(keys=True, data=True))
    ]

    return {
        "nodes": elements_nodes,
        "edges": elements_edges,
        "summary": {
            "node_count": len(elements_nodes),
            "edge_count": len(elements_edges)
        }
    }
