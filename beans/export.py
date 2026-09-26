"""Exports for other tools (roadmap C5).

  neo4j(out_dir) → nodes/edges CSVs for `neo4j-admin database import full`
                   (Wallet, Transaction, IP nodes; SPENDS / PAYS / RELAYED edges, risk + cluster on wallets)
  stix(path)     → STIX 2.1 bundle: one indicator per alerted wallet and per first-relaying IP, with the alert's
                   risk/confidence and reasons, grouped in a report. Wallet addresses use the custom SCO type
                   `x-cryptocurrency-wallet` because STIX 2.1 has no built-in cryptocurrency object.
"""
import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from beans.store.duck import DuckStore

NS = uuid.UUID("6f1c3a3e-2b9d-4d0e-9a7c-3f5e2b1d8c4a")   # deterministic STIX ids for the same indicator


def neo4j(out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = DuckStore().get_connection()
    q = lambda sql: conn.execute(sql).fetchall()
    counts = {}

    def write(name, header, rows):
        with open(out_dir / name, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
        counts[name] = len(rows)

    write("wallets.csv", ["address:ID(Wallet)", "risk:float", "typology", "cluster_id", ":LABEL"],
          [(a, r or 0, t or "", c or "", "Wallet") for a, r, t, c in
           q("SELECT address, risk_score, threat_classification, cluster_id FROM wallet_profiles")])
    write("transactions.csv", ["txid:ID(Transaction)", "timestamp", "total_out:float", "fee:float", ":LABEL"],
          [(t, str(ts), v, f, "Transaction") for t, ts, v, f in q("SELECT txid, timestamp, total_output, fee FROM transactions")])
    write("ips.csv", ["ip:ID(IP)", "country", "asn", "asn_type", ":LABEL"],
          [(*r, "IP") for r in q("SELECT src_ip, any_value(geo_country), any_value(asn), any_value(asn_type) "
                                 "FROM net_observations GROUP BY 1")])
    write("spends.csv", [":START_ID(Wallet)", ":END_ID(Transaction)", "amount:float", ":TYPE"],
          [(a, t, v, "SPENDS") for t, a, v in q("SELECT txid, unnest(input_addresses), unnest(input_amounts) FROM transactions")])
    write("pays.csv", [":START_ID(Transaction)", ":END_ID(Wallet)", "amount:float", ":TYPE"],
          [(t, a, v, "PAYS") for t, a, v in q("SELECT txid, unnest(output_addresses), unnest(output_amounts) FROM transactions")])
    write("relayed.csv", [":START_ID(IP)", ":END_ID(Transaction)", "first_seen:boolean", ":TYPE"],
          [(ip, t, str(bool(first)).lower(), "RELAYED") for ip, t, first in q("""
              SELECT o.src_ip, o.txid, o.src_ip = t.src_ip FROM net_observations o JOIN transactions t USING (txid)
              GROUP BY ALL""")])
    conn.close()
    (out_dir / "IMPORT.md").write_text(
        "neo4j-admin database import full beans --nodes=wallets.csv --nodes=transactions.csv --nodes=ips.csv "
        "--relationships=spends.csv --relationships=pays.csv --relationships=relayed.csv\n")
    return counts


def stix(path: Path, min_risk: float = 65) -> dict:
    conn = DuckStore().get_connection()
    rows = conn.execute("SELECT alert_id, entity_id, alert_type, risk_score, calibrated_confidence, severity, reasons, "
                        "evidence, recommended_action FROM alerts WHERE risk_score >= ? ORDER BY risk_score DESC",
                        [min_risk]).fetchall()
    conn.close()
    keys = ("alert_id", "entity_id", "alert_type", "risk_score", "calibrated_confidence", "severity", "reasons",
            "evidence", "recommended_action")
    bundle = stix_bundle([dict(zip(keys, r)) for r in rows])
    Path(path).write_text(json.dumps(bundle, indent=2))
    n_ip = sum(1 for o in bundle["objects"] if o["type"] == "indicator" and "addr:value" in o["pattern"])
    return {"indicators": len(bundle["objects"]) - 2, "wallets": len(rows), "ips": n_ip}


def stix_bundle(alerts: list) -> dict:
    """STIX 2.1 bundle: one indicator per alerted wallet (+ one per first-relay IP) and a report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    identity = {"type": "identity", "spec_version": "2.1", "id": f"identity--{uuid.uuid5(NS, 'beans')}",
                "created": now, "modified": now, "name": "BEANS (offline Bitcoin forensics)", "identity_class": "system"}
    objs, ips = [identity], set()
    for a in alerts:
        ev = a.get("evidence") or {}
        ev = json.loads(ev) if isinstance(ev, str) else ev
        ra = a.get("recommended_action") or {}
        ra = json.loads(ra) if isinstance(ra, str) else ra
        wallet, atype, sev = a["entity_id"], a["alert_type"], a["severity"]
        objs.append({
            "type": "indicator", "spec_version": "2.1", "id": f"indicator--{uuid.uuid5(NS, wallet)}",
            "created": now, "modified": now, "created_by_ref": identity["id"],
            "name": f"{atype.replace('_PATTERN', '')} wallet {wallet[:16]}…",
            "description": " · ".join(a.get("reasons") or []), "indicator_types": ["malicious-activity"],
            "pattern": f"[x-cryptocurrency-wallet:address = '{wallet}']", "pattern_type": "stix", "valid_from": now,
            "confidence": int(round(float(a["calibrated_confidence"]) * 100)), "labels": [sev.lower(), atype.lower()],
            "x_beans_risk": a["risk_score"], "x_beans_alert_id": a["alert_id"],
            "x_beans_recommended_action": ra.get("action"),
        })
        if ev.get("first_spy_ip") and ev["first_spy_ip"] not in ips:
            ips.add(ev["first_spy_ip"])
            ip = ev["first_spy_ip"]
            objs.append({
                "type": "indicator", "spec_version": "2.1", "id": f"indicator--{uuid.uuid5(NS, ip)}",
                "created": now, "modified": now, "created_by_ref": identity["id"],
                "name": f"First relay of flagged transaction ({ev.get('first_spy_asn_type', 'unknown')})",
                "indicator_types": ["anomalous-activity"],
                "pattern": f"[{'ipv6-addr' if ':' in ip else 'ipv4-addr'}:value = '{ip}']", "pattern_type": "stix",
                "valid_from": now, "confidence": int(round(100 * float(ev.get("first_spy_confidence") or 0.3))),
            })
    objs.append({"type": "report", "spec_version": "2.1", "id": f"report--{uuid.uuid4()}", "created": now,
                 "modified": now, "created_by_ref": identity["id"], "name": "BEANS alert export", "published": now,
                 "report_types": ["threat-report"], "object_refs": [o["id"] for o in objs[1:]]})
    return {"type": "bundle", "id": f"bundle--{uuid.uuid4()}", "objects": objs}
