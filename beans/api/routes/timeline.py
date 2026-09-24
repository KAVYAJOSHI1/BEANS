from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from beans.api import db

router = APIRouter(prefix="/timeline", tags=["Timeline Replay"])


@router.get("/sequence")
def get_timeline_sequence(
    entity: Optional[str] = Query(None, description="wallet address to follow; default = highest-risk alert"),
    limit: int = Query(50, ge=1, le=500),
) -> List[Dict[str, Any]]:
    if not entity:
        top = db.one("SELECT entity_id FROM alerts WHERE entity_type = 'WALLET' ORDER BY risk_score DESC LIMIT 1")
        entity = top["entity_id"] if top else None
    cols = ("txid, timestamp, input_addresses, output_addresses, input_amounts, output_amounts, total_output, fee, "
            "src_ip, geo_country, asn, asn_type")
    if entity:
        rows = db.query(f"SELECT {cols} FROM transactions WHERE list_contains(input_addresses, ?) "
                        "OR list_contains(output_addresses, ?) ORDER BY timestamp LIMIT ?", [entity, entity, limit])
    else:
        rows = db.query(f"SELECT {cols} FROM transactions ORDER BY timestamp LIMIT ?", [limit])

    events = []
    for i, r in enumerate(rows, 1):
        ins, outs = r["input_addresses"] or [], r["output_addresses"] or []
        amounts = sorted(r["output_amounts"] or [], reverse=True)
        events.append({
            "step": i, "entity": entity, "txid": r["txid"], "timestamp": r["timestamp"],
            "inputs_count": len(ins), "outputs_count": len(outs),
            "amount_btc": r["total_output"] or 0.0, "fee_btc": r["fee"] or 0.0,
            "src_ip": r["src_ip"], "geo_country": r["geo_country"], "asn": r["asn"], "asn_type": r["asn_type"],
            "direction": "OUT" if entity in ins else "IN",
            # peel shape: one input, two outputs, one output much smaller than the other
            "is_peel": len(ins) == 1 and len(outs) == 2 and amounts[1] < 0.25 * amounts[0],
            "is_split": len(outs) >= 5,
        })
    return events
