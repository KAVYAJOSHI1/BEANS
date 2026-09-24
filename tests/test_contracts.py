"""Shared-contract smoke tests. Must stay green on every branch."""
import json
from pathlib import Path

from beans.schema import Alert, RawRecord
from beans.store.db import DATA_TABLES, SCORE_TABLES, connect

ROOT = Path(__file__).resolve().parent.parent


def test_ddl_creates_all_tables():
    con = connect(":memory:")
    names = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    for t in DATA_TABLES + SCORE_TABLES + ["alert_status", "case_file", "case_alert", "audit_log"]:
        assert t in names, t


def test_mock_alerts_match_contract():
    for a in json.loads((ROOT / "data/samples/mock_alerts.json").read_text()):
        Alert.model_validate(a)


def test_sample_json_records_valid():
    for r in json.loads((ROOT / "data/samples/sample.json").read_text()):
        RawRecord.model_validate(r)


def test_cli_loads():
    from beans.cli import app
    assert app is not None
