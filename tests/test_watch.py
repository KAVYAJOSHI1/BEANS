"""Watchlist: watched wallets that spend raise one movement event, traced to exchanges and pushed to webhooks."""
import csv
import hashlib
import json
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import duckdb
import pytest
from fastapi.testclient import TestClient


class _Sink(BaseHTTPRequestHandler):
    bodies: list = []

    def do_POST(self):
        _Sink.bodies.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def client(tmp_path_factory, dataset):
    from beans.config import settings
    settings.DB_PATH = tmp_path_factory.mktemp("db") / "watch.duckdb"
    from beans.api.main import app
    from beans.ingest.pipeline import ForensicPipeline
    from beans.store.duck import DuckStore
    ForensicPipeline(DuckStore(settings.DB_PATH)).load_sidecars(dataset)
    c = TestClient(app)
    with open(dataset / "transactions.csv", "rb") as fh:
        assert c.post("/api/ingest/upload", files={"file": ("base.csv", fh, "text/csv")}).status_code == 200
    return c


def _spend_file(tmp_path, wallet, amount, to_addr, when):
    txid = hashlib.sha256(f"{wallet}{to_addr}{when}".encode()).hexdigest()
    p = tmp_path / "later.csv"
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp", "src_ip", "src_port", "dst_ip", "dst_port", "txid", "input_addresses", "input_amounts",
                    "output_addresses", "output_amounts", "fee", "script_type"])
        w.writerow([when.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "185.220.101.5", 51234, "10.0.0.1", 8333, txid, wallet,
                    f"{amount:.8f}", to_addr, f"{amount - 0.0002:.8f}", "0.0002", "P2WPKH"])
    return p, txid


def test_taint_watch_wallets_are_watched_automatically(client):
    watched = client.get("/api/watchlist").json()
    monitor = client.get("/api/alerts?action=PASSIVE_TAINT_MONITOR&limit=1000").json()
    assert monitor, "fixture produced no taint-watch directive; the test would be vacuous"
    assert {a["entity_id"] for a in monitor} <= {w["address"] for w in watched}
    assert all(w["reason"] == "AUTO_TAINT_WATCH" and w["watched_from"] for w in watched)


def test_movement_to_exchange_raises_one_event_and_webhook(client, tmp_path):
    from beans.alerting import webhooks
    from beans.config import settings
    srv = HTTPServer(("127.0.0.1", 0), _Sink)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    hook = client.post("/api/webhooks", json={"url": f"http://127.0.0.1:{srv.server_port}/", "fmt": "json",
                                              "min_severity": "CRITICAL"}).json()
    client.post("/api/webhooks/dispatch")                     # flush the base run's alerts
    _Sink.bodies.clear()

    con = duckdb.connect(str(settings.DB_PATH))
    wallet, balance = con.execute("""SELECT address, balance FROM wallet_profiles WHERE balance > 0.001
        AND address NOT IN (SELECT address FROM known_entities) ORDER BY balance DESC LIMIT 1""").fetchone()
    vasp_addr, vasp = con.execute("SELECT address, entity_name FROM known_entities WHERE entity_type = 'VASP' "
                                  "AND in_jurisdiction LIMIT 1").fetchone()
    last = con.execute("SELECT max(timestamp) FROM transactions").fetchone()[0]
    con.close()
    assert client.post("/api/watchlist", json={"address": wallet, "note": "test"}).json()["added"] in (True, False)
    assert client.post("/api/watchlist", json={"address": "bc1qnotthere"}).status_code == 404

    path, txid = _spend_file(tmp_path, wallet, balance, vasp_addr, last + timedelta(minutes=20))
    with open(path, "rb") as fh:
        r = client.post("/api/ingest/upload", files={"file": ("later.csv", fh, "text/csv")})
    assert r.status_code == 200 and r.json()["pipeline_stats"]["watch_events"] >= 1

    ev = next(e for e in client.get("/api/watch-events").json() if e["txid"] == txid)
    assert ev["address"] == wallet and ev["vasp"] == vasp and ev["vasp_in_jurisdiction"]
    assert ev["recommended"] == "IMMEDIATE_FREEZE_DRAFT" and ev["minutes_since_move"] == 0.0
    assert abs(ev["amount_btc"] - balance) < 1e-6 and ev["destinations"][0]["address"] == vasp_addr

    webhooks.dispatch_pending(__import__("beans.store.duck", fromlist=["DuckStore"]).DuckStore())
    sent = [a for b in _Sink.bodies for a in b["alerts"] if a["alert_id"] == ev["event_id"]]
    assert len(sent) == 1 and sent[0]["typology"] == "WATCHED_FUNDS_MOVED" and sent[0]["severity"] == "CRITICAL"

    # rescoring never duplicates the event or the delivery
    client.post("/api/seeds/repropagate")
    assert sum(e["txid"] == txid for e in client.get("/api/watch-events").json()) == 1
    _Sink.bodies.clear()
    webhooks.dispatch_pending(__import__("beans.store.duck", fromlist=["DuckStore"]).DuckStore())
    assert not [a for b in _Sink.bodies for a in b["alerts"] if a["alert_id"] == ev["event_id"]]

    assert client.patch(f"/api/watch-events/{ev['event_id']}", json={"status": "ACKNOWLEDGED"}).status_code == 200
    assert client.patch(f"/api/watch-events/{ev['event_id']}", json={"status": "NOPE"}).status_code == 422
    assert client.get("/api/stats/overview").json()["kpis"]["watched_wallets"] >= 1
    client.delete(f"/api/webhooks/{hook['id']}")
    srv.shutdown()


def test_unwatch_and_case_watch(client):
    w = client.get("/api/watchlist").json()[0]["address"]
    assert client.delete(f"/api/watchlist/{w}").status_code == 200
    assert client.delete(f"/api/watchlist/{w}").status_code == 404
    case = client.post("/api/cases", json={"case_name": "watch me", "suspect_entities": [w]}).json()
    assert client.post(f"/api/cases/{case['case_id']}/watch").json()["watched"] == 1
    assert any(x["address"] == w and x["reason"] == "CASE" for x in client.get("/api/watchlist").json())
