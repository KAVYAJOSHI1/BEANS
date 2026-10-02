"""Review queue, global search, live monitor, case narratives (fact-checked), and summaries in case packs."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from beans.config import settings
from beans.explain import narrative


@pytest.fixture(scope="module")
def client(tmp_path_factory, dataset):
    settings.DB_PATH = tmp_path_factory.mktemp("db") / "features.duckdb"
    from beans.api.main import app
    from beans.ingest.pipeline import ForensicPipeline
    from beans.store.duck import DuckStore
    ForensicPipeline(DuckStore(settings.DB_PATH)).load_sidecars(dataset)
    c = TestClient(app)
    with open(dataset / "transactions.csv", "rb") as fh:
        assert c.post("/api/ingest/upload", files={"file": ("f.csv", fh, "text/csv")}).status_code == 200
    return c


def test_review_queue_and_verdicts(client):
    q = client.get("/api/review/queue?limit=50").json()
    assert q["alert_threshold"] == settings.ALERT_MIN_PROBABILITY and q["verdicts_so_far"] == 0
    u = [a["uncertainty"] for a in q["uncertain_alerts"]]
    assert u and u == sorted(u, reverse=True) and all(a["why_review"] for a in q["uncertain_alerts"])
    assert all(q["near_miss_min"] <= w["p"] < q["alert_threshold"] for w in q["near_misses"])
    top = q["uncertain_alerts"][0]
    r = client.post("/api/review/verdict", json={"entity_id": top["entity_id"], "label": "FALSE_POSITIVE"}).json()
    assert r["alert_id"] == top["alert_id"]
    assert client.get(f"/api/alerts/{top['alert_id']}").json()["status"] == "FALSE_POSITIVE"
    q2 = client.get("/api/review/queue?limit=50").json()
    assert q2["verdicts_so_far"] == 1 and top["alert_id"] not in {a["alert_id"] for a in q2["uncertain_alerts"]}
    if q["near_misses"]:   # a verdict on a wallet that never became an alert
        w = q["near_misses"][0]["address"]
        assert client.post("/api/review/verdict", json={"entity_id": w, "label": "TRUE_POSITIVE"}).json()["alert_id"] is None
    assert client.post("/api/review/verdict", json={"entity_id": "x", "label": "MAYBE"}).status_code == 422
    assert client.post("/api/review/verdict", json={"entity_id": "not-a-wallet", "label": "TRUE_POSITIVE"}).status_code == 404


def test_search(client):
    a = client.get("/api/alerts?limit=1").json()[0]
    r = client.get(f"/api/search?q={a['entity_id'][:10]}").json()
    assert any(w["id"] == a["entity_id"] for w in r["wallets"])
    tx = a["evidence"]["txid"]
    assert client.get(f"/api/search?q={tx[:12]}").json()["transactions"][0]["id"] == tx
    assert client.get(f"/api/search?q={a['alert_id']}").json()["alerts"][0]["id"] == a["alert_id"]
    cl = client.get(f"/api/search?q={a['evidence']['cluster_id'][:6]}").json()["clusters"]
    assert cl and cl[0]["top_wallet"]
    assert client.get("/api/search?q=a").status_code == 422      # at least 2 characters


def test_live_status_reads_process_heartbeats(client, tmp_path):
    settings.LIVE_INBOX = tmp_path
    try:
        s = client.get("/api/live/status").json()
        assert s["collector"] is None and s["watcher"] is None and s["transactions"] > 0
        (tmp_path / "waiting.csv").write_text("x")
        (tmp_path / "collector.status").write_text(json.dumps({"running": True, "updated_at": time.time(), "peers": 7, "tx": 10}))
        (tmp_path / "watch.status").write_text(json.dumps({"updated_at": time.time() - 300, "files_done": 3}))
        s = client.get("/api/live/status").json()
        assert s["collector"]["alive"] and s["collector"]["peers"] == 7
        assert not s["watcher"]["alive"] and s["watcher"]["age_s"] >= 299          # stale heartbeat
        assert s["files_waiting"] == ["waiting.csv"] and s["recent_files"] and s["recent_alerts"]
    finally:
        settings.LIVE_INBOX = None


def test_narrative_fact_check():
    sheet = ["Wallet abc has risk 97 of 100 (CRITICAL).", "4.5 BTC reached exchange VASP-A in 2 hop(s).",
             "The funds pass through a peel chain of 9 transactions."]
    good = "Wallet abc has a risk of 97 out of 100 [F1]. It sent 4.5 BTC to exchange VASP-A in 2 hops [F2]."
    kept, dropped = narrative.check(good, sheet)
    assert dropped == 0 and [k["facts"] for k in kept] == [[1], [2]]
    bad = ("Wallet abc sent 7.5 BTC to exchange VASP-A [F2]. "          # number not in the cited fact
           "The owner probably laundered the funds [F3]. "               # speculation
           "The funds went to exchange VASP-A in 2 hops [F3]. "          # wrong citation
           "The funds pass through a peel chain [F9]. "                  # fact does not exist
           "The wallet is dangerous.")                                    # no citation
    assert narrative.check(bad, sheet) == ([], 5)


def test_narrative_generate_falls_back_to_template(client):
    alert = client.get("/api/alerts?limit=1").json()[0]
    sheet = narrative.facts(alert)
    ok = narrative.generate(alert, llm=lambda p: f"{sheet[0]} [F1] {sheet[1]} [F2]")
    assert ok["engine"] == "test model" and len(ok["sentences"]) == 2
    junk = narrative.generate(alert, llm=lambda p: "The owner probably did it [F1]. Nothing else.")
    assert junk["engine"] == "template" and "fact check" in junk["note"] and len(junk["sentences"]) == len(sheet)
    def down(p):
        raise ConnectionRefusedError()
    off = narrative.generate(alert, llm=down)
    assert off["engine"] == "template" and "unavailable" in off["note"]


def test_narrative_endpoints_and_case_pack(client):
    a = client.get("/api/alerts?limit=1").json()[0]
    assert client.get(f"/api/alerts/{a['alert_id']}/narrative").json()["cached"] is False
    n = client.post(f"/api/alerts/{a['alert_id']}/narrative?engine=template").json()
    assert n["engine"] == "template" and n["cached"]
    assert client.get(f"/api/alerts/{a['alert_id']}/narrative").json()["facts_sha256"] == n["facts_sha256"]
    case = client.post("/api/cases", json={"case_name": "narrative case", "suspect_entities": [a["entity_id"]]}).json()
    cid = case.get("case_id", case.get("id"))
    pack = client.get(f"/api/cases/{cid}/export?fmt=json").json()
    f = next(x for x in pack["evidence"]["findings"] if x["alert_id"] == a["alert_id"])
    assert f["case_summary"]["engine"] == "template" and "[F1]" in f["case_summary"]["text"]
    assert "Case summary" in client.get(f"/api/cases/{cid}/export?fmt=md").text


def test_every_ingest_path_logs_the_file(client, dataset, tmp_path):
    """API uploads, `beans ingest` and `beans watch` all record the file and its SHA-256 (case-pack sources)."""
    import hashlib
    import shutil
    from beans.api import db
    from beans.ingest.pipeline import ForensicPipeline
    f = tmp_path / "cli_copy.csv"
    shutil.copy(dataset / "transactions.csv", f)
    p = ForensicPipeline()
    p.execute_ml_pipeline = lambda *a: {"skipped": True}
    p.run_file_ingestion(f, "WATCH")
    rows = {r["file"]: r for r in db.query("SELECT file, sha256, source FROM ingest_log")}
    assert any(k.endswith("f.csv") and r["source"] == "UPLOAD" for k, r in rows.items())   # the fixture's API upload
    assert rows["cli_copy.csv"] == {"file": "cli_copy.csv", "sha256": hashlib.sha256(f.read_bytes()).hexdigest(), "source": "WATCH"}


def test_single_transaction_database_has_numeric_features():
    """A tiny live file (one transaction, no peel chain) must still give a purely numeric matrix: the persisted model rejects object columns."""
    import pandas as pd
    from beans.features.extractors import Frames, tx_features
    ts = pd.Timestamp("2026-09-01 10:00")
    f = Frames(pd.DataFrame([{"txid": "t", "ts": ts, "fee": 0.0001, "script_type": "P2WPKH"}]),
               pd.DataFrame([{"txid": "t", "ts": ts, "address": "a", "amount": 1.0}]),
               pd.DataFrame([{"txid": "t", "ts": ts, "idx": 0, "address": "b", "amount": 0.9}]),
               pd.DataFrame([{"txid": "t", "spy_ip": "1.2.3.4", "spy_port": 8333, "spy_country": "US", "spy_asn": "AS1",
                              "spy_asn_type": "RESIDENTIAL", "n_obs": 1, "spy_delta": float("nan")}]))
    X = tx_features(f)
    assert all(pd.api.types.is_numeric_dtype(t) for t in X.dtypes), X.dtypes[~X.dtypes.map(pd.api.types.is_numeric_dtype)]
