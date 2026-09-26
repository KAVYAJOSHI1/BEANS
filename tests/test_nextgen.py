"""Action directives, legal drafts, RFC 3161 timestamps, referral packs and SIEM webhooks."""
import hashlib
import json
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pandas as pd
import pytest

from beans.decision import actions
from beans.features.extractors import Frames

T = datetime(2026, 9, 1, 12, 0)
VASP_IN = {"entity_name": "VASP-IN", "entity_type": "VASP", "country": "IN", "in_jurisdiction": True}
VASP_OFF = {"entity_name": "VASP-OFF", "entity_type": "VASP", "country": "SC", "in_jurisdiction": False}


def _frames(txs):
    """txs: list of (txid, minutes, [(in_addr, amt)], [(out_addr, amt)])."""
    tx, tin, tout = [], [], []
    for txid, m, ins, outs in txs:
        ts = T + timedelta(minutes=m)
        tx.append({"txid": txid, "ts": ts, "fee": 0.0001, "script_type": "P2WPKH"})
        tin += [{"txid": txid, "ts": ts, "address": a, "amount": v} for a, v in ins]
        tout += [{"txid": txid, "ts": ts, "idx": i, "address": a, "amount": v} for i, (a, v) in enumerate(outs)]
    return Frames(pd.DataFrame(tx), pd.DataFrame(tin, columns=["txid", "ts", "address", "amount"]),
                  pd.DataFrame(tout), pd.DataFrame())


def _decide(frames, wallet, known, risk=90.0, **w):
    W = pd.DataFrame([{"recv_btc": 0.5, "sent_btc": 0.5, "share_risky_asn": 0.0, "taint": 0.0, "hops_from_seed": 99,
                       "hops_to_seed": 99, "max_p_peel": 0.0, "max_p_coinjoin": 0.0, "max_p_fan_out": 0.0,
                       "max_peel_chain_len": 0, "cluster_id": "SOLO-1", **w}], index=[wallet])
    alert = {"alert_id": "A1", "entity_id": wallet, "risk_score": risk, "evidence": {},
             "shap_top_features": [{"feature": "taint", "value": 0.4, "impact": 1.2}, {"feature": "x", "value": 0, "impact": -0.5}]}
    actions.recommend([alert], W, frames, known)
    return alert["recommended_action"]


def test_fast_exchange_deposit_is_a_freeze_draft():
    f = _frames([("t0", 0, [("src", 1.0)], [("W", 0.5)]), ("t1", 12, [("W", 0.5)], [("DEP", 0.49)])])
    ra = _decide(f, "W", {"DEP": VASP_IN})
    assert ra["action"] == "IMMEDIATE_FREEZE_DRAFT"
    assert ra["facts"]["minutes_after_receipt"] == 12.0 and ra["facts"]["deposit_address"] == "DEP"
    assert "DRAFT_SECTION_94_BNSS" in ra["also_matched"]
    assert ra["shap_support"] == [{"feature": "taint", "value": 0.4, "impact": 1.2}]   # only risk-raising features
    assert ra["vasp_exposure"][0]["vasp"] == "VASP-IN"


def test_slow_or_low_risk_deposit_is_a_section94_draft():
    f = _frames([("t0", 0, [("src", 1.0)], [("W", 0.5)]), ("t1", 300, [("W", 0.5)], [("X", 0.49)]),
                 ("t2", 320, [("X", 0.49)], [("DEP", 0.48)])])
    ra = _decide(f, "W", {"DEP": VASP_IN})
    assert ra["action"] == "DRAFT_SECTION_94_BNSS" and ra["facts"]["hops"] == 2
    fast = _frames([("t0", 0, [("src", 1.0)], [("W", 0.5)]), ("t1", 5, [("W", 0.5)], [("DEP", 0.49)])])
    assert _decide(fast, "W", {"DEP": VASP_IN}, risk=50)["action"] == "DRAFT_SECTION_94_BNSS"   # below freeze risk


def test_offshore_exchange_gets_jurisdiction_note_and_no_section94():
    f = _frames([("t0", 0, [("src", 1.0)], [("W", 0.5)]), ("t1", 10, [("W", 0.5)], [("DEP", 0.49)])])
    ra = _decide(f, "W", {"DEP": VASP_OFF})
    assert ra["action"] == "IMMEDIATE_FREEZE_DRAFT" and "Section 112" in ra["facts"]["jurisdiction_note"]
    assert "DRAFT_SECTION_94_BNSS" not in ra["also_matched"]


def test_layering_via_risky_infrastructure_is_a_referral():
    f = _frames([("t0", 0, [("src", 3.0)], [("W", 2.0)]), ("t1", 60, [("W", 2.0)], [("Y", 1.9)])])
    ra = _decide(f, "W", {}, recv_btc=2.0, sent_btc=2.0, share_risky_asn=1.0, max_p_peel=0.9)
    assert ra["action"] == "FIU_REFERRAL_PACK" and ra["facts"]["layering"] == {"peel": 0.9}


def test_dormant_tainted_balance_is_monitored_and_known_entity_is_benign():
    f = _frames([("t0", 0, [("src", 1.0)], [("W", 0.5)]), ("t9", 60 * 24, [("a", 1)], [("b", 1)])])
    assert _decide(f, "W", {}, recv_btc=0.5, sent_btc=0.0, taint=0.2)["action"] == "PASSIVE_TAINT_MONITOR"
    assert _decide(f, "W", {"W": VASP_IN})["action"] == "REVIEW_LIKELY_BENIGN"
    assert _decide(f, "W", {})["action"] == "ANALYST_REVIEW"


def test_decision_module_never_reads_ground_truth():
    src = Path(actions.__file__).read_text()
    assert "labels_address" not in src.split('"""', 2)[2] and "labels_tx" not in src


def test_rfc3161_timestamp_roundtrip():
    from beans.report import timestamp
    if not timestamp.available():
        pytest.skip("openssl not installed")
    digest = hashlib.sha256(b"evidence").hexdigest()
    ts = timestamp.stamp(digest)
    assert ts["status"] == "stamped" and ts["message_imprint"] == digest and ts["gen_time"]
    assert timestamp.verify(digest, ts["token_der_b64"])
    assert not timestamp.verify(hashlib.sha256(b"tampered").hexdigest(), ts["token_der_b64"])


# ------------------------------------------------------------------ API (full pipeline on the fixture dataset)
@pytest.fixture(scope="module")
def client(tmp_path_factory, dataset):
    from fastapi.testclient import TestClient
    from beans.config import settings
    settings.DB_PATH = tmp_path_factory.mktemp("db") / "nextgen.duckdb"
    from beans.api.main import app
    from beans.ingest.pipeline import ForensicPipeline
    from beans.store.duck import DuckStore
    ForensicPipeline(DuckStore(settings.DB_PATH)).load_sidecars(dataset)
    c = TestClient(app)
    with open(dataset / "transactions.csv", "rb") as fh:
        assert c.post("/api/ingest/upload", files={"file": ("fixture.csv", fh, "text/csv")}).status_code == 200
    return c


def test_every_alert_has_a_directive(client):
    alerts = client.get("/api/alerts?limit=1000").json()
    assert alerts and all(a["recommended_action"].get("action") in actions.ACTIONS for a in alerts)
    assert all(a["recommended_action"]["rule"] for a in alerts)
    summary = client.get("/api/actions/summary").json()
    assert sum(x["count"] for x in summary["actions"]) == len(alerts) and summary["known_entities"] > 0
    act = alerts[0]["recommended_action"]["action"]
    assert all(a["recommended_action"]["action"] == act for a in client.get(f"/api/alerts?action={act}").json())


def test_legal_drafts_and_referral(client):
    alerts = client.get("/api/alerts?limit=1000").json()
    exposed = next(a for a in alerts if a["recommended_action"].get("vasp_exposure"))
    r = client.post(f"/api/alerts/{exposed['alert_id']}/legal/section94", json={"fir_no": "123/2026", "io_name": "SI Test"})
    assert r.status_code == 200, r.text
    doc = r.json()
    assert "SECTION 94" in doc["html"] and "123/2026" in doc["html"] and "[__________]" in doc["html"]
    assert "fir_no" not in doc["missing_fields"] and "offences" in doc["missing_fields"]
    assert len(doc["evidence_sha256"]) == 64 and doc["annex"]["deposits"]
    assert client.post(f"/api/alerts/{exposed['alert_id']}/legal/freeze?fmt=html").text.startswith("<!doctype html>")
    assert client.post(f"/api/alerts/{exposed['alert_id']}/legal/bogus").status_code == 422
    unexposed = next((a for a in alerts if not a["recommended_action"].get("vasp_exposure")), None)
    if unexposed:
        assert client.post(f"/api/alerts/{unexposed['alert_id']}/legal/section94").status_code == 409

    pack = client.get(f"/api/alerts/{exposed['alert_id']}/referral").json()
    assert pack["dossier"]["subject"]["wallet"] == exposed["entity_id"] and len(pack["evidence_sha256"]) == 64
    if pack["timestamp"]["status"] == "stamped":
        assert client.post("/api/tsa/verify", json={"sha256": pack["evidence_sha256"],
                                                    "token_der_b64": pack["timestamp"]["token_der_b64"]}).json()["valid"]
        assert "BEGIN CERTIFICATE" in client.get("/api/tsa/tsa_ca.pem").text
    assert client.get("/api/tsa/tsa.key").status_code == 404


def test_case_pack_is_timestamped(client):
    a = client.get("/api/alerts").json()[0]
    case = client.post("/api/cases", json={"case_name": "ts", "suspect_entities": [a["entity_id"]]}).json()
    pack = client.get(f"/api/cases/{case['case_id']}/export").json()
    assert pack["timestamp"]["status"] in {"stamped", "unavailable"}
    assert pack["evidence"]["findings"][0]["recommended_action"]["action"]


class _Sink(BaseHTTPRequestHandler):
    received: list = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Sink.received.append((self.path, dict(self.headers), body))
        self.send_response(500 if self.path == "/fail" else 200)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def sink():
    srv = HTTPServer(("127.0.0.1", 0), _Sink)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_webhooks_deliver_once_per_alert(client, sink, monkeypatch):
    from beans.alerting import webhooks
    monkeypatch.setattr(webhooks, "RETRIES", (0.0,))
    assert client.post("/api/webhooks", json={"url": "ftp://x"}).status_code == 422
    h = client.post("/api/webhooks", json={"name": "splunk", "url": f"{sink}/hec", "fmt": "splunk_hec",
                                           "min_severity": "HIGH", "token": "s3cret"}).json()
    assert h["token_set"] and "token" not in h
    s = client.post("/api/webhooks", json={"url": f"{sink}/stix", "fmt": "stix", "min_severity": "CRITICAL"}).json()
    _Sink.received.clear()
    res = {r["webhook_id"]: r for r in client.post("/api/webhooks/dispatch").json()["results"]}
    n_high = sum(a["severity"] in ("HIGH", "CRITICAL") for a in client.get("/api/alerts?limit=1000").json())
    assert res[h["id"]]["sent"] == n_high
    hec = next(x for x in _Sink.received if x[0] == "/hec")
    assert hec[1]["Authorization"] == "Splunk s3cret"
    assert len(hec[2].decode().splitlines()) == n_high
    assert json.loads(hec[2].decode().splitlines()[0])["event"]["recommended_action"]
    if res[s["id"]]["sent"]:
        bundle = json.loads(next(x for x in _Sink.received if x[0] == "/stix")[2])
        assert bundle["type"] == "bundle" and bundle["objects"][-1]["type"] == "report"
    again = {r["webhook_id"]: r for r in client.post("/api/webhooks/dispatch").json()["results"]}
    assert again[h["id"]]["sent"] == 0                    # nothing is delivered twice
    assert client.post(f"/api/webhooks/{h['id']}/test").json()["ok"]

    bad = client.post("/api/webhooks", json={"url": f"{sink}/fail", "fmt": "json", "min_severity": "LOW"}).json()
    out = {r["webhook_id"]: r for r in client.post("/api/webhooks/dispatch").json()["results"]}
    assert out[bad["id"]]["ok"] is False and out[bad["id"]]["http_status"] == 500
    assert client.get("/api/webhooks").json()[-1]["failed"] > 0
    for x in (h, s, bad):
        client.delete(f"/api/webhooks/{x['id']}")


def test_known_entities_upload(client):
    csv = b"address,entity_name,entity_type,country,in_jurisdiction\nbc1qexampleaddr,Test Exchange,VASP,IN,true\n"
    r = client.post("/api/known-entities/upload?rescore=false", files={"file": ("k.csv", csv, "text/csv")})
    assert r.status_code == 200 and r.json()["added"] == 1
    assert any(k["entity_name"] == "Test Exchange" and k["in_jurisdiction"] for k in client.get("/api/known-entities").json())
    bad = client.post("/api/known-entities/upload?rescore=false", files={"file": ("k.csv", b"foo\n1\n", "text/csv")})
    assert bad.status_code == 422


def test_section94_prefers_indian_exchange():
    from beans.report import bnss
    alert = {"alert_id": "A1", "entity_id": "W", "risk_score": 90, "recommended_action": {
        "action": "IMMEDIATE_FREEZE_DRAFT", "facts": {"vasp": "VASP-OFF"}, "vasp_exposure": [
            {"vasp": "VASP-OFF", "in_jurisdiction": False, "country": "SC", "deposit_address": "D1", "txid": "t1",
             "amount_btc": 0.1, "deposit_ts": "2026-09-01 12:00:00", "hops": 1, "minutes_after_receipt": 5, "path": ["t1"]},
            {"vasp": "VASP-IN", "in_jurisdiction": True, "country": "IN", "deposit_address": "D2", "txid": "t2",
             "amount_btc": 0.1, "deposit_ts": "2026-09-01 13:00:00", "hops": 2, "minutes_after_receipt": 65, "path": ["t1", "t2"]}]}}
    assert bnss.build("section94", alert)["vasp"] == "VASP-IN"
    freeze = bnss.build("freeze", alert)
    assert freeze["vasp"] == "VASP-OFF" and "Section 112" in freeze["html"]


def test_thresholds_come_from_config(monkeypatch, client):
    from beans.config import settings
    from beans.score import run
    monkeypatch.setattr(settings, "RISK_CRITICAL_MIN", 95.0)
    assert run._severity(90) == "HIGH" and run._severity(96) == "CRITICAL"
    cfg = client.get("/api/config").json()
    assert cfg["severity_thresholds"]["CRITICAL"] == 95.0
    assert cfg["actions"]["ACTION_FREEZE_WINDOW_MIN"] == settings.ACTION_FREEZE_WINDOW_MIN
    assert cfg["data_origin"] == "synthetic" and client.get("/api/health").json()["data_origin"] == "synthetic"


def test_context_features_are_label_free():
    from beans.features import extractors
    src = Path(extractors.__file__).read_text()
    assert "labels_" not in src.split('"""', 2)[2]
    f = _frames([("t0", 0, [("hub", 5.0)], [("a", 0.095), ("b", 0.0951), ("c", 0.0949)]),
                 ("t1", 10, [("a", 0.095)], [("dep", 0.094)])])
    X = pd.DataFrame({"n_in": [1, 1], "n_out": [3, 1]}, index=["t0", "t1"])
    C = extractors.context_features(f, X)
    assert C.loc["a", "fund_below_round"] == 1.0          # 0.095 sits just below the 0.1 threshold
    assert C.loc["a", "fund_out_cv"] < 0.01               # near-identical sibling outputs (structuring)


def _xtx(f):
    n_in = f.tin.groupby("txid").size()
    n_out = f.tout.groupby("txid").size()
    X = pd.DataFrame({"n_in": n_in, "n_out": n_out}).fillna(0)
    X["peel_shape"] = 0.0
    X["peel_chain_len"] = 0.0
    return X


def test_self_split_merges_equal_fresh_parts_but_not_varied_payouts():
    from beans.engines import e1_cluster
    parts = [(f"p{i}", 0.5) for i in range(8)] + [("chg", 0.123456789)]
    payout = [(f"u{i}", 0.05 * (i + 1)) for i in range(8)]
    f = _frames([("t0", 0, [("src", 5.0)], [("L", 4.2)]), ("t1", 5, [("L", 4.2)], parts),
                 ("t2", 10, [("HOT", 9.0)], payout)])
    cl, rep = e1_cluster.cluster(f, _xtx(f), set())
    assert rep["split_merges"] == 1
    assert cl["p0"] == cl["p7"] == cl["L"] == cl["chg"]           # one owner split the balance
    assert cl["u0"] != cl["u1"]                                     # varied payout amounts: different owners


def test_change_heuristic_never_picks_a_swept_deposit_address():
    from beans.engines import e1_cluster
    sweep_inputs = [("DEP", 0.01234567)] + [(f"d{i}", 0.1) for i in range(12)]
    f = _frames([("t0", 0, [("src", 2.0)], [("W", 1.0)]),
                 ("t1", 5, [("W", 1.0)], [("DEP", 0.01234567), ("NEXT", 0.9870)]),    # precise small output
                 ("t2", 60, sweep_inputs, [("COLD", 1.2)])])
    cl, _ = e1_cluster.cluster(f, _xtx(f), set())
    assert cl["W"] != cl["DEP"] and cl["W"] != cl["COLD"]


def test_hubs_absorb_taint():
    import networkx as nx
    from beans.engines import e4_propagate as e4
    G = nx.DiGraph()
    G.add_edge("SEED", "HUB", weight=1.0)
    for i in range(e4.HUB_DEGREE + 5):
        G.add_edge("HUB", f"cust{i}", weight=1.0)
    G.add_edge("SEED", "mule", weight=1.0)
    df, _ = e4.propagate(G, {"SEED"})
    assert df.loc["mule", "taint"] > 0.5 and df.loc["cust0", "taint"] == 0
