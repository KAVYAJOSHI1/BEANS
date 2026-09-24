from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from beans.store.duck import DuckStore

router = APIRouter(prefix="/entity", tags=["Entity 360"])

@router.get("/wallet/{address}")
def get_wallet_360(address: str) -> Dict[str, Any]:
    store = DuckStore()
    conn = store.get_connection()

    profile_df = conn.execute("SELECT * FROM wallet_profiles WHERE address = ?", [address]).fetchdf()
    if profile_df.empty:
        # Create on the fly from txs
        profile = {
            "address": address,
            "risk_score": 20.0,
            "threat_classification": "UNKNOWN",
            "cluster_id": "SOLO",
            "associated_ips": []
        }
    else:
        profile = profile_df.to_dict(orient="records")[0]

    # Related transactions
    tx_df = conn.execute("""
    SELECT txid, timestamp, input_addresses, output_addresses, total_output, fee, src_ip, geo_country, asn
    FROM transactions
    WHERE list_contains(input_addresses, ?) OR list_contains(output_addresses, ?)
    ORDER BY timestamp ASC
    """, [address, address]).fetchdf()

    transactions = []
    for t in tx_df.to_dict(orient="records"):
        in_addrs = list(t.get("input_addresses")) if t.get("input_addresses") is not None else []
        role = "SENDER" if address in in_addrs else "RECIPIENT"
        transactions.append({
            "txid": t.get("txid"),
            "timestamp": str(t.get("timestamp")),
            "role": role,
            "amount": float(t.get("total_output", 0.0)),
            "fee": float(t.get("fee", 0.0)),
            "src_ip": t.get("src_ip"),
            "geo_country": t.get("geo_country"),
            "asn": t.get("asn")
        })

    # Related alert
    alert_df = conn.execute("SELECT * FROM alerts WHERE entity_id = ?", [address]).fetchdf()
    alert_data = alert_df.to_dict(orient="records")[0] if not alert_df.empty else None

    conn.close()

    return {
        "profile": profile,
        "transactions": transactions,
        "alert": alert_data
    }
