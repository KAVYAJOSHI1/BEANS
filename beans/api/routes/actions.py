"""Action directives, legal drafts (Section 94 / freeze), FIU referral packs, attribution list and local TSA."""
import tempfile
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Body, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse, Response

from beans.api import db
from beans.api.rescore import rescore_all
from beans.api.routes.alerts import alert_out
from beans.decision.actions import ACTIONS
from beans.report import bnss, referral, timestamp
from beans.report.pdf_export import CaseReportGenerator
from beans.store.duck import DuckStore

router = APIRouter(tags=["Actions & Legal"])


def _alert(alert_id: str) -> Dict[str, Any]:
    row = db.one("SELECT * FROM alerts WHERE alert_id = ?", [alert_id])
    if not row:
        raise HTTPException(404, f"alert {alert_id} not found")
    return alert_out(row)


def _render(doc_html: str, fmt: str, stem: str, payload: Dict[str, Any]):
    if fmt == "pdf":
        try:
            pdf = CaseReportGenerator.to_pdf(doc_html)
        except Exception as e:  # missing system libs
            raise HTTPException(501, f"PDF rendering unavailable ({e}); use fmt=html") from e
        return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{stem}.pdf"'})
    if fmt == "html":
        return Response(doc_html, media_type="text/html")
    return payload


@router.get("/actions/summary")
def actions_summary() -> Dict[str, Any]:
    counts = {r["action"]: r["n"] for r in db.query(
        "SELECT json_extract_string(recommended_action, '$.action') AS action, COUNT(*) AS n FROM alerts "
        "WHERE recommended_action IS NOT NULL GROUP BY 1")}
    return {"actions": [{"action": k, **v, "count": counts.get(k, 0)} for k, v in ACTIONS.items()],
            "known_entities": db.scalar("SELECT COUNT(*) FROM known_entities")}


@router.post("/alerts/{alert_id}/legal/{kind}")
def legal_draft(alert_id: str, kind: str, io: Dict[str, Any] = Body(default={}),
                fmt: str = Query("json", pattern="^(json|html|pdf)$"), vasp: str = Query(None)):
    if kind not in bnss.KINDS:
        raise HTTPException(422, f"kind must be one of {sorted(bnss.KINDS)}")
    try:
        doc = bnss.build(kind, _alert(alert_id), io, vasp)
    except LookupError as e:
        raise HTTPException(409, str(e)) from e
    db.audit("LEGAL_DRAFT", "ALERT", alert_id, {"kind": kind, "vasp": doc["vasp"], "evidence_sha256": doc["evidence_sha256"],
                                                 "timestamp_serial": doc["timestamp"].get("serial")})
    return _render(doc["html"], fmt, f"BEANS_{kind}_{alert_id}", doc)


@router.get("/alerts/{alert_id}/referral")
def referral_pack(alert_id: str, fmt: str = Query("json", pattern="^(json|html|pdf)$")):
    a = _alert(alert_id)
    wallet = db.one("SELECT total_received, total_sent, balance, transaction_count FROM wallet_profiles WHERE address = ?",
                    [a["entity_id"]]) or {}
    ips = db.query("SELECT src_ip AS ip, any_value(geo_country) AS country, any_value(asn) AS asn, "
                   "any_value(asn_type) AS asn_type, COUNT(*) AS n FROM transactions "
                   "WHERE list_contains(input_addresses, ?) GROUP BY 1 ORDER BY n DESC LIMIT 20", [a["entity_id"]])
    sources = db.query("SELECT file, sha256, records, ingested_at FROM ingest_log ORDER BY ingested_at")
    pack = referral.build(a, wallet, ips, sources)
    db.audit("REFERRAL_PACK", "ALERT", alert_id, {"evidence_sha256": pack["evidence_sha256"], "format": fmt})
    return _render(pack["html"], fmt, f"BEANS_referral_{alert_id}", pack)


# ------------------------------------------------------------------ attribution list (exchanges / mining pools)
@router.get("/known-entities")
def known_entities_summary():
    return db.query("SELECT entity_name, entity_type, country, in_jurisdiction, COUNT(*) AS addresses FROM known_entities "
                    "GROUP BY ALL ORDER BY addresses DESC")


@router.post("/known-entities/upload")
async def upload_known_entities(file: UploadFile = File(...), rescore: bool = True):
    """CSV: address, entity_name[, entity_type (VASP|MINING_POOL|…), country, in_jurisdiction, source]."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(await file.read())
    try:
        n = DuckStore().load_known_entities(Path(tmp.name))
    except Exception as e:
        raise HTTPException(422, f"could not load attribution CSV: {e}") from e
    finally:
        Path(tmp.name).unlink(missing_ok=True)
    db.audit("KNOWN_ENTITIES_UPLOAD", "FILE", file.filename, {"added": n})
    out = {"status": "success", "added": n}
    if rescore:
        out["rescore"] = rescore_all()
    return out


# ------------------------------------------------------------------ local RFC 3161 TSA
@router.get("/tsa")
def tsa_status():
    return {"openssl": timestamp.available(), "initialised": (timestamp.tsa_dir() / "tsa.pem").exists(),
            "ca_sha256_fingerprint": timestamp.ca_fingerprint()}


@router.get("/tsa/{name}", response_class=PlainTextResponse)
def tsa_cert(name: str):
    if name not in ("tsa_ca.pem", "tsa.pem"):
        raise HTTPException(404, "only tsa_ca.pem and tsa.pem are published")
    p = timestamp.tsa_dir() / name
    if not p.exists():
        raise HTTPException(404, "TSA not initialised yet (it is created on the first timestamp)")
    return p.read_text()


@router.post("/tsa/verify")
def tsa_verify(payload: Dict[str, Any]):
    try:
        return {"valid": timestamp.verify(str(payload["sha256"]), str(payload["token_der_b64"]))}
    except (KeyError, ValueError) as e:
        raise HTTPException(422, f"need sha256 and token_der_b64: {e}") from e
