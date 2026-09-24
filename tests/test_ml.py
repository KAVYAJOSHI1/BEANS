"""Generator v2 + the four engines + fusion, end to end on a throwaway DB."""
import csv
import inspect
import json
import shutil

import pytest

from beans.config import settings
from beans.features import extractors
from beans.ingest.pipeline import ForensicPipeline
from beans.store.duck import DuckStore
from beans.synth.writer import SyntheticDatasetWriter


def test_generator_is_deterministic_and_utxo_consistent(tmp_root):
    a = SyntheticDatasetWriter.generate_dataset(tmp_root / "g1", n_tx=400, seed=5)
    b = SyntheticDatasetWriter.generate_dataset(tmp_root / "g2", n_tx=400, seed=5)
    assert a["csv_sha256"] == b["csv_sha256"]
    assert 0.02 <= a["illicit_wallet_share"] <= 0.12
    assert {"peel", "coinjoin", "fan_out", "fan_in", "round_trip"} <= set(a["tx_classes"])
    # every non-coinbase input must spend an output created earlier, and no output is spent twice
    created, spent = set(), set()
    rows = sorted(json.loads((tmp_root / "g1" / "transactions.json").read_text()), key=lambda r: r["timestamp"])
    seen = set()
    for r in rows:
        if r["txid"] in seen:
            continue
        seen.add(r["txid"])
        for addr, amt in zip(r["input_addresses"], r["input_amounts"]):
            assert (addr, amt) in created, "input spends an output that does not exist yet"
            assert (addr, amt, r["txid"]) not in spent
            spent.add((addr, amt, r["txid"]))
        created.update(zip(r["output_addresses"], r["output_amounts"]))


@pytest.fixture(scope="module")
def trained(dataset):
    store = DuckStore(settings.DB_PATH)
    result = ForensicPipeline(store).run_file_ingestion(dataset / "transactions.csv")
    return store, result


def test_pipeline_trains_scores_and_alerts(trained, dataset):
    store, result = trained
    assert result["pipeline_stats"]["trained"] is True
    assert set(result["sidecars_loaded"]) >= {"seeds.csv", "labels_address.csv", "labels_tx.csv"}
    conn = store.get_connection()
    alerts = conn.execute("SELECT entity_id, risk_score, calibrated_confidence, shap_top_features FROM alerts").fetchall()
    conn.close()
    assert alerts, "no alerts"
    truth = {r["address"]: r["is_illicit"] == "1" for r in csv.DictReader(open(dataset / "labels_address.csv"))}
    precision = sum(truth.get(a[0], False) for a in alerts) / len(alerts)
    assert precision >= 0.6, f"alert precision {precision:.2f}"
    assert all(0 <= a[1] <= 100 and 0 <= a[2] <= 1 for a in alerts)
    assert all(json.loads(a[3]) for a in alerts), "every alert must carry SHAP contributions"


def test_model_card_is_measured(trained):
    card = json.loads((settings.MODELS_DIR / "model_card.json").read_text())
    names = {m["metric"] for m in card["engine_metrics"]}
    assert any("PR-AUC" in n for n in names) and any("Macro F1" in n for n in names)
    assert all(0 <= m["score"] <= 1 for m in card["engine_metrics"])
    assert card["feature_importances"]


def test_no_label_leakage(trained):
    """Ground truth must never be read by feature code or appear as a model input."""
    src = inspect.getsource(extractors)
    assert "labels_" not in src.replace("labels_*", "")
    import joblib
    bundle = joblib.load(settings.MODELS_DIR / "fusion.joblib")
    forbidden = {"is_illicit", "typology", "entity_id", "tx_class"}
    assert not forbidden & set(bundle["features"])
    assert not any(f.startswith("label") for f in bundle["features"])


def test_inference_without_labels_uses_persisted_models(trained, dataset, tmp_root):
    """Operational data has no ground truth: the models trained above must be applied, not retrained."""
    d = tmp_root / "unlabelled"
    d.mkdir(exist_ok=True)
    shutil.copy(dataset / "transactions.csv", d / "transactions.csv")
    store = DuckStore(tmp_root / "unlabelled.duckdb")
    result = ForensicPipeline(store).run_file_ingestion(d / "transactions.csv")
    assert result["sidecars_loaded"] == []
    assert result["pipeline_stats"]["trained"] is False
    assert result["pipeline_stats"]["alerts_generated"] > 0


def test_analyst_feedback_retrains_on_unlabelled_data(trained, dataset, tmp_root):
    """S5: verdicts on operational (unlabelled) data are added to the saved training set and the model retrains."""
    store = DuckStore(tmp_root / "unlabelled.duckdb")
    conn = store.get_connection()
    top = conn.execute("SELECT entity_id FROM alerts ORDER BY risk_score DESC LIMIT 2").fetchall()
    low = conn.execute("SELECT address FROM wallet_profiles ORDER BY risk_score LIMIT 1").fetchone()[0]
    conn.execute("INSERT INTO feedback (id, alert_id, entity_id, user_label) VALUES (1, 'a', ?, 'FALSE_POSITIVE'), "
                 "(2, 'b', ?, 'TRUE_POSITIVE'), (3, 'c', ?, 'TRUE_POSITIVE')", [top[0][0], top[1][0], low])
    conn.close()
    stats = ForensicPipeline(store).execute_ml_pipeline()
    assert stats["trained"] is True
    report = json.loads((settings.MODELS_DIR / "training_report.json").read_text())
    assert report["fusion"]["analyst_feedback_used"] == 3
