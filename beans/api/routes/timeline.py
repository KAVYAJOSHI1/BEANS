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


@router.get("/trace")
def trace_endpoint(
    entity: Optional[str] = Query(None, description="wallet to start from; default = highest-risk alert"),
    max_hops: int = Query(60, ge=1, le=500),
) -> Dict[str, Any]:
    return follow_the_money(entity, max_hops)


def follow_the_money(entity: Optional[str] = None, max_hops: int = 60) -> Dict[str, Any]:
    """Peel-chain replay: from `entity`, follow each spend's change (largest output) hop by hop.

    Every hop lists what was peeled off and where it went (known exchanges flagged from the attribution list).
    Stops when the money is split (≥ 5 outputs), cashed out in one piece to a known exchange, left unspent, or loops.
    """
    if not entity:
        top = db.one("SELECT entity_id FROM alerts WHERE entity_type = 'WALLET' ORDER BY risk_score DESC LIMIT 1")
        entity = top["entity_id"] if top else None
    if not entity:
        return {"start": None, "hops": [], "stop_reason": "no data"}
    known = {r["address"]: r for r in db.query("SELECT address, entity_name, entity_type, in_jurisdiction FROM known_entities")}
    cols = ("txid, timestamp, input_addresses, input_amounts, output_addresses, output_amounts, fee, src_ip, geo_country, "
            "asn_type")
    hops, seen, current, after, prev_ts = [], set(), entity, None, None
    stop = "max hops reached"
    peeled_total = 0.0
    for _ in range(max_hops):
        params = [current] + ([after] if after else [])
        tx = db.one(f"SELECT {cols} FROM transactions WHERE list_contains(input_addresses, ?)"
                    f"{' AND timestamp >= ?' if after else ''} ORDER BY timestamp LIMIT 1", params)
        if not tx:
            stop = "funds left unspent" if hops else "wallet never spends"
            break
        if tx["txid"] in seen:
            stop = "loop"
            break
        seen.add(tx["txid"])
        outs = sorted(zip(tx["output_addresses"] or [], tx["output_amounts"] or []), key=lambda x: -x[1])
        amount_in = sum(a for w, a in zip(tx["input_addresses"] or [], tx["input_amounts"] or []) if w == current)
        change, peels = (outs[0], outs[1:]) if outs else ((None, 0.0), [])
        peel_rows = [{"address": a, "amount": v, "exchange": known.get(a, {}).get("entity_name"),
                      "in_jurisdiction": known.get(a, {}).get("in_jurisdiction")} for a, v in peels[:10]]
        peeled_total += sum(v for _, v in peels)
        ts = tx["timestamp"]
        hop = {"hop": len(hops) + 1, "txid": tx["txid"], "timestamp": ts, "from": current,
               "amount_in": round(amount_in, 8), "fee": tx["fee"] or 0.0, "outputs": len(outs),
               "change_address": change[0], "change_amount": round(change[1], 8),
               "peels": peel_rows, "peeled_total": round(peeled_total, 8),
               "change_exchange": known.get(change[0], {}).get("entity_name"),
               "minutes_since_previous": None if prev_ts is None else round(
                   (_ts(ts) - _ts(prev_ts)).total_seconds() / 60, 1),
               "src_ip": tx["src_ip"], "geo_country": tx["geo_country"], "asn_type": tx["asn_type"]}
        hops.append(hop)
        if len(outs) >= 5:
            stop = f"split into {len(outs)} outputs"
            break
        if hop["change_exchange"]:
            stop = f"cashed out to {hop['change_exchange']}"
            break
        current, after, prev_ts = change[0], ts, ts
    first, last = (hops[0]["timestamp"], hops[-1]["timestamp"]) if hops else (None, None)
    return {"start": entity, "hops": hops, "stop_reason": stop,
            "summary": {"hops": len(hops), "start_amount": hops[0]["amount_in"] if hops else 0.0,
                        "end_amount": hops[-1]["change_amount"] if hops else 0.0,
                        "peeled_total": round(peeled_total, 8),
                        "exchanges_reached": sorted({p["exchange"] for h in hops for p in h["peels"] if p["exchange"]}
                                                    | ({hops[-1]["change_exchange"]} if hops and hops[-1]["change_exchange"] else set())),
                        "duration_h": round((_ts(last) - _ts(first)).total_seconds() / 3600, 2) if hops else 0.0}}


def _ts(v):
    from datetime import datetime
    return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))
