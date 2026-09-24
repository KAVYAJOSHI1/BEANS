import pytest
from pathlib import Path
from datetime import datetime
from beans.schema import CanonicalRecord
from beans.ingest.csv_parser import StreamingCSVParser
from beans.ingest.json_parser import StreamingJSONParser
from beans.ingest.xml_parser import StreamingXMLParser
from beans.enrich.geoip import OfflineGeoIPEnricher
from beans.enrich.asn_classifier import ASNClassifier
from beans.synth.writer import SyntheticDatasetWriter
from beans.engines.e1_cluster import EntityClusteringEngine
from beans.engines.e2_anomaly import AnomalyDetectionEngine
from beans.engines.e3_peelmix import PeelingAndMixingClassifier
from beans.engines.e4_propagate import RiskPropagationEngine
from beans.score.fuse import MetaFusionEngine
from beans.explain.reasons import PlainEnglishReasonGenerator
from beans.report.pdf_export import LawEnforcementReportGenerator

@pytest.fixture
def sample_records():
    demo_dir = Path("data/synth/test_fixture")
    SyntheticDatasetWriter.generate_dataset(demo_dir, n_tx=30)
    parser = StreamingCSVParser()
    records = list(parser.parse(demo_dir / "transactions.csv"))
    return records

def test_multi_format_ingestion_equality():
    """R1: Verify identical record counts across CSV, JSON, and XML"""
    demo_dir = Path("data/synth/test_fixture")
    SyntheticDatasetWriter.generate_dataset(demo_dir, n_tx=50)

    csv_recs = list(StreamingCSVParser().parse(demo_dir / "transactions.csv"))
    json_recs = list(StreamingJSONParser().parse(demo_dir / "transactions.json"))
    xml_recs = list(StreamingXMLParser().parse(demo_dir / "transactions.xml"))

    assert len(csv_recs) == len(json_recs) == len(xml_recs) == 50
    assert csv_recs[0].txid == json_recs[0].txid == xml_recs[0].txid

def test_offline_enrichment():
    """R3: Verify offline GeoIP and ASN enrichment"""
    enricher = OfflineGeoIPEnricher()
    res = enricher.enrich("185.220.101.42")
    assert res["country"] == "NL"
    assert res["asn"] == "AS9009"
    assert ASNClassifier.classify(res["asn"]) == "BULLETPROOF"

def test_e1_clustering_cioh(sample_records):
    """E1: Verify Common Input Ownership Heuristic (CIOH) clustering"""
    cluster_map = EntityClusteringEngine.compute_clusters(sample_records)
    assert len(cluster_map) > 0
    # Every address should map to a cluster ID
    for r in sample_records:
        for addr in r.input_addresses + r.output_addresses:
            assert addr in cluster_map

def test_e2_anomaly_detection(sample_records):
    """E2: Verify Isolation Forest produces normalized anomaly scores"""
    e2 = AnomalyDetectionEngine()
    scores = e2.fit_predict(sample_records)
    assert len(scores) == len(sample_records)
    for txid, s in scores.items():
        assert 0.0 <= s <= 1.0

def test_e3_peeling_mixing_classifier(sample_records):
    """E3: Verify Typology classifier identifies peel chains and coinjoin"""
    e3 = PeelingAndMixingClassifier()
    preds = e3.predict_probabilities(sample_records)
    assert len(preds) == len(sample_records)
    typologies = {p["predicted_typology"] for p in preds.values()}
    assert len(typologies) >= 2

def test_e4_risk_propagation(sample_records):
    """E4: Verify Personalized PageRank and Decayed Taint from seeds"""
    seeds = {sample_records[0].input_addresses[0]} if sample_records[0].input_addresses else set()
    ppr, taint, paths = RiskPropagationEngine.compute_ppr_and_taint(sample_records, seeds)
    assert len(ppr) > 0
    assert len(taint) > 0

def test_meta_fusion_and_reasons():
    """R6: Verify composite risk score, calibrated confidence and plain-English reasons"""
    score, conf, sev, comp = MetaFusionEngine.fuse_entity_score(
        address="bc1qTestSuspectWallet999",
        cluster_id="CLUST_8812",
        e2_anomaly=0.88,
        e3_typology="RANSOMWARE",
        e3_conf=0.95,
        e4_ppr=0.75,
        e4_taint=0.60,
        network_meta={"asn_type": "BULLETPROOF", "geo_country": "NL", "has_impossible_travel": True, "travel_speed_kmh": 1420}
    )
    assert score >= 85.0
    assert sev == "CRITICAL"
    assert 0.80 <= conf <= 1.0

    reasons = PlainEnglishReasonGenerator.generate_reasons(
        typology="RANSOMWARE",
        typology_conf=0.95,
        taint_pct=0.60,
        path_to_seed=["bc1qSeed", "bc1qTestSuspectWallet999"],
        network_meta={"asn_type": "BULLETPROOF", "geo_country": "NL", "has_impossible_travel": True, "travel_speed_kmh": 1420},
        anomaly_score=0.88
    )
    assert len(reasons) >= 3

def test_law_enforcement_dossier_export():
    """S3: Verify court-admissible LE dossier generation with SHA-256 hash"""
    dossier = LawEnforcementReportGenerator.generate_case_dossier(
        case_id=1,
        case_name="Operation Test Case",
        incident_type="RANSOMWARE",
        suspect_wallets=["bc1qSuspect1", "bc1qSuspect2"],
        investigator="Special Agent Analyst",
        notes="Suspect syndicate identified.",
        alerts=[{
            "entity_id": "bc1qSuspect1",
            "risk_score": 92.0,
            "calibrated_confidence": 0.90,
            "alert_type": "RANSOMWARE",
            "severity": "CRITICAL",
            "reasons": ["Ransomware collection pattern"],
            "shap_top_features": [{"feature": "is_bulletproof", "value": 1.0, "impact": "+0.32"}]
        }],
        dataset_sha256="TEST_SHA256_HASH_12345"
    )
    assert "LAW ENFORCEMENT" in dossier["markdown"]
    assert "TEST_SHA256_HASH_12345" in dossier["markdown"]
