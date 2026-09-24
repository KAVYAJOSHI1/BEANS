import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from beans.api import db

router = APIRouter(prefix="/graph", tags=["Link Graph"])

TXID_RE = re.compile(r"^[0-9a-f]{64}$")
IP_RE = re.compile(r"^[0-9a-fA-F:.]+$")
TX_COLS = "txid, timestamp, input_addresses, output_addresses, input_amounts, output_amounts, total_output, fee, " \
          "src_ip, geo_country, asn, asn_type"


def _txs_touching(wallets: List[str], limit: int) -> List[Dict[str, Any]]:
    return db.query(
        f"SELECT {TX_COLS} FROM transactions WHERE list_has_any(input_addresses, ?::VARCHAR[]) "
        "OR list_has_any(output_addresses, ?::VARCHAR[]) ORDER BY timestamp LIMIT ?",
        [wallets, wallets, limit])


def _expand(center: Optional[str], hops: int, limit: int) -> tuple[List[Dict[str, Any]], List[str]]:
    """Collect the transactions within `hops` wallet-hops of the center (or of the top alerts)."""
    if center and TXID_RE.match(center.lower()):
        start = db.query(f"SELECT {TX_COLS} FROM transactions WHERE txid = ?", [center.lower()])
    elif center and IP_RE.match(center) and ("." in center or ":" in center) and not center.startswith("bc1"):
        start = db.query(f"SELECT {TX_COLS} FROM transactions WHERE src_ip = ? LIMIT ?", [center, limit])
    elif center:
        start = _txs_touching([center], limit)
    else:  # default view: neighbourhood of the highest-risk alerted wallets
        top = [r["entity_id"] for r in db.query(
            "SELECT entity_id FROM alerts WHERE entity_type = 'WALLET' ORDER BY risk_score DESC LIMIT 12")]
        start = _txs_touching(top, limit) if top else db.query(
            f"SELECT {TX_COLS} FROM transactions ORDER BY timestamp DESC LIMIT ?", [limit])
    if center and not start:
        raise HTTPException(404, f"nothing found for {center}")

    txs = {t["txid"]: t for t in start}
    frontier = {w for t in start for w in (t["input_addresses"] or []) + (t["output_addresses"] or [])}
    seen = set(frontier)
    for _ in range(hops - 1):
        if len(txs) >= limit or not frontier:
            break
        for t in _txs_touching(sorted(frontier), limit - len(txs)):
            txs.setdefault(t["txid"], t)
        frontier = {w for t in txs.values() for w in (t["input_addresses"] or []) + (t["output_addresses"] or [])} - seen
        seen |= frontier
    return list(txs.values())[:limit], sorted(seen)


@router.get("/topology")
def get_graph_topology(
    center: Optional[str] = Query(None, description="wallet address, txid or IP"),
    hops: int = Query(2, ge=1, le=4),
    min_risk: float = Query(0.0, ge=0, le=100),
    limit: int = Query(120, ge=10, le=400),
) -> Dict[str, Any]:
    txs, wallets = _expand(center, hops, limit)

    risk = {r["entity_id"]: r for r in db.query(
        "SELECT entity_id, risk_score, alert_type, severity, evidence FROM alerts WHERE list_contains(?, entity_id)",
        [wallets])} if wallets else {}
    seeds = {r["address"] for r in db.query("SELECT address FROM seeds")}
    profiles = {r["address"]: r for r in db.query(
        "SELECT address, cluster_id, threat_classification FROM wallet_profiles WHERE list_contains(?, address)",
        [wallets])} if wallets else {}

    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []

    def wallet_node(addr: str) -> Optional[str]:
        meta = risk.get(addr, {})
        score = float(meta.get("risk_score") or 0.0)
        keep = score >= min_risk or addr == center or addr in seeds
        if not keep:
            return None
        nid = f"w_{addr}"
        nodes.setdefault(nid, {
            "id": nid, "type": "WALLET", "label": f"{addr[:6]}…{addr[-4:]}", "full_id": addr,
            "risk_score": score, "alert_type": meta.get("alert_type", "NONE"), "severity": meta.get("severity", "LOW"),
            "is_seed": addr in seeds, "is_center": addr == center,
            "cluster_id": profiles.get(addr, {}).get("cluster_id", "SOLO"),
        })
        return nid

    for t in txs:
        tid = f"tx_{t['txid'][:12]}"
        nodes[tid] = {"id": tid, "type": "TRANSACTION", "label": f"TX {t['txid'][:8]}", "full_id": t["txid"],
                      "value": t["total_output"] or 0.0, "fee": t["fee"] or 0.0, "timestamp": t["timestamp"],
                      "n_inputs": len(t["input_addresses"] or []), "n_outputs": len(t["output_addresses"] or [])}
        if t["src_ip"]:
            iid = f"ip_{t['src_ip']}"
            nodes.setdefault(iid, {"id": iid, "type": "IP", "label": t["src_ip"], "full_id": t["src_ip"],
                                   "country": t["geo_country"], "asn": t["asn"], "isp_type": t["asn_type"],
                                   "risk_score": 0.0})
            edges.append({"source": iid, "target": tid, "type": "RELAYED", "label": "first relayed"})
        for addr, amt in zip(t["input_addresses"] or [], t["input_amounts"] or []):
            if (w := wallet_node(addr)):
                edges.append({"source": w, "target": tid, "type": "INPUT", "label": f"{amt:.4f}", "amount": amt})
        for addr, amt in zip(t["output_addresses"] or [], t["output_amounts"] or []):
            if (w := wallet_node(addr)):
                edges.append({"source": tid, "target": w, "type": "OUTPUT", "label": f"{amt:.4f}", "amount": amt})

    # Evidence overlays the UI can highlight: path to the nearest seed and the peel chain of the center
    highlight: Dict[str, List[str]] = {"path_to_seed": [], "txids": []}
    if center and center in risk:
        ev = risk[center].get("evidence") or {}
        highlight["path_to_seed"] = [f"w_{a}" for a in (ev.get("path_to_seed") or [])]
        highlight["txids"] = [f"tx_{x[:12]}" for x in ([ev["txid"]] if ev.get("txid") else [])]

    return {
        "nodes": [{"data": n} for n in nodes.values()],
        "edges": [{"data": {"id": f"e_{i}", **e}} for i, e in enumerate(edges)],
        "highlight": highlight,
        "summary": {"center": center, "hops": hops, "node_count": len(nodes), "edge_count": len(edges),
                    "transactions": len(txs)},
    }
