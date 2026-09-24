"""API smoke tests on a throwaway DuckDB (Kavya)."""
import pytest
from fastapi.testclient import TestClient

from beans.config import settings

@pytest.fixture(scope="module")
def client(tmp_path_factory, dataset):
    settings.DB_PATH = tmp_path_factory.mktemp("db") / "api_test.duckdb"
    from beans.api.main import app
    from beans.ingest.pipeline import ForensicPipeline
    from beans.store.duck import DuckStore
    ForensicPipeline(DuckStore(settings.DB_PATH)).load_sidecars(dataset)   # ground truth + seeds for training
    c = TestClient(app)
    with open(dataset / "transactions.csv", "rb") as fh:
        r = c.post("/api/ingest/upload", files={"file": ("fixture.csv", fh, "text/csv")})
    assert r.status_code == 200, r.text
    return c


def test_read_endpoints(client):
    for path in ["/api/health", "/api/stats/overview", "/api/alerts", "/api/graph/topology", "/api/timeline/sequence",
                 "/api/geomap/origins", "/api/cases", "/api/modelcard", "/api/seeds", "/api/audit"]:
        assert client.get(path).status_code == 200, path


def test_alerts_have_native_types(client):
    alerts = client.get("/api/alerts").json()
    assert alerts, "pipeline produced no alerts on the fixture"
    a = alerts[0]
    assert isinstance(a["reasons"], list) and isinstance(a["evidence"], dict)
    assert client.get(f"/api/entity/wallet/{a['entity_id']}").status_code == 200


def test_status_case_and_export(client):
    a = client.get("/api/alerts").json()[0]
    assert client.patch(f"/api/alerts/{a['alert_id']}/status", json={"status": "NOPE"}).status_code == 422
    assert client.patch(f"/api/alerts/{a['alert_id']}/status", json={"status": "CONFIRMED"}).status_code == 200
    case = client.post("/api/cases", json={"case_name": "t", "suspect_entities": [a["entity_id"]]}).json()
    pack = client.get(f"/api/cases/{case['case_id']}/export").json()
    assert len(pack["evidence"]["findings"]) == 1 and len(pack["evidence_sha256"]) == 64
    assert client.get("/api/cases/9999/export").status_code == 404


def test_upload_rejects_bad_type(client):
    r = client.post("/api/ingest/upload", files={"file": ("../evil.sh", b"x", "text/plain")})
    assert r.status_code == 422


def test_model_card_never_invents_numbers(client):
    card = client.get("/api/modelcard").json()
    assert card["status"] in {"evaluated", "not_evaluated"}
    if card["status"] == "not_evaluated":
        assert card["engine_metrics"] == []


def test_model_card_evaluation_measures_real_metrics(client, dataset):
    r = client.post("/api/modelcard/evaluate")
    assert r.status_code == 200, r.text
    card = r.json()
    assert card["status"] == "evaluated" and card["engine_metrics"]
    assert all(0.0 <= m["score"] <= 1.0 for m in card["engine_metrics"])
    assert client.get("/api/modelcard").json()["status"] == "evaluated"


def test_upload_with_column_mapping(client, dataset):
    """An export with foreign column names ingests through the API when a mapping YAML is attached."""
    import csv as _csv
    import io
    rows = list(_csv.DictReader(open(dataset / "transactions.csv")))[:50]
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["time", "tx_hash", "peer", "vin", "vin_amt", "vout", "vout_amt"])
    for r in rows:
        w.writerow([r["timestamp"], r["txid"], r["src_ip"], r["input_addresses"], r["input_amounts"],
                    r["output_addresses"], r["output_amounts"]])
    mapping = b"peer: src_ip\nvin_amt: input_amounts\nvout_amt: output_amounts\nvin: input_addresses\nvout: output_addresses\n"
    r = client.post("/api/ingest/upload", files={"file": ("export.csv", buf.getvalue().encode(), "text/csv"),
                                                  "mapping": ("m.yaml", mapping, "application/x-yaml")})
    assert r.status_code == 200, r.text
    assert r.json()["records_ingested"] == 50 and r.json()["rows_quarantined"] == 0
