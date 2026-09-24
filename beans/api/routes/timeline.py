from fastapi import APIRouter, Query
from typing import List, Dict, Any, Optional
from beans.store.duck import DuckStore

router = APIRouter(prefix="/timeline", tags=["Timeline Replay"])

@router.get("/sequence")
def get_timeline_sequence(
    entity: Optional[str] = Query(None),
    limit: int = Query(50, ge=10, le=200)
) -> List[Dict[str, Any]]:
    store = DuckStore()
    conn = store.get_connection()

    if entity:
        sql = """
        SELECT txid, timestamp, input_addresses, output_addresses, input_amounts, output_amounts,
               total_output, fee, src_ip, geo_country, asn, asn_type
        FROM transactions
        WHERE list_contains(input_addresses, ?) OR list_contains(output_addresses, ?)
        ORDER BY timestamp ASC LIMIT ?
        """
        df = conn.execute(sql, [entity, entity, limit]).fetchdf()
    else:
        sql = """
        SELECT txid, timestamp, input_addresses, output_addresses, input_amounts, output_amounts,
               total_output, fee, src_ip, geo_country, asn, asn_type
        FROM transactions
        ORDER BY timestamp ASC LIMIT ?
        """
        df = conn.execute(sql, [limit]).fetchdf()

    conn.close()

    events = []
    for idx, r in enumerate(df.to_dict(orient="records")):
        ins = list(r.get("input_addresses")) if r.get("input_addresses") is not None else []
        outs = list(r.get("output_addresses")) if r.get("output_addresses") is not None else []
        
        events.append({
            "step": idx + 1,
            "txid": r.get("txid"),
            "timestamp": str(r.get("timestamp")),
            "inputs_count": len(ins),
            "outputs_count": len(outs),
            "amount_btc": float(r.get("total_output", 0.0)),
            "fee_btc": float(r.get("fee", 0.0)),
            "src_ip": r.get("src_ip"),
            "geo_country": r.get("geo_country"),
            "asn": r.get("asn"),
            "asn_type": r.get("asn_type"),
            "is_peel": (len(ins) == 1 and len(outs) == 2),
            "is_split": (len(outs) >= 5)
        })

    return events
