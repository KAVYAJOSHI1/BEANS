"""Continuous ingestion worker (beans serve --watch / beans live) and the collector's clean stop."""
import json
import os
import shutil
import socket
import threading
import time

import pytest

from beans.config import settings
from beans.ingest.worker import IngestWorker


@pytest.fixture()
def worker_db(tmp_path, dataset):
    settings.DB_PATH = tmp_path / "worker.duckdb"
    from beans.ingest.pipeline import ForensicPipeline
    from beans.store.duck import DuckStore
    ForensicPipeline(DuckStore(settings.DB_PATH)).load_sidecars(dataset)   # labels: scoring trains a model
    return tmp_path


def _split(dataset, inbox, parts=3):
    """The fixture dataset as several files (whole transactions per file)."""
    lines = (dataset / "transactions.csv").read_text().splitlines()
    head, rows = lines[0], lines[1:]
    k = len(rows) // parts
    names = []
    for i in range(parts):
        f = inbox / f"part{i}.csv"
        f.write_text("\n".join([head] + rows[i * k:(i + 1) * k if i < parts - 1 else None]) + "\n")
        os.utime(f, (time.time() - 60, time.time() - 60))   # finished writing a minute ago
        names.append(f.name)
    return names


def test_batches_load_everything_then_score_once(worker_db, dataset):
    inbox = worker_db / "inbox"
    inbox.mkdir()
    _split(dataset, inbox, 2)
    (inbox / "broken.xml").write_text("<not xml")
    os.utime(inbox / "broken.xml", (time.time() - 60, time.time() - 60))
    runs = []
    w = IngestWorker(inbox, interval=0.1, score_every=3600, log=lambda m: None)
    real = w.score
    w.score = lambda: runs.append(1) or real()
    w.step()
    assert w.state["files_done"] == 2 and w.state["files_failed"] == 1 and runs == [1]      # one scoring for the batch
    assert sorted(p.name.split("_", 2)[-1] for p in (inbox / "processed").iterdir()) == ["part0.csv", "part1.csv"]
    assert [p.name.split("_", 2)[-1] for p in (inbox / "failed").iterdir()] == ["broken.xml"]
    # a file arriving right after a scoring run is loaded now and scored at the next allowed time
    shutil.copy(dataset / "transactions.csv", inbox / "late.csv")
    os.utime(inbox / "late.csv", (time.time() - 60, time.time() - 60))
    w.step()
    assert w.state["files_done"] == 3 and runs == [1] and w.unscored_rows > 0
    w.last_score -= 3600
    w.step()
    assert runs == [1, 1] and w.unscored_rows == 0
    st = json.loads((inbox / "watch.status").read_text())
    assert st["mode"] == "in-process" and st["scoring_runs"] == 2 and st["files_failed"] == 1 and not st["scoring"]
    from beans.api import db
    assert {r["source"] for r in db.query("SELECT source FROM ingest_log")} == {"WATCH"}


def test_file_still_being_written_waits(worker_db):
    inbox = worker_db / "inbox"
    inbox.mkdir()
    f = inbox / "growing.csv"
    f.write_text("timestamp,txid\n")          # fresh file: wait until its size is stable over one scan
    w = IngestWorker(inbox, interval=10, log=lambda m: None)
    assert w.ready_files() == []
    f.write_text("timestamp,txid\n1,a\n")      # still growing
    assert w.ready_files() == []
    assert w.ready_files() == [f]              # unchanged since the last scan


def test_dashboard_reads_and_writes_while_the_worker_scores(worker_db, dataset):
    """The reason the worker runs inside the server process: API calls keep working during scoring."""
    inbox = worker_db / "inbox"
    inbox.mkdir()
    _split(dataset, inbox, 1)
    w = IngestWorker(inbox, interval=0.1, score_every=3600, log=lambda m: None)
    w.load(w.ready_files() or [inbox / "part0.csv"])
    from beans.api import db
    t = threading.Thread(target=w.score)
    t.start()
    ok, errors = 0, []
    while t.is_alive():
        try:
            db.query("SELECT COUNT(*) AS n FROM transactions")
            db.audit("TEST", "WORKER", "x", investigator="test")
            ok += 1
        except Exception as e:   # pragma: no cover - the failure this test guards against
            errors.append(repr(e))
        time.sleep(0.05)
    t.join()
    assert ok > 0 and errors == [] and w.state["scoring_runs"] == 1


def test_collector_halts_from_another_thread(tmp_path):
    import asyncio
    from beans.collector.p2p import Collector
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()                                # accepts, then never answers: the peer task would wait 120 s
    c = Collector(tmp_path)
    t = threading.Thread(target=lambda: asyncio.run(c.run([("127.0.0.1", srv.getsockname()[1])], None, log=lambda m: None)))
    t.start()
    time.sleep(1)
    c.halt()
    t.join(timeout=15)
    srv.close()
    assert not t.is_alive()
    st = json.loads((tmp_path / "collector.status").read_text())
    assert st["running"] is False


def test_corrupt_or_truncated_files_are_refused(tmp_path):
    """A file cut off in transfer (e.g. across a data diode) must fail loudly, not load as 'fine, 0 rows'."""
    from beans.ingest.json_parser import StreamingJSONParser
    from beans.ingest.mapping import ColumnMapper
    from beans.ingest.xml_parser import StreamingXMLParser
    (tmp_path / "cut.json").write_text('[{"txid": "a", "timest')
    (tmp_path / "cut.xml").write_text('<transactions><tx txid="a" timestamp="2026-01-01T00:00:00Z"><src_ip>1.2.3.4</src_ip>')
    with pytest.raises(ValueError, match="corrupt or truncated"):
        list(StreamingJSONParser(ColumnMapper()).parse(tmp_path / "cut.json"))
    with pytest.raises(ValueError, match="corrupt or truncated"):
        list(StreamingXMLParser().parse(tmp_path / "cut.xml"))
