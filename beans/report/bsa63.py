"""Section 63 BSA 2023 certificate (electronic record) for an alert or a case: a DRAFT for the officer and an expert to sign.

Section 63 of the Bharatiya Sakshya Adhiniyam, 2023 (formerly Section 65B of the Indian Evidence Act) makes a
computer output admissible only with a certificate in the form of the Schedule: Part A by the person in charge of the
device / records, Part B by an expert, each stating the hash value of the record. Whether a certificate is accepted is
for the court. This module:

- lists the electronic records the findings rest on (source files with their SHA-256, and each transaction record
  with its own SHA-256) and a single digest over all of them, then seals the annex (SHA-256 + RFC 3161 token);
- leaves everything BEANS cannot know (who the certifier is, lawful control of the device, regular use) as visible
  blanks for the signatories to affirm. BEANS asserts no fact about the officer or the device;
- is filed as a legal request (kind BSA63): PENDING_APPROVAL until a different supervisor approves (four-eyes), with the
  same audit trail as the Section 94 and freeze drafts.

Have counsel check the wording against the Schedule before first use. The verification code is the head of the annex
hash, for checking a printed copy against the stored record. It proves integrity, not admissibility.
"""
import html
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from beans.report.pdf_export import _canonical_hash
from beans.report.timestamp import stamp

BLANK = "[__________]"
KIND = "BSA63"
IO_FIELDS = ("certifier_name", "certifier_designation", "organisation", "device_description", "expert_name",
             "expert_designation", "fir_no", "fir_date", "police_station", "district_state")
RECORD_FIELDS = ("txid", "timestamp", "input_addresses", "input_amounts", "output_addresses", "output_amounts", "fee",
                 "src_ip")
MAX_RECORDS = 200

_CSS = """
@page { size: A4; margin: 18mm 16mm; @bottom-right { content: "Page " counter(page) " of " counter(pages); font-size: 8pt; color: #666; }
        @top-center { content: "DRAFT: not valid until signed by the certifier and the expert"; font-size: 8pt; color: #b91c1c; } }
body { font-family: 'DejaVu Sans', sans-serif; font-size: 10pt; color: #111; line-height: 1.5; max-width: 820px; margin: 0 auto; padding: 12px; }
h1 { font-size: 13pt; text-align: center; margin: 4px 0 2px; } .sub { text-align: center; font-size: 9pt; color: #444; }
h2 { font-size: 11pt; margin-top: 16px; border-bottom: 1px solid #ccc; } .mono { font-family: 'DejaVu Sans Mono', monospace; font-size: 8pt; word-break: break-all; }
table { border-collapse: collapse; width: 100%; margin: 6px 0; } td, th { border: 1px solid #ccc; padding: 3px 5px; text-align: left; font-size: 8.5pt; vertical-align: top; }
th { background: #f1f3f5; } .draft { border: 2px dashed #b91c1c; color: #b91c1c; padding: 6px 10px; font-weight: bold; font-size: 9pt; }
.seal { background: #f8fafc; border: 1px solid #cbd5e1; padding: 6px 10px; font-size: 8pt; margin-top: 14px; } .sig { margin-top: 30px; }
.code { font-family: 'DejaVu Sans Mono', monospace; font-size: 14pt; letter-spacing: 2px; text-align: center; border: 1px solid #94a3b8; padding: 6px; margin: 8px 0; }
"""


def _esc(v) -> str:
    return html.escape(str(v if v is not None and v != "" else BLANK))


def record_hash(rec: Dict[str, Any]) -> str:
    return _canonical_hash({k: rec.get(k) for k in RECORD_FIELDS})


def records_root(hashes: List[str]) -> str:
    """One digest over every record: SHA-256 of the sorted record hashes, joined with newlines."""
    return _canonical_hash(sorted(hashes))


def verification_code(digest: str) -> str:
    return "-".join(digest[i:i + 4] for i in range(0, 16, 4)).upper()


def build(subjects: List[Dict[str, Any]], records: List[Dict[str, Any]], sources: List[Dict[str, Any]],
          io: Optional[Dict[str, Any]] = None, case: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not subjects:
        raise LookupError("nothing to certify: the case has no alerts")
    io = {k: (io or {}).get(k) for k in IO_FIELDS}
    recs = [{**{k: r.get(k) for k in RECORD_FIELDS}, "record_sha256": record_hash(r)} for r in records[:MAX_RECORDS]]
    annex = {
        "kind": KIND, "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "scope": {"case": None if not case else {"id": case.get("id"), "name": case.get("case_name")},
                  "alerts": [s["alert_id"] for s in subjects]},
        "system": {"name": "BEANS", "operation": "offline analysis of ingested transaction and network metadata",
                   "hash_algorithm": "SHA-256"},
        "source_files": [{k: str(s.get(k)) if k == "ingested_at" else s.get(k) for k in ("file", "sha256", "records", "ingested_at")}
                         for s in sources],
        "records": recs, "records_root_sha256": records_root([r["record_sha256"] for r in recs]),
        "records_truncated": len(records) > MAX_RECORDS,
        "findings": [{"alert_id": s["alert_id"], "wallet": s["entity_id"], "typology": s.get("alert_type"),
                      "risk_score": s.get("risk_score"), "severity": s.get("severity"), "reasons": s.get("reasons") or [],
                      "directive": ((s.get("recommended_action") or {}).get("action")),
                      "key_transaction": (s.get("evidence") or {}).get("txid")} for s in subjects],
    }
    digest = _canonical_hash(annex)
    ts = stamp(digest)
    return {"kind": KIND, "alert_id": subjects[0]["alert_id"], "vasp": None, "evidence_sha256": digest, "timestamp": ts,
            "annex": annex, "html": _html(annex, io, digest, ts), "missing_fields": [k for k, v in io.items() if not v],
            "verification_code": verification_code(digest)}


def check(annex: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute every hash in a stored annex. Used to verify a printed or archived copy."""
    recs = annex.get("records") or []
    ok = [record_hash(r) == r.get("record_sha256") for r in recs]
    return {"annex_sha256": _canonical_hash(annex), "records": len(recs), "record_hashes_valid": all(ok),
            "records_root_valid": records_root([r.get("record_sha256") for r in recs]) == annex.get("records_root_sha256"),
            "bad_records": [r.get("txid") for r, v in zip(recs, ok) if not v]}


def _html(a: Dict[str, Any], io: Dict[str, Any], digest: str, ts: Dict[str, Any]) -> str:
    scope = a["scope"]
    ref = (f"Case #{_esc(scope['case']['id'])}: {_esc(scope['case']['name'])}" if scope["case"]
           else f"Alert {_esc(', '.join(scope['alerts']))}")
    fir = (f"FIR / Case No. {_esc(io['fir_no'])} dated {_esc(io['fir_date'])}, P.S. {_esc(io['police_station'])}, "
           f"{_esc(io['district_state'])}")
    src = "".join(f"<tr><td>{_esc(s['file'])}</td><td class=mono>{_esc(s['sha256'])}</td><td>{_esc(s['records'])}</td></tr>"
                  for s in a["source_files"]) or "<tr><td colspan=3><i>no source files recorded</i></td></tr>"
    recs = "".join(f"<tr><td>{i}</td><td class=mono>{_esc(r['txid'])}</td><td>{_esc(r['timestamp'])}</td>"
                   f"<td class=mono>{_esc(r['src_ip'])}</td><td class=mono>{_esc(r['record_sha256'])}</td></tr>"
                   for i, r in enumerate(a["records"], 1))
    finds = "".join(f"<li><span class=mono>{_esc(f['wallet'])}</span> · {_esc(f['typology'])} · risk {_esc(f['risk_score'])}/100"
                    f" ({_esc(f['severity'])})<ul>{''.join(f'<li>{_esc(r)}</li>' for r in f['reasons'])}</ul></li>"
                    for f in a["findings"])
    stamp_line = (f"RFC 3161: {_esc(ts.get('gen_time'))} · serial {_esc(ts.get('serial'))} · "
                  f"TSA CA {_esc(ts.get('tsa_ca_sha256_fingerprint'))}" if ts.get("status") == "stamped"
                  else f"RFC 3161: not available ({_esc(ts.get('reason'))})")
    trunc = ("<p><b>Note:</b> the record list is limited to the first %d transactions; the hash covers only those.</p>"
             % MAX_RECORDS if a["records_truncated"] else "")
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8><title>Section 63 BSA certificate {html.escape(ref)}</title><style>{_CSS}</style></head><body>
    <div class=draft>DRAFT generated by BEANS from the stored records. The certifier and the expert must check every statement, fill every {BLANK} field and sign. Counsel should check the form against the Schedule to Section 63.</div>
    <h1>CERTIFICATE UNDER SECTION 63(4)(c) OF THE BHARATIYA SAKSHYA ADHINIYAM, 2023</h1>
    <div class=sub>{fir}<br>{ref}</div>

    <h2>Part A: certificate by the person in charge of the device / records</h2>
    <p>I, {_esc(io['certifier_name'])}, {_esc(io['certifier_designation'])}, {_esc(io['organisation'])}, state that:</p>
    <ol>
      <li>The electronic records described below were produced by the BEANS analysis system, installed on: {_esc(io['device_description'])}.</li>
      <li>The records are derived from the source files listed in section 2, each identified by its SHA-256 hash value. The hash values were calculated by the system when the files were ingested and are repeated in this certificate.</li>
      <li>I affirm, from my own knowledge, the lawful control of the device and its regular use for the purpose of the activity in question during the material period: {BLANK} (BEANS cannot assert this).</li>
      <li>The information in the records was fed into the system in the ordinary course of that activity, and the output below is a faithful reproduction of what the system stored: {BLANK} (to be affirmed).</li>
    </ol>
    <div class=sig>(Signature) {BLANK}<br>{_esc(io['certifier_name'])}, {_esc(io['certifier_designation'])}<br>Date and place: {BLANK}</div>

    <h2>1. The electronic records certified</h2>
    <p>Findings produced by BEANS for {ref}. The listed findings are automated investigative leads; their reasons are quoted from the system.</p>
    <ul>{finds}</ul>
    <h2>2. Source files and their hash values (SHA-256)</h2>
    <table><tr><th>File</th><th>SHA-256</th><th>Records</th></tr>{src}</table>
    <h2>3. Transaction records relied on and their hash values (SHA-256)</h2>
    {trunc}<table><tr><th>#</th><th>Transaction ID</th><th>Observed (UTC)</th><th>First-seen IP</th><th>Record SHA-256</th></tr>{recs}</table>
    <p>Records digest (SHA-256 over the sorted record hashes): <span class=mono>{_esc(a['records_root_sha256'])}</span></p>

    <h2>Part B: certificate by the expert</h2>
    <p>I, {_esc(io['expert_name'])}, {_esc(io['expert_designation'])}, state that I examined the system output described in this certificate and the hash values stated above, and that I recomputed them as follows (the method is in section 4): {BLANK}.</p>
    <div class=sig>(Signature) {BLANK}<br>{_esc(io['expert_name'])}, {_esc(io['expert_designation'])}<br>Date and place: {BLANK}</div>

    <h2>4. Checking this certificate</h2>
    <div class=code>{verification_code(digest)}</div>
    <p>The code is the start of the annex hash below. To check a copy, recompute SHA-256 over the canonical JSON of the stored annex
    (<code>POST /api/bsa63/verify</code> does this and also re-checks every record hash). A matching code shows the annex is unchanged since it was sealed;
    it does not show that the certificate is admissible.</p>
    <div class=seal>Annex SHA-256: <span class=mono>{digest}</span><br>{stamp_line}<br>Generated {_esc(a['generated_at'])}.</div>
    </body></html>"""
