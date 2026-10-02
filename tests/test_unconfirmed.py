"""Unconfirmed-first monitoring: spends by watched wallets and seeds are reported when the file is loaded, before
scoring, marked unconfirmed, and are never a freeze trigger."""
import csv
import hashlib
from datetime import timedelta

import duckdb

from beans.alerting import watch
from beans.config import settings
from beans.ingest.worker import IngestWorker
from tests.test_watch import client  # noqa: F401 (fixture)


def _file(path, wallet, amount, to_addr, when, confirmed):
    txid = hashlib.sha256(f"{wallet}{to_addr}{when}{confirmed}".encode()).hexdigest()
    cols = ["timestamp", "src_ip", "src_port", "dst_ip", "dst_port", "txid", "input_addresses", "input_amounts",
            "output_addresses", "output_amounts", "fee", "script_type"] + (["confirmed"] if confirmed is not None else [])
    row = [when.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "185.220.101.5", 51234, "10.0.0.1", 8333, txid, wallet,
           f"{amount:.8f}", to_addr, f"{amount - 0.0002:.8f}", "0.0002", "P2WPKH"] + ([int(confirmed)] if confirmed is not None else [])
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        w.writerow(row)
    return txid


def _events(where="1=1"):
    con = duckdb.connect(str(settings.DB_PATH))
    try:
        cur = con.execute(f"SELECT * FROM watch_events WHERE {where} ORDER BY ts")
        return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    finally:
        con.close()


def _pick():
    con = duckdb.connect(str(settings.DB_PATH))
    try:
        wallet, balance = con.execute("""SELECT address, balance FROM wallet_profiles WHERE balance > 0.001
            AND address NOT IN (SELECT address FROM known_entities) ORDER BY balance DESC OFFSET 1 LIMIT 1""").fetchone()
        vasp_addr = con.execute("SELECT address FROM known_entities WHERE entity_type = 'VASP' AND in_jurisdiction LIMIT 1").fetchone()[0]
        last = con.execute("SELECT max(timestamp) FROM transactions").fetchone()[0]
        seed = con.execute("SELECT address FROM seeds LIMIT 1").fetchone()[0]
    finally:
        con.close()
    return wallet, balance, vasp_addr, last, seed


def test_unconfirmed_spend_is_reported_at_load_time_and_never_a_freeze(client, tmp_path):
    wallet, balance, vasp_addr, last, _ = _pick()
    assert client.post("/api/watchlist", json={"address": wallet, "note": "unconfirmed test"}).status_code == 200
    f = tmp_path / "mempool_1.csv"
    txid = _file(f, wallet, balance, vasp_addr, last + timedelta(minutes=30), confirmed=False)
    w = IngestWorker(tmp_path, log=lambda m: None)
    since = w._db_now()
    w.load([f])
    assert w.quick_watch(since) == 1                       # reported before any scoring run
    ev = _events(f"txid = '{txid}'")[0]
    assert ev["confirmed"] is False and ev["detected_via"] == "QUICK" and ev["recommended"] == "UNCONFIRMED_MOVEMENT"
    assert ev["vasp"] is None                              # no trace yet: that comes with scoring
    alert = watch.as_alert(ev)
    assert "UNCONFIRMED" in alert["reasons"][0] and "no freeze" in alert["recommended_action"]["rule"]
    assert w.quick_watch(since) == 0                       # idempotent: one event per (wallet, transaction)

    from beans.ingest.pipeline import ForensicPipeline
    ForensicPipeline().execute_ml_pipeline()               # scoring enriches the event with the exchange trace
    ev = _events(f"txid = '{txid}'")[0]
    assert ev["vasp"] and ev["recommended"] == "UNCONFIRMED_MOVEMENT"   # reached an exchange on paper, still no freeze
    assert len(_events(f"txid = '{txid}'")) == 1


def test_unknown_confirmation_keeps_the_old_behaviour(client, tmp_path):
    wallet, balance, vasp_addr, last, _ = _pick()
    con = duckdb.connect(str(settings.DB_PATH))
    last = con.execute("SELECT max(timestamp) FROM transactions").fetchone()[0]
    con.close()
    client.post("/api/watchlist", json={"address": wallet, "note": "historic"})
    f = tmp_path / "hist.csv"
    txid = _file(f, wallet, balance / 2, vasp_addr, last + timedelta(minutes=60), confirmed=None)
    w = IngestWorker(tmp_path, log=lambda m: None)
    since = w._db_now()
    w.load([f])
    w.quick_watch(since)
    ev = _events(f"txid = '{txid}'")[0]
    assert ev["confirmed"] is True and ev["recommended"] == "TRACE_AND_REVIEW"


def test_seed_wallet_spending_is_reported_even_when_not_watched(client, tmp_path):
    _, _, vasp_addr, last, seed = _pick()
    f = tmp_path / "seed.csv"
    txid = _file(f, seed, 0.01, vasp_addr, last + timedelta(minutes=90), confirmed=False)
    w = IngestWorker(tmp_path, log=lambda m: None)
    since = w._db_now()
    w.load([f])
    assert w.quick_watch(since) >= 1
    ev = _events(f"txid = '{txid}'")[0]
    assert ev["watch_reason"] == "SEED" and ev["recommended"] == "UNCONFIRMED_MOVEMENT"
    assert any(e["event_id"] == ev["event_id"] for e in client.get("/api/watch-events").json())


def test_old_files_are_not_reported_by_the_fast_path(client, tmp_path):
    """`since` limits the fast path to what was just loaded: earlier events and rows are not re-reported."""
    con = duckdb.connect(str(settings.DB_PATH))
    try:
        now = watch.db_now(con)
    finally:
        con.close()
    assert watch.quick_check(duckdb.connect(str(settings.DB_PATH)), now + timedelta(days=1)) == []
