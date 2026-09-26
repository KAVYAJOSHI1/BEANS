from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from beans.api import db
from beans.api.routes.alerts import alert_out

router = APIRouter(prefix="/entity", tags=["Entity 360"])

TX_COLS = ("txid, timestamp, input_addresses, input_amounts, output_addresses, output_amounts, "
           "total_output, fee, src_ip, geo_country, geo_city, asn, asn_name, asn_type, tx_version, locktime, rbf")


def _describe_fingerprint(version, locktime, rbf) -> str:
    lock = "no locktime" if not locktime else ("anti-fee-sniping locktime" if locktime < 500_000_000 else "time locktime")
    return f"version {version} · {lock} · {'RBF on' if rbf else 'RBF off'}"


def _latest_alert(entity_id: str):
    row = db.one("SELECT * FROM alerts WHERE entity_id = ? ORDER BY risk_score DESC LIMIT 1", [entity_id])
    return alert_out(row) if row else None


@router.get("/wallet/{address}")
def get_wallet_360(address: str) -> Dict[str, Any]:
    txs = db.query(
        f"SELECT {TX_COLS} FROM transactions "
        "WHERE list_contains(input_addresses, ?) OR list_contains(output_addresses, ?) ORDER BY timestamp",
        [address, address],
    )
    stored = db.one("SELECT * FROM wallet_profiles WHERE address = ?", [address])
    if not txs and not stored:
        raise HTTPException(404, f"wallet {address} not found")

    transactions, received, sent, ips = [], 0.0, 0.0, {}
    for t in txs:
        ins, outs = t["input_addresses"] or [], t["output_addresses"] or []
        got = sum(a for w, a in zip(outs, t["output_amounts"] or []) if w == address)
        spent = sum(a for w, a in zip(ins, t["input_amounts"] or []) if w == address)
        received += got
        sent += spent
        role = "SENDER" if spent else "RECIPIENT"
        if spent and t["src_ip"]:  # IPs that broadcast this wallet's spends
            ips.setdefault(t["src_ip"], {"ip": t["src_ip"], "country": t["geo_country"], "asn": t["asn"],
                                         "asn_type": t["asn_type"], "tx_count": 0})["tx_count"] += 1
        transactions.append({
            "txid": t["txid"], "timestamp": t["timestamp"], "role": role,
            "amount": round(spent if spent else got, 8), "fee": t["fee"] or 0.0,
            "n_inputs": len(ins), "n_outputs": len(outs),
            "src_ip": t["src_ip"], "geo_country": t["geo_country"], "asn": t["asn"], "asn_type": t["asn_type"],
        })

    stored = stored or {}
    cluster_id = stored.get("cluster_id") or "SOLO"
    cluster_members = []
    if cluster_id not in ("SOLO", None):
        cluster_members = [r["address"] for r in db.query(
            "SELECT address FROM wallet_profiles WHERE cluster_id = ? AND address != ? LIMIT 50", [cluster_id, address])]

    fps = {}
    for t in txs:
        if address in (t["input_addresses"] or []) and t.get("tx_version") is not None and t.get("rbf") is not None:
            key = _describe_fingerprint(t["tx_version"], t.get("locktime") or 0, t["rbf"])
            fps[key] = fps.get(key, 0) + 1
    profile = {
        "address": address,
        "software_fingerprints": [{"fingerprint": k, "spends": v} for k, v in sorted(fps.items(), key=lambda kv: -kv[1])],
        "first_seen": txs[0]["timestamp"] if txs else stored.get("first_seen"),
        "last_seen": txs[-1]["timestamp"] if txs else stored.get("last_seen"),
        "transaction_count": len(txs),
        "total_received": round(received, 8),
        "total_sent": round(sent, 8),
        "balance": round(received - sent, 8),
        "risk_score": float(stored.get("risk_score") or 0.0),
        "threat_classification": stored.get("threat_classification") or "UNSCORED",
        "cluster_id": cluster_id,
        "cluster_size": len(cluster_members) + 1,
        "is_seed": bool(db.scalar("SELECT COUNT(*) FROM seeds WHERE address = ?", [address])),
        "associated_ips": list(ips.values()),
    }
    return {"profile": profile, "transactions": transactions, "cluster_members": cluster_members,
            "alert": _latest_alert(address)}


@router.get("/ip/{ip}")
def get_ip_360(ip: str) -> Dict[str, Any]:
    obs = db.one(
        "SELECT src_ip AS ip, any_value(geo_country) AS country, any_value(geo_city) AS city, any_value(asn) AS asn, "
        "any_value(asn_name) AS asn_name, any_value(asn_type) AS asn_type, COUNT(*) AS observations, "
        "COUNT(DISTINCT txid) AS tx_count, MIN(timestamp) AS first_seen, MAX(timestamp) AS last_seen "
        "FROM net_observations WHERE src_ip = ? GROUP BY src_ip", [ip])
    if not obs:
        raise HTTPException(404, f"ip {ip} not found")
    txs = db.query(f"SELECT {TX_COLS} FROM transactions WHERE src_ip = ? ORDER BY timestamp LIMIT 200", [ip])
    wallets = sorted({w for t in txs for w in (t["input_addresses"] or [])})
    flagged = db.query(
        "SELECT entity_id, risk_score, severity, alert_type FROM alerts WHERE list_contains(?, entity_id) "
        "ORDER BY risk_score DESC", [wallets]) if wallets else []
    return {"profile": obs, "transactions": txs, "linked_wallets": wallets[:200], "flagged_wallets": flagged,
            "alert": _latest_alert(ip)}


@router.get("/tx/{txid}")
def get_tx_360(txid: str) -> Dict[str, Any]:
    tx = db.one("SELECT * FROM transactions WHERE txid = ?", [txid])
    if not tx:
        raise HTTPException(404, f"transaction {txid} not found")
    relays = db.query(
        "SELECT timestamp, src_ip, src_port, dst_ip, dst_port, geo_country, asn, asn_type "
        "FROM net_observations WHERE txid = ? ORDER BY timestamp", [txid])
    return {"transaction": tx, "relays": relays, "alert": _latest_alert(txid)}
