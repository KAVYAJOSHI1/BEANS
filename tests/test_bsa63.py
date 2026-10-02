"""Section 63 BSA certificate: sealed annex, per-record hashes, tamper detection, four-eyes approval."""
import copy

from beans.report import bsa63
from tests.test_nextgen import client  # noqa: F401 (fixture)

ALERT = {"alert_id": "A1", "entity_id": "W1", "alert_type": "RANSOMWARE_PATTERN", "risk_score": 91.0, "severity": "CRITICAL",
         "reasons": ["peel chain of 7 hops"], "recommended_action": {"action": "ANALYST_REVIEW"}, "evidence": {"txid": "t1"}}
TX = [{"txid": f"t{i}", "timestamp": f"2026-09-01 10:0{i}:00", "input_addresses": ["a"], "input_amounts": [1.0],
       "output_addresses": ["b"], "output_amounts": [0.9], "fee": 0.1, "src_ip": f"203.0.113.{i}"} for i in range(3)]
SRC = [{"file": "day1.csv", "sha256": "ab" * 32, "records": 3, "ingested_at": "2026-09-01"}]


def _doc(io=None):
    return bsa63.build([ALERT], TX, SRC, io)


def test_annex_is_sealed_and_checks_out():
    d = _doc()
    chk = bsa63.check(d["annex"])
    assert chk["annex_sha256"] == d["evidence_sha256"] and chk["record_hashes_valid"] and chk["records_root_valid"]
    assert d["verification_code"] == bsa63.verification_code(d["evidence_sha256"]) and len(d["verification_code"]) == 19


def test_any_edit_is_detected():
    d = _doc()
    bad = copy.deepcopy(d["annex"])
    bad["records"][1]["output_amounts"] = [9.9]
    chk = bsa63.check(bad)
    assert not chk["record_hashes_valid"] and chk["bad_records"] == ["t1"] and chk["annex_sha256"] != d["evidence_sha256"]
    dropped = copy.deepcopy(d["annex"])
    dropped["records"].pop()
    assert not bsa63.check(dropped)["records_root_valid"]


def test_unknown_facts_stay_blank_and_nothing_is_asserted_about_the_officer():
    d = _doc()
    assert len(d["missing_fields"]) == len(bsa63.IO_FIELDS)
    assert "[__________]" in d["html"] and "BEANS cannot assert this" in d["html"]
    filled = _doc({"certifier_name": "R. Sharma", "expert_name": "A. Rao"})
    assert "R. Sharma" in filled["html"] and "A. Rao" in filled["html"]
    assert "admissible" not in d["html"].replace("not show that the certificate is admissible", "")


def test_banner_can_be_swapped_for_the_approval_state():
    from beans.report import bnss
    d = _doc()
    out = bnss.with_status(d["html"], {"id": 7, "status": "PENDING_APPROVAL", "created_by": "alice"})
    assert "PENDING SUPERVISOR APPROVAL" in out and "Part A" in out


def test_an_empty_case_cannot_be_certified():
    import pytest
    with pytest.raises(LookupError):
        bsa63.build([], TX, SRC)


def test_alert_and_case_certificates_go_through_four_eyes(client):
    a = client.get("/api/alerts?limit=5").json()[0]
    r = client.post(f"/api/alerts/{a['alert_id']}/bsa63", json={"certifier_name": "IO One"})
    assert r.status_code == 200
    body = r.json()
    assert body["request"]["kind"] == "BSA63" and body["request"]["status"] == "PENDING_APPROVAL"
    ok = client.post("/api/bsa63/verify", json={"annex": body["request"]["annex"], "sha256": body["evidence_sha256"]}).json()
    assert ok["matches_expected"] and ok["record_hashes_valid"] and ok["records_root_valid"]
    assert any(x["kind"] == "BSA63" for x in client.get("/api/legal-requests").json())
    case = client.post("/api/cases", json={"case_name": "bsa", "suspect_entities": [a["entity_id"]]}).json()
    c = client.post(f"/api/cases/{case['case_id']}/bsa63")
    assert c.status_code == 200 and c.json()["request"]["alert_id"] == a["alert_id"]
    empty = client.post("/api/cases", json={"case_name": "none", "suspect_entities": []}).json()
    assert client.post(f"/api/cases/{empty['case_id']}/bsa63").status_code == 409
    assert client.post("/api/alerts/NOPE/bsa63").status_code == 404
    assert client.get(f"/api/alerts/{a['alert_id']}/referral").status_code == 200   # other packs unaffected
