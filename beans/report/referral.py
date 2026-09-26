"""FIU-IND intelligence referral pack for one alert.

Reporting entities (banks, registered exchanges) file STRs with FIU-IND through FINnet; an agency does not.
This pack is what the agency hands to the IO / its FIU-IND liaison officer: the wallet, why it was flagged,
the money trail, the network evidence and the exchanges it touched, all in one sealed file (SHA-256 + RFC 3161).
"""
import html
from datetime import datetime, timezone
from typing import Any, Dict, List

from beans.report.pdf_export import _canonical_hash
from beans.report.timestamp import stamp

CLASSIFICATION = "RESTRICTED: for official use by law enforcement / FIU-IND only"


def build(alert: Dict[str, Any], wallet: Dict[str, Any], ips: List[Dict[str, Any]], sources: List[Dict[str, Any]]) -> Dict[str, Any]:
    ra = alert.get("recommended_action") or {}
    ev = alert.get("evidence") or {}
    dossier = {
        "classification": CLASSIFICATION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "subject": {"wallet": alert["entity_id"], "cluster_id": ev.get("cluster_id"), "cluster_size": ev.get("cluster_size"),
                    "total_received_btc": wallet.get("total_received"), "total_sent_btc": wallet.get("total_sent"),
                    "balance_btc": wallet.get("balance"), "transaction_count": wallet.get("transaction_count")},
        "assessment": {"alert_id": alert["alert_id"], "typology": (alert.get("alert_type") or "").replace("_PATTERN", ""),
                       "risk_score": alert.get("risk_score"), "calibrated_confidence": alert.get("calibrated_confidence"),
                       "severity": alert.get("severity"), "reasons": alert.get("reasons") or [],
                       "shap_top_features": alert.get("shap_top_features") or [], "engine_scores": alert.get("engine_scores") or {}},
        "directive": {k: ra.get(k) for k in ("action", "title", "rule", "legal_basis", "facts", "also_matched")},
        "money_trail": {"key_transaction": ev.get("txid"), "top_transactions": ev.get("top_txids") or [],
                        "path_to_seed": ev.get("path_to_seed") or [], "peel_chain": ev.get("peel_chain") or []},
        "exchange_exposure": ra.get("vasp_exposure") or [],
        "network_evidence": {"first_relay_ip": ev.get("first_spy_ip"), "first_relay_confidence": ev.get("first_spy_confidence"),
                             "first_relay_asn_type": ev.get("first_spy_asn_type"), "relaying_ips": ips},
        "source_files": sources,
        "caveats": ["Automated findings are investigative leads and need analyst confirmation.",
                    "First-relay IP is the first peer seen broadcasting; it may be a relay, VPN or Tor exit, not the owner.",
                    "Exchange attribution comes from the loaded attribution list and is only as good as that list."],
    }
    digest = _canonical_hash(dossier)
    ts = stamp(digest)
    return {"alert_id": alert["alert_id"], "evidence_sha256": digest, "timestamp": ts, "dossier": dossier,
            "html": _html(dossier, digest, ts)}


def _html(d: Dict[str, Any], digest: str, ts: Dict[str, Any]) -> str:
    e = lambda v: html.escape(str(v if v is not None else "n/a"))  # noqa: E731
    s, a, dr, m, n = d["subject"], d["assessment"], d["directive"], d["money_trail"], d["network_evidence"]
    kv = lambda rows: "<table>" + "".join(f"<tr><th>{e(k)}</th><td>{v}</td></tr>" for k, v in rows) + "</table>"  # noqa: E731
    exp = "".join(f"<tr><td>{e(h['vasp'])}</td><td>{e(h.get('country'))}</td><td class=mono>{e(h['deposit_address'])}</td>"
                  f"<td>{e(h['amount_btc'])}</td><td>{e(h['deposit_ts'])}</td><td>{e(h['hops'])}</td></tr>" for h in d["exchange_exposure"])
    ips = "".join(f"<tr><td class=mono>{e(i.get('ip'))}</td><td>{e(i.get('country'))}</td><td>{e(i.get('asn'))}</td>"
                  f"<td>{e(i.get('asn_type'))}</td><td>{e(i.get('n'))}</td></tr>" for i in n["relaying_ips"])
    stamp_line = (f"RFC 3161 timestamp {e(ts.get('gen_time'))} · serial {e(ts.get('serial'))}" if ts.get("status") == "stamped"
                  else f"RFC 3161 timestamp unavailable ({e(ts.get('reason'))})")
    return f"""<!doctype html><html><head><meta charset=utf-8><title>FIU Referral {e(a['alert_id'])}</title><style>
    @page {{ size: A4; margin: 16mm 14mm; @top-center {{ content: "{CLASSIFICATION}"; font-size: 8pt; color: #b91c1c; }}
             @bottom-right {{ content: "Page " counter(page) " of " counter(pages); font-size: 8pt; color: #666; }} }}
    body {{ font-family: 'DejaVu Sans', sans-serif; font-size: 9.5pt; line-height: 1.45; color: #111; max-width: 860px; margin: 0 auto; padding: 12px; }}
    h1 {{ font-size: 15pt; margin: 0; }} h2 {{ font-size: 11pt; border-bottom: 1px solid #ccc; margin-top: 16px; }}
    .cls {{ color: #b91c1c; font-weight: bold; font-size: 8.5pt; }} .mono {{ font-family: 'DejaVu Sans Mono', monospace; font-size: 8pt; word-break: break-all; }}
    table {{ border-collapse: collapse; width: 100%; margin: 4px 0; }} td, th {{ border: 1px solid #ddd; padding: 3px 5px; text-align: left; font-size: 8.5pt; vertical-align: top; }}
    th {{ background: #f1f3f5; width: 26%; }} .seal {{ background: #f8fafc; border: 1px solid #cbd5e1; padding: 6px 10px; font-size: 8pt; margin-top: 14px; }}
    </style></head><body>
    <div class=cls>{CLASSIFICATION}</div>
    <h1>Intelligence Referral Pack: {e(a['typology'])}</h1>
    <p>Alert {e(a['alert_id'])} · generated {e(d['generated_at'])} · for the IO / FIU-IND liaison officer</p>
    <h2>1. Subject</h2>{kv([("Wallet", f"<span class=mono>{e(s['wallet'])}</span>"), ("Cluster", f"{e(s['cluster_id'])} ({e(s['cluster_size'])} wallets)"),
        ("Received / sent (BTC)", f"{e(s['total_received_btc'])} / {e(s['total_sent_btc'])}"), ("Balance (BTC)", e(s['balance_btc'])),
        ("Transactions", e(s['transaction_count']))])}
    <h2>2. Assessment</h2>{kv([("Risk / severity", f"{e(a['risk_score'])}/100 · {e(a['severity'])}"),
        ("Confidence", e(a['calibrated_confidence'])), ("Why flagged", "<ul>" + "".join(f"<li>{e(r)}</li>" for r in a['reasons']) + "</ul>")])}
    <h2>3. Recommended action</h2>{kv([("Directive", e(dr.get('title'))), ("Rule", e(dr.get('rule'))), ("Legal basis", e(dr.get('legal_basis'))),
        ("Also matched", e(', '.join(dr.get('also_matched') or []) or 'none'))])}
    <h2>4. Money trail</h2>{kv([("Key transaction", f"<span class=mono>{e(m['key_transaction'])}</span>"),
        ("Path to known-bad seed", f"<span class=mono>{e(' → '.join(m['path_to_seed']) or 'none found')}</span>"),
        ("Peel chain", f"{len(m['peel_chain'])} transactions")])}
    <h2>5. Exchange exposure</h2><table><tr><th>Exchange</th><th>Country</th><th>Deposit address</th><th>BTC</th><th>Time (UTC)</th><th>Hops</th></tr>
    {exp or '<tr><td colspan=6><i>No known exchange deposit within 4 hops</i></td></tr>'}</table>
    <h2>6. Network evidence</h2>{kv([("First relay IP", f"<span class=mono>{e(n['first_relay_ip'])}</span> ({e(n['first_relay_asn_type'])}, confidence {e(n['first_relay_confidence'])})")])}
    <table><tr><th>IP</th><th>Country</th><th>ASN</th><th>Type</th><th>Broadcasts</th></tr>{ips or '<tr><td colspan=5><i>none</i></td></tr>'}</table>
    <h2>7. Caveats</h2><ul>{''.join(f'<li>{e(c)}</li>' for c in d['caveats'])}</ul>
    <div class=seal>Dossier SHA-256 <span class=mono>{digest}</span><br>{stamp_line}</div>
    </body></html>"""
