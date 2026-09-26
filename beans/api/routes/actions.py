"""Action directives, legal drafts (Section 94 / freeze), FIU referral packs, attribution list and local TSA."""
import tempfile
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse, Response

import json

from beans.api import auth, db
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
    """Draft a Section 94 / freeze request. It is stored PENDING_APPROVAL until a (different) supervisor decides."""
    if kind not in bnss.KINDS:
        raise HTTPException(422, f"kind must be one of {sorted(bnss.KINDS)}")
    alert = _alert(alert_id)
    try:
        doc = bnss.build(kind, alert, io, vasp)
    except LookupError as e:
        raise HTTPException(409, str(e)) from e
    req_id = int(db.scalar("SELECT COALESCE(MAX(id), 0) + 1 FROM legal_requests"))
    db.execute("""INSERT INTO legal_requests (id, alert_id, entity_id, kind, vasp, io, annex, evidence_sha256,
                  timestamp_token, html, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
               [req_id, alert_id, alert["entity_id"], kind, doc["vasp"], json.dumps(io or {}), json.dumps(doc["annex"], default=str),
                doc["evidence_sha256"], json.dumps(doc["timestamp"]), doc["html"], auth.current_user()["username"]])
    db.audit("LEGAL_DRAFT", "ALERT", alert_id, {"kind": kind, "vasp": doc["vasp"], "request_id": req_id,
                                                 "evidence_sha256": doc["evidence_sha256"],
                                                 "timestamp_serial": doc["timestamp"].get("serial")})
    req = _request(req_id)
    return _render(req["html"], fmt, f"BEANS_{kind}_{alert_id}_DRAFT", {**doc, "html": req["html"], "request": _public(req)})


def _request(req_id: int) -> Dict[str, Any]:
    req = db.one("SELECT * FROM legal_requests WHERE id = ?", [req_id])
    if not req:
        raise HTTPException(404, f"legal request {req_id} not found")
    req["html"] = bnss.with_status(req["html"], req, auth=req.get("decided_by") != auth.SINGLE_USER["username"])
    return req


def _public(req: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in req.items() if k != "html"}


@router.get("/legal-requests")
def legal_requests(status: str = Query(None)):
    where, params = ("WHERE status = ?", [status.upper()]) if status and status != "ALL" else ("", [])
    return db.query(f"SELECT id, alert_id, entity_id, kind, vasp, evidence_sha256, status, created_by, created_at, "
                    f"decided_by, decided_at, decision_comment FROM legal_requests {where} ORDER BY id DESC", params)


@router.get("/legal-requests/{req_id}")
def legal_request(req_id: int, fmt: str = Query("json", pattern="^(json|html|pdf)$")):
    req = _request(req_id)
    suffix = "APPROVED" if req["status"] == "APPROVED" else req["status"]
    return _render(req["html"], fmt, f"BEANS_{req['kind']}_{req['alert_id']}_{suffix}", {**_public(req), "html": req["html"]})


@router.post("/legal-requests/{req_id}/decision", dependencies=[Depends(auth.require("SUPERVISOR"))])
def decide(req_id: int, payload: Dict[str, Any]):
    req = _request(req_id)
    decision = str(payload.get("decision") or "").upper()
    if decision not in ("APPROVE", "REJECT"):
        raise HTTPException(422, "decision must be APPROVE or REJECT")
    if req["status"] != "PENDING_APPROVAL":
        raise HTTPException(409, f"request is already {req['status']}")
    user = auth.current_user()
    if user["auth"] and user["username"] == req["created_by"]:
        raise HTTPException(403, "four-eyes rule: the drafter cannot approve their own request")
    if decision == "REJECT" and not str(payload.get("comment") or "").strip():
        raise HTTPException(422, "a rejection needs a comment")
    status = "APPROVED" if decision == "APPROVE" else "REJECTED"
    db.execute("UPDATE legal_requests SET status = ?, decided_by = ?, decision_comment = ?, decided_at = now() WHERE id = ?",
               [status, user["username"], payload.get("comment"), req_id])
    db.audit("LEGAL_DECISION", "LEGAL_REQUEST", str(req_id), {"decision": status, "comment": payload.get("comment"),
                                                              "evidence_sha256": req["evidence_sha256"]})
    return _public(_request(req_id))


@router.get("/alerts/{alert_id}/referral")
def referral_pack(alert_id: str, fmt: str = Query("json", pattern="^(json|html|pdf)$")):
    a = _alert(alert_id)
    wallet = db.one("SELECT total_received, total_sent, balance, transaction_count FROM wallet_profiles WHERE address = ?",
                    [a["entity_id"]]) or {}
    ips = db.query("SELECT src_ip AS ip, any_value(geo_country) AS country, any_value(asn) AS asn, "
                   "any_value(asn_type) AS asn_type, COUNT(*) AS n FROM transactions "
                   "WHERE list_contains(input_addresses, ?) GROUP BY 1 ORDER BY n DESC LIMIT 20", [a["entity_id"]])
    sources = db.query("SELECT file, sha256, records, ingested_at FROM ingest_log ORDER BY ingested_at")
    from beans.api.routes.timeline import follow_the_money
    pack = referral.build(a, wallet, ips, sources, follow_the_money(a["entity_id"], 30))
    db.audit("REFERRAL_PACK", "ALERT", alert_id, {"evidence_sha256": pack["evidence_sha256"], "format": fmt})
    return _render(pack["html"], fmt, f"BEANS_referral_{alert_id}", pack)


# ------------------------------------------------------------------ attribution list (exchanges / mining pools)
@router.get("/known-entities")
def known_entities_summary():
    return db.query("SELECT entity_name, entity_type, country, in_jurisdiction, COUNT(*) AS addresses FROM known_entities "
                    "GROUP BY ALL ORDER BY addresses DESC")


@router.post("/known-entities/upload", dependencies=[Depends(auth.require("SUPERVISOR"))])
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
