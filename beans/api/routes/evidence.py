"""Section 63 BSA 2023 certificates for an alert or a whole case, filed like the other legal drafts (four-eyes)."""
import json
from typing import Any, Dict, List

from fastapi import APIRouter, Body, HTTPException, Query

from beans.api import auth, db
from beans.api.routes.actions import _public, _render, _request
from beans.api.routes.alerts import alert_out
from beans.report import bsa63

router = APIRouter(tags=["Evidence (Section 63 BSA)"])


def _txids(alert: Dict[str, Any]) -> List[str]:
    ev, ra = alert.get("evidence") or {}, alert.get("recommended_action") or {}
    ids = [ev.get("txid"), *(ev.get("top_txids") or []), *(ev.get("peel_chain") or [])]
    for h in (ra.get("vasp_exposure") or [])[:3] + (ra.get("cross_chain_exits") or [])[:3]:
        ids += [h.get("txid"), *(h.get("path") or [])]
    return list(dict.fromkeys(t for t in ids if t))


def _file(subjects: List[Dict[str, Any]], io: Dict[str, Any], case: Dict[str, Any] = None, scope: str = ""):
    txids = list(dict.fromkeys(t for s in subjects for t in _txids(s)))[: bsa63.MAX_RECORDS + 1]
    records = db.query("SELECT txid, timestamp, input_addresses, input_amounts, output_addresses, output_amounts, fee, src_ip "
                       "FROM transactions WHERE list_contains(?, txid) ORDER BY timestamp, txid", [txids]) if txids else []
    sources = db.query("SELECT file, sha256, records, ingested_at FROM ingest_log ORDER BY ingested_at")
    try:
        doc = bsa63.build(subjects, records, sources, io, case)
    except LookupError as e:
        raise HTTPException(409, str(e)) from e
    req_id = int(db.scalar("SELECT COALESCE(MAX(id), 0) + 1 FROM legal_requests"))
    db.execute("""INSERT INTO legal_requests (id, alert_id, entity_id, kind, vasp, io, annex, evidence_sha256,
                  timestamp_token, html, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
               [req_id, doc["alert_id"], subjects[0]["entity_id"], bsa63.KIND, None, json.dumps(io or {}),
                json.dumps(doc["annex"], default=str), doc["evidence_sha256"], json.dumps(doc["timestamp"]), doc["html"],
                auth.current_user()["username"]])
    db.audit("BSA63_DRAFT", "CASE" if case else "ALERT", str(case["id"]) if case else subjects[0]["alert_id"],
             {"request_id": req_id, "evidence_sha256": doc["evidence_sha256"], "records": len(doc["annex"]["records"]),
              "alerts": len(subjects), "timestamp_serial": doc["timestamp"].get("serial")})
    return doc, _request(req_id)


@router.post("/alerts/{alert_id}/bsa63")
def alert_certificate(alert_id: str, io: Dict[str, Any] = Body(default={}),
                      fmt: str = Query("json", pattern="^(json|html|pdf)$")):
    row = db.one("SELECT * FROM alerts WHERE alert_id = ?", [alert_id])
    if not row:
        raise HTTPException(404, f"alert {alert_id} not found")
    doc, req = _file([alert_out(row)], io)
    return _render(req["html"], fmt, f"BEANS_BSA63_{alert_id}_DRAFT",
                   {"verification_code": doc["verification_code"], "evidence_sha256": doc["evidence_sha256"],
                    "timestamp": doc["timestamp"], "missing_fields": doc["missing_fields"], "html": req["html"],
                    "request": _public(req)})


@router.post("/cases/{case_id}/bsa63")
def case_certificate(case_id: int, io: Dict[str, Any] = Body(default={}),
                     fmt: str = Query("json", pattern="^(json|html|pdf)$")):
    case = db.one("SELECT * FROM case_files WHERE id = ?", [case_id])
    if not case:
        raise HTTPException(404, f"case {case_id} not found")
    suspects = case["suspect_entities"] or []
    rows = db.query("SELECT * FROM alerts WHERE list_contains(?, entity_id) ORDER BY risk_score DESC", [suspects]) if suspects else []
    doc, req = _file([alert_out(r) for r in rows], io, case)
    return _render(req["html"], fmt, f"BEANS_BSA63_case{case_id}_DRAFT",
                   {"verification_code": doc["verification_code"], "evidence_sha256": doc["evidence_sha256"],
                    "timestamp": doc["timestamp"], "missing_fields": doc["missing_fields"], "html": req["html"],
                    "request": _public(req)})


@router.post("/bsa63/verify")
def verify(payload: Dict[str, Any]):
    """Recompute the annex hash and every record hash of a stored annex; compare with an expected SHA-256 if given."""
    annex = payload.get("annex")
    if not isinstance(annex, dict):
        raise HTTPException(422, "annex (the stored annex JSON) is required")
    res = bsa63.check(annex)
    exp = str(payload.get("sha256") or "").lower()
    if exp:
        res["matches_expected"] = exp == res["annex_sha256"]
    res["verification_code"] = bsa63.verification_code(res["annex_sha256"])
    return res
