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
body { font-family: 'DejaVu Sans', 'Noto Sans Devanagari', 'Lohit Devanagari', sans-serif; font-size: 10pt; color: #111; line-height: 1.5; max-width: 820px; margin: 0 auto; padding: 12px; }
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


def build(kind: str, alert: Dict[str, Any], io: Optional[Dict[str, Any]] = None, vasp: Optional[str] = None,
          lang: str = "en") -> Dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    if lang not in LANGS:
        raise ValueError(f"lang must be one of {sorted(LANGS)}")
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
        "lang": lang,
        "freeze_trigger": {k: ((alert.get("recommended_action") or {}).get("facts") or {}).get(k)
                           for k in ("minutes_after_receipt", "minutes_before_latest_data")}
        if (alert.get("recommended_action") or {}).get("action") == "IMMEDIATE_FREEZE_DRAFT" else {},
    }
    digest = _canonical_hash(annex)
    ts = stamp(digest)
    doc = _html(kind, annex, io, digest, ts, lang)
    return {"kind": kind, "alert_id": alert["alert_id"], "vasp": vasp, "evidence_sha256": digest, "timestamp": ts,
            "annex": annex, "html": doc, "missing_fields": [k for k, v in io.items() if not v]}


LANGS = {"en", "hi"}

# Every sentence of the drafts, per language. Hindi: drafted for BEANS; a native legal reviewer must check it
# before real use (the Hindi document says so on its face).
TEXT = {
    "en": {
        "draft": "DRAFT generated by BEANS from blockchain evidence. The Investigating Officer must check the facts, "
                 "fill every {blank} field and sign before issue.",
        "ref": "FIR / Case No. {fir} dated {date}, P.S. {ps}, {district}",
        "to": "To,<br>The Principal Officer / Nodal Officer (Law Enforcement Requests)<br><b>{vasp}</b><br>{addr}",
        "subject_label": "Subject:",
        "offshore": "<b>Note:</b> the exchange appears to operate outside India. This letter can only be a voluntary request; "
                    "the formal route is a Letter of Request under Section 112 BNSS 2023 / MLAT.",
        "s94_title": "NOTICE UNDER SECTION 94 OF THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023",
        "s94_subject": "Production of KYC and account records relating to cryptocurrency deposit address(es): {ref}",
        "s94_p1": "Whereas the investigation of the above case, registered for offences under {offences}, is in progress, "
                  "and it has come to notice that proceeds connected with the case were deposited to the following "
                  "address(es) controlled by your exchange:",
        "s94_p2": "And whereas the production of the documents and records listed below is necessary for the purpose of the "
                  "said investigation, you are hereby required under Section 94 of the Bharatiya Nagarik Suraksha Sanhita, "
                  "2023 to produce them, in certified electronic form with a certificate under Section 63 of the Bharatiya "
                  "Sakshya Adhiniyam, 2023, within <b>{days} days</b> of receipt of this notice:",
        "s94_items": ["KYC documents of the account holder(s) to whom each address above is assigned (name, PAN, photograph, "
                      "mobile number, e-mail, address proof) and the account creation date.",
                      "Complete ledger of deposits, trades and withdrawals (crypto and INR) of those accounts from {since} to date.",
                      "Login, IP address and device logs with timestamps for the same period.",
                      "Bank accounts, UPI IDs and payment gateways linked to or used by those accounts.",
                      "Destination addresses and transaction IDs of all crypto withdrawals from those accounts."],
        "s94_close": "You are also requested not to alert the account holder(s) about this notice, as that may hamper the investigation.",
        "fr_title": "REQUEST TO FREEZE / HOLD CREDITED FUNDS (SECTION 106, BHARATIYA NAGARIK SURAKSHA SANHITA, 2023)",
        "fr_subject": "Immediate hold on funds credited to cryptocurrency deposit address(es): {ref}",
        "fr_p1": "During investigation of the above case, registered for offences under {offences}, proceeds suspected to be "
                 "connected with the offence were traced on the Bitcoin blockchain to the following deposit address(es) of "
                 "your exchange. {timing} so the funds are likely still held by you:",
        "fr_quick": "The first deposit reached your exchange <b>{m} minutes</b> after the flagged wallet received the funds,",
        "fr_fresh": "The deposit reached your exchange <b>{m} minutes</b> before the latest transaction data we hold,",
        "fr_other": "The deposits are listed in Annex A,",
        "fr_p2": "In exercise of the powers under Section 106 of the Bharatiya Nagarik Suraksha Sanhita, 2023, you are requested "
                 "to <b>immediately freeze / place on hold</b> all balances (crypto and INR) of the account(s) to which these "
                 "addresses are assigned, to block withdrawals, and to confirm the action and the balances held to the "
                 "undersigned. A requisition for KYC and account records under Section 94 BNSS follows separately.",
        "sig": "(Signature)<br>{name}<br>{rank}, Investigating Officer<br>P.S. {ps}, {district}<br>Date: {blank}",
        "annex": "Annex A: blockchain evidence",
        "annex_line": "Flagged wallet {wallet} · alert {alert} · {atype} · risk {risk}/100 ({sev})",
        "cols": ["#", "Deposit address", "Transaction ID", "BTC", "Time (UTC)", "Hops"],
        "rule": "Directive rule:", "why": "Why the wallet was flagged:",
        "seal": "Annex SHA-256: {digest}<br>{stamp}<br>Generated {gen}, offline. Recompute the hash of the annex JSON to verify integrity.",
        "review": "",
    },
    "hi": {
        "draft": "ब्लॉकचेन साक्ष्य से BEANS द्वारा तैयार प्रारूप। अन्वेषण अधिकारी तथ्यों की जाँच करें, प्रत्येक {blank} "
                 "भरें एवं जारी करने से पूर्व हस्ताक्षर करें।",
        "ref": "प्राथमिकी / प्रकरण क्र. {fir} दिनांक {date}, थाना {ps}, {district}",
        "to": "सेवा में,<br>प्रधान अधिकारी / नोडल अधिकारी (विधि प्रवर्तन अनुरोध)<br><b>{vasp}</b><br>{addr}",
        "subject_label": "विषय:",
        "offshore": "<b>टिप्पणी:</b> यह एक्सचेंज भारत के बाहर संचालित प्रतीत होता है। यह पत्र केवल स्वैच्छिक अनुरोध हो सकता है; "
                    "औपचारिक मार्ग भारतीय नागरिक सुरक्षा संहिता, 2023 की धारा 112 के अंतर्गत अनुरोध-पत्र (Letter of Request) / एमएलएटी है।",
        "s94_title": "भारतीय नागरिक सुरक्षा संहिता, 2023 की धारा 94 के अंतर्गत सूचना",
        "s94_subject": "क्रिप्टोकरेंसी जमा पते(पतों) से संबंधित केवाईसी एवं खाता अभिलेख प्रस्तुत करने हेतु: {ref}",
        "s94_p1": "चूँकि उपर्युक्त प्रकरण, जो {offences} के अंतर्गत पंजीबद्ध है, का अन्वेषण प्रचलित है, तथा यह संज्ञान में आया है कि "
                  "प्रकरण से संबंधित आगम आपके एक्सचेंज द्वारा नियंत्रित निम्नलिखित पते(पतों) पर जमा किए गए:",
        "s94_p2": "और चूँकि नीचे सूचीबद्ध दस्तावेज़ एवं अभिलेख उक्त अन्वेषण के प्रयोजन हेतु आवश्यक हैं, अतः भारतीय नागरिक सुरक्षा "
                  "संहिता, 2023 की धारा 94 के अंतर्गत आपको निर्देशित किया जाता है कि इस सूचना की प्राप्ति के <b>{days} दिवस</b> "
                  "के भीतर इन्हें भारतीय साक्ष्य अधिनियम, 2023 की धारा 63 के अंतर्गत प्रमाणपत्र सहित प्रमाणित इलेक्ट्रॉनिक रूप में प्रस्तुत करें:",
        "s94_items": ["उपर्युक्त प्रत्येक पता जिस खाताधारक(कों) को आवंटित है, उनके केवाईसी दस्तावेज़ (नाम, पैन, फ़ोटो, मोबाइल नंबर, "
                      "ई-मेल, पते का प्रमाण) तथा खाता खोलने की तिथि।",
                      "उक्त खातों की {since} से आज तक की जमा, ट्रेड एवं निकासी (क्रिप्टो एवं INR) की संपूर्ण खाता-बही।",
                      "उसी अवधि के लॉगिन, आईपी पता एवं डिवाइस लॉग, समय सहित।",
                      "उक्त खातों से जुड़े या उनके द्वारा प्रयुक्त बैंक खाते, यूपीआई आईडी एवं भुगतान गेटवे।",
                      "उक्त खातों से हुई सभी क्रिप्टो निकासियों के गंतव्य पते एवं ट्रांज़ैक्शन आईडी।"],
        "s94_close": "आपसे यह भी अनुरोध है कि खाताधारक(कों) को इस सूचना के बारे में अवगत न कराएँ, क्योंकि इससे अन्वेषण बाधित हो सकता है।",
        "fr_title": "जमा राशि को तत्काल फ्रीज़ / होल्ड करने हेतु अनुरोध (धारा 106, भारतीय नागरिक सुरक्षा संहिता, 2023)",
        "fr_subject": "क्रिप्टोकरेंसी जमा पते(पतों) पर जमा राशि को तत्काल रोकने हेतु: {ref}",
        "fr_p1": "उपर्युक्त प्रकरण, जो {offences} के अंतर्गत पंजीबद्ध है, के अन्वेषण के दौरान अपराध से संबंधित संदिग्ध आगम को बिटकॉइन "
                 "ब्लॉकचेन पर आपके एक्सचेंज के निम्नलिखित जमा पते(पतों) तक ट्रेस किया गया है। {timing} अतः संभावना है कि राशि अभी भी आपके पास है:",
        "fr_quick": "चिह्नित वॉलेट को राशि प्राप्त होने के <b>{m} मिनट</b> बाद पहली जमा आपके एक्सचेंज पर पहुँची,",
        "fr_fresh": "यह जमा हमारे पास उपलब्ध नवीनतम ट्रांज़ैक्शन डेटा से <b>{m} मिनट</b> पहले आपके एक्सचेंज पर पहुँची,",
        "fr_other": "जमा राशियाँ अनुलग्नक क में सूचीबद्ध हैं,",
        "fr_p2": "भारतीय नागरिक सुरक्षा संहिता, 2023 की धारा 106 के अंतर्गत प्रदत्त शक्तियों का प्रयोग करते हुए आपसे अनुरोध है कि इन "
                 "पतों से संबंधित खाते(खातों) की समस्त शेष राशि (क्रिप्टो एवं INR) को <b>तत्काल फ्रीज़ / होल्ड</b> करें, निकासी "
                 "अवरुद्ध करें, तथा की गई कार्यवाही एवं रोकी गई राशि की पुष्टि अधोहस्ताक्षरी को करें। धारा 94 के अंतर्गत केवाईसी एवं "
                 "खाता अभिलेखों की अध्यपेक्षा पृथक से भेजी जा रही है।",
        "sig": "(हस्ताक्षर)<br>{name}<br>{rank}, अन्वेषण अधिकारी<br>थाना {ps}, {district}<br>दिनांक: {blank}",
        "annex": "अनुलग्नक क: ब्लॉकचेन साक्ष्य",
        "annex_line": "चिह्नित वॉलेट {wallet} · अलर्ट {alert} · {atype} · जोखिम {risk}/100 ({sev})",
        "cols": ["क्र.", "जमा पता", "ट्रांज़ैक्शन आईडी", "BTC", "समय (UTC)", "हॉप"],
        "rule": "निर्देश नियम:", "why": "वॉलेट को चिह्नित करने के कारण (अंग्रेज़ी में):",
        "seal": "अनुलग्नक SHA-256: {digest}<br>{stamp}<br>{gen} को ऑफ़लाइन तैयार। सत्यनिष्ठा जाँचने हेतु अनुलग्नक JSON का हैश पुनः गणना करें।",
        "review": "हिंदी पाठ मशीन-सहायित प्रारूप है: जारी करने से पूर्व विधिक समीक्षा आवश्यक। "
                  "(Hindi text: legal review by a native speaker required before issue.)",
    },
}


def _html(kind: str, a: Dict[str, Any], io: Dict[str, Any], digest: str, ts: Dict[str, Any], lang: str = "en") -> str:
    T = TEXT[lang]
    dep_rows = "".join(
        f"<tr><td>{i}</td><td class=mono>{_esc(d['deposit_address'])}</td><td class=mono>{_esc(d['txid'])}</td>"
        f"<td>{d['amount_btc']:.8f}</td><td>{_esc(d['deposit_ts'])}</td><td>{_esc(d['hops'])}</td></tr>"
        for i, d in enumerate(a["deposits"], 1))
    addrs = "".join(f"<li class=mono>{_esc(d['deposit_address'])}</li>" for d in a["deposits"])
    ref = T["ref"].format(fir=_esc(io["fir_no"]), date=_esc(io["fir_date"]), ps=_esc(io["police_station"]),
                          district=_esc(io["district_state"]))
    to = T["to"].format(vasp=_esc(a["vasp"]), addr=_esc(io["vasp_address_line"]))
    days = html.escape(str(io["reply_days"] or "7"))
    offshore = "" if a["vasp_in_jurisdiction"] else f"<p>{T['offshore']}</p>"
    if kind == "section94":
        title, subject = T["s94_title"], T["s94_subject"].format(ref=ref)
        items = "".join(f"<li>{x.format(since=_esc(a['period_utc']['from'][:10]))}</li>" for x in T["s94_items"])
        body = (f"<p>{T['s94_p1'].format(offences=_esc(io['offences']))}</p><ol>{addrs}</ol>"
                f"<p>{T['s94_p2'].format(days=days)}</p><ol>{items}</ol><p>{T['s94_close']}</p>")
    else:
        title, subject = T["fr_title"], T["fr_subject"].format(ref=ref)
        trig = a.get("freeze_trigger") or {}
        if trig.get("minutes_before_latest_data") is not None:
            timing = T["fr_fresh"].format(m=_esc(trig["minutes_before_latest_data"]))
        elif a["deposits"][0].get("minutes_after_receipt") is not None:
            timing = T["fr_quick"].format(m=_esc(a["deposits"][0]["minutes_after_receipt"]))
        else:
            timing = T["fr_other"]
        body = (f"<p>{T['fr_p1'].format(offences=_esc(io['offences']), timing=timing)}</p><ol>{addrs}</ol>"
                f"<p>{T['fr_p2']}</p>")
    stamp_line = (f"RFC 3161: {_esc(ts.get('gen_time'))} · serial {_esc(ts.get('serial'))} · "
                  f"TSA CA {_esc(ts.get('tsa_ca_sha256_fingerprint'))}" if ts.get("status") == "stamped"
                  else f"RFC 3161: not available ({_esc(ts.get('reason'))})")
    heads = "".join(f"<th>{c}</th>" for c in T["cols"])
    review = f'<div class=draft style="border-color:#1d4ed8;color:#1d4ed8">{T["review"]}</div>' if T["review"] else ""
    return f"""<!doctype html><html lang={lang}><head><meta charset=utf-8><title>{html.escape(title)}</title><style>{_CSS}</style></head><body>
    <div class=draft>{T['draft'].format(blank=BLANK)}</div>{review}
    <h1>{title}</h1><div class=sub>{ref}</div>
    <p style="margin-top:14px">{to}</p>
    <p><b>{T['subject_label']}</b> {subject}</p>
    {offshore}{body}
    <div class=sig>{T['sig'].format(name=_esc(io['io_name']), rank=_esc(io['io_rank']), ps=_esc(io['police_station']),
                                    district=_esc(io['district_state']), blank=BLANK)}</div>
    <h2>{T['annex']}</h2>
    <p>{T['annex_line'].format(wallet=f"<span class=mono>{_esc(a['flagged_wallet'])}</span>", alert=_esc(a['alert_id']),
                               atype=_esc(a['alert_type']), risk=_esc(a['risk_score']), sev=_esc(a['severity']))}</p>
    <table><tr>{heads}</tr>{dep_rows}</table>
    <p><b>{T['rule']}</b> {_esc(a['directive'].get('rule'))}</p>
    <p><b>{T['why']}</b></p><ul>{''.join(f'<li>{_esc(r)}</li>' for r in a['reasons'])}</ul>
    <div class=seal>{T['seal'].format(digest=f"<span class=mono>{digest}</span>", stamp=stamp_line, gen=_esc(a['generated_at']))}</div>
    </body></html>"""


def with_status(doc_html: str, req: dict, auth: bool = True) -> str:
    """Replace the draft banner with the request's approval state (the evidence hash is unaffected)."""
    st = req.get("status")
    if st == "APPROVED":
        who = f"{req.get('decided_by')} on {str(req.get('decided_at'))[:19]} UTC"
        extra = "" if auth else " (single-user mode: no second-person check)"
        banner = (f'<div class=draft style="border-color:#15803d;color:#15803d">APPROVED FOR ISSUE by supervisor {html.escape(who)}'
                  f'{extra}. Request #{req["id"]}, drafted by {html.escape(str(req.get("created_by")))}. '
                  "The Investigating Officer must still sign before issue.</div>")
    elif st == "REJECTED":
        banner = (f'<div class=draft>REJECTED by {html.escape(str(req.get("decided_by")))}: '
                  f'{html.escape(str(req.get("decision_comment") or "no comment"))}. Not for issue.</div>')
    else:
        banner = (f'<div class=draft style="border-color:#c2410c;color:#c2410c">PENDING SUPERVISOR APPROVAL (request #{req["id"]}, '
                  f'drafted by {html.escape(str(req.get("created_by")))}). Not for issue.</div>')
    start = doc_html.index("<div class=draft>")
    end = doc_html.index("</div>", start) + len("</div>")
    return doc_html[:start] + banner + doc_html[end:]
