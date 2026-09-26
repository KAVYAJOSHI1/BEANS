"""Draft legal requests to exchanges (VASPs) from an alert's action directive.

Two kinds:
  section94   requisition to produce documents / records, Section 94 BNSS 2023 (formerly Section 91 CrPC)
  freeze      request to hold the credited funds, Section 106 BNSS 2023 (seizure; formerly Section 102 CrPC)

These are DRAFTS for the Investigating Officer (IO). BEANS fills in only what the blockchain evidence shows.
Everything it cannot know (FIR number, offences, IO details, the exchange's nodal-officer address) is left as
a visible blank "[__________]" for the IO to complete. A draft is not valid until the IO signs it. Every draft
carries the SHA-256 of its evidence annex and an RFC 3161 timestamp token over that hash.
"""
import html
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from beans.report.pdf_export import _canonical_hash
from beans.report.timestamp import stamp

BLANK = "[__________]"
KINDS = {"section94", "freeze"}
IO_FIELDS = ("io_name", "io_rank", "police_station", "district_state", "fir_no", "fir_date", "offences", "reply_days",
             "vasp_address_line")

_CSS = """
@page { size: A4; margin: 18mm 16mm; @bottom-right { content: "Page " counter(page) " of " counter(pages); font-size: 8pt; color: #666; }
        @top-center { content: "DRAFT: not valid until signed by the Investigating Officer"; font-size: 8pt; color: #b91c1c; } }
body { font-family: 'DejaVu Sans', sans-serif; font-size: 10pt; color: #111; line-height: 1.5; max-width: 820px; margin: 0 auto; padding: 12px; }
h1 { font-size: 13pt; text-align: center; margin: 4px 0 2px; } .sub { text-align: center; font-size: 9pt; color: #444; }
h2 { font-size: 11pt; margin-top: 16px; border-bottom: 1px solid #ccc; } .mono { font-family: 'DejaVu Sans Mono', monospace; font-size: 8pt; word-break: break-all; }
table { border-collapse: collapse; width: 100%; margin: 6px 0; } td, th { border: 1px solid #ccc; padding: 3px 5px; text-align: left; font-size: 8.5pt; vertical-align: top; }
th { background: #f1f3f5; } .draft { border: 2px dashed #b91c1c; color: #b91c1c; padding: 6px 10px; font-weight: bold; font-size: 9pt; }
.seal { background: #f8fafc; border: 1px solid #cbd5e1; padding: 6px 10px; font-size: 8pt; margin-top: 14px; } .sig { margin-top: 36px; }
"""


def _esc(v) -> str:
    return html.escape(str(v if v is not None and v != "" else BLANK))


def _deposits(alert: Dict[str, Any], vasp: Optional[str], kind: str) -> tuple:
    ra = alert.get("recommended_action") or {}
    hits = ra.get("vasp_exposure") or []
    if not vasp and kind == "section94":   # a Section 94 notice goes to an exchange that operates in India
        vasp = next((h["vasp"] for h in hits if h.get("in_jurisdiction")), None)
    vasp = vasp or ra.get("facts", {}).get("vasp") or (hits[0]["vasp"] if hits else None)
    return [h for h in hits if h["vasp"] == vasp], vasp


def build(kind: str, alert: Dict[str, Any], io: Optional[Dict[str, Any]] = None, vasp: Optional[str] = None) -> Dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    io = {k: (io or {}).get(k) for k in IO_FIELDS}
    deposits, vasp = _deposits(alert, vasp, kind)
    if not deposits:
        raise LookupError("no known exchange deposit is linked to this alert; nothing to request from an exchange")
    in_jur = bool(deposits[0].get("in_jurisdiction"))
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    first = min(h["deposit_ts"] for h in deposits)
    last = max(h["deposit_ts"] for h in deposits)
    annex = {
        "kind": kind, "generated_at": generated, "alert_id": alert["alert_id"], "flagged_wallet": alert["entity_id"],
        "risk_score": alert.get("risk_score"), "severity": alert.get("severity"), "alert_type": alert.get("alert_type"),
        "directive": {k: (alert.get("recommended_action") or {}).get(k) for k in ("action", "rule", "legal_basis")},
        "vasp": vasp, "vasp_country": deposits[0].get("country"), "vasp_in_jurisdiction": in_jur,
        "deposits": [{k: h.get(k) for k in ("deposit_address", "txid", "amount_btc", "deposit_ts", "hops",
                                            "minutes_after_receipt", "path")} for h in deposits],
        "period_utc": {"from": first, "to": last},
        "reasons": alert.get("reasons") or [],
    }
    digest = _canonical_hash(annex)
    ts = stamp(digest)
    doc = _html(kind, annex, io, digest, ts)
    return {"kind": kind, "alert_id": alert["alert_id"], "vasp": vasp, "evidence_sha256": digest, "timestamp": ts,
            "annex": annex, "html": doc, "missing_fields": [k for k, v in io.items() if not v]}


def _html(kind: str, a: Dict[str, Any], io: Dict[str, Any], digest: str, ts: Dict[str, Any]) -> str:
    dep_rows = "".join(
        f"<tr><td>{i}</td><td class=mono>{_esc(d['deposit_address'])}</td><td class=mono>{_esc(d['txid'])}</td>"
        f"<td>{d['amount_btc']:.8f}</td><td>{_esc(d['deposit_ts'])}</td><td>{_esc(d['hops'])}</td></tr>"
        for i, d in enumerate(a["deposits"], 1))
    addrs = "".join(f"<li class=mono>{_esc(d['deposit_address'])}</li>" for d in a["deposits"])
    ref = f"FIR / Case No. {_esc(io['fir_no'])} dated {_esc(io['fir_date'])}, P.S. {_esc(io['police_station'])}, {_esc(io['district_state'])}"
    to = (f"To,<br>The Principal Officer / Nodal Officer (Law Enforcement Requests)<br><b>{_esc(a['vasp'])}</b><br>"
          f"{_esc(io['vasp_address_line'])}")
    days = io["reply_days"] or "7"
    offshore = "" if a["vasp_in_jurisdiction"] else (
        "<p><b>Note:</b> the exchange appears to operate outside India. This letter can only be a voluntary request; "
        "the formal route is a Letter of Request under Section 112 BNSS 2023 / MLAT.</p>")
    if kind == "section94":
        title = "NOTICE UNDER SECTION 94 OF THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023"
        subject = f"Production of KYC and account records relating to cryptocurrency deposit address(es): {ref}"
        body = f"""
        <p>Whereas the investigation of the above case, registered for offences under {_esc(io['offences'])}, is in
        progress, and it has come to notice that proceeds connected with the case were deposited to the following
        address(es) controlled by your exchange:</p><ol>{addrs}</ol>
        <p>And whereas the production of the documents and records listed below is necessary for the purpose of the
        said investigation, you are hereby required under Section 94 of the Bharatiya Nagarik Suraksha Sanhita, 2023
        to produce them, in certified electronic form with a certificate under Section 63 of the Bharatiya Sakshya
        Adhiniyam, 2023, within <b>{html.escape(str(days))} days</b> of receipt of this notice:</p>
        <ol>
          <li>KYC documents of the account holder(s) to whom each address above is assigned (name, PAN, photograph,
              mobile number, e-mail, address proof) and the account creation date.</li>
          <li>Complete ledger of deposits, trades and withdrawals (crypto and INR) of those accounts from
              {_esc(a['period_utc']['from'][:10])} to date.</li>
          <li>Login, IP address and device logs with timestamps for the same period.</li>
          <li>Bank accounts, UPI IDs and payment gateways linked to or used by those accounts.</li>
          <li>Destination addresses and transaction IDs of all crypto withdrawals from those accounts.</li>
        </ol>
        <p>You are also requested not to alert the account holder(s) about this notice, as that may hamper the investigation.</p>"""
    else:
        title = "REQUEST TO FREEZE / HOLD CREDITED FUNDS (SECTION 106, BHARATIYA NAGARIK SURAKSHA SANHITA, 2023)"
        subject = f"Immediate hold on funds credited to cryptocurrency deposit address(es): {ref}"
        body = f"""
        <p>During investigation of the above case, registered for offences under {_esc(io['offences'])}, proceeds
        suspected to be connected with the offence were traced on the Bitcoin blockchain to the following deposit
        address(es) of your exchange. The first deposit reached your exchange
        <b>{_esc(a['deposits'][0].get('minutes_after_receipt'))} minutes</b> after the flagged wallet received the funds,
        so the funds are likely still held by you:</p><ol>{addrs}</ol>
        <p>In exercise of the powers under Section 106 of the Bharatiya Nagarik Suraksha Sanhita, 2023, you are
        requested to <b>immediately freeze / place on hold</b> all balances (crypto and INR) of the account(s) to which
        these addresses are assigned, to block withdrawals, and to confirm the action and the balances held to the
        undersigned. A requisition for KYC and account records under Section 94 BNSS follows separately.</p>"""
    stamp_line = (f"RFC 3161 timestamp: {_esc(ts.get('gen_time'))} · serial {_esc(ts.get('serial'))} · "
                  f"TSA CA fingerprint {_esc(ts.get('tsa_ca_sha256_fingerprint'))}" if ts.get("status") == "stamped"
                  else f"RFC 3161 timestamp: not available ({_esc(ts.get('reason'))})")
    return f"""<!doctype html><html><head><meta charset=utf-8><title>{html.escape(title.title())}</title><style>{_CSS}</style></head><body>
    <div class=draft>DRAFT generated by BEANS from blockchain evidence. The Investigating Officer must check the facts,
    fill every {BLANK} field and sign before issue.</div>
    <h1>{title}</h1><div class=sub>{ref}</div>
    <p style="margin-top:14px">{to}</p>
    <p><b>Subject:</b> {subject}</p>
    {offshore}{body}
    <div class=sig>(Signature)<br>{_esc(io['io_name'])}<br>{_esc(io['io_rank'])}, Investigating Officer<br>
    P.S. {_esc(io['police_station'])}, {_esc(io['district_state'])}<br>Date: {BLANK}</div>
    <h2>Annex A: blockchain evidence</h2>
    <p>Flagged wallet <span class=mono>{_esc(a['flagged_wallet'])}</span> · alert {_esc(a['alert_id'])} ·
    {_esc(a['alert_type'])} · risk {_esc(a['risk_score'])}/100 ({_esc(a['severity'])})</p>
    <table><tr><th>#</th><th>Deposit address</th><th>Transaction ID</th><th>BTC</th><th>Time (UTC)</th><th>Hops</th></tr>{dep_rows}</table>
    <p><b>Directive rule:</b> {_esc(a['directive'].get('rule'))}</p>
    <p><b>Why the wallet was flagged:</b></p><ul>{''.join(f'<li>{_esc(r)}</li>' for r in a['reasons'])}</ul>
    <div class=seal>Annex SHA-256: <span class=mono>{digest}</span><br>{stamp_line}<br>
    Generated {_esc(a['generated_at'])}, offline. Recompute the hash of the annex JSON to verify integrity.</div>
    </body></html>"""
