"""Ingestion, enrichment and report tests."""
from beans.enrich.geoip import OfflineGeoIPEnricher
from beans.ingest.csv_parser import StreamingCSVParser
from beans.ingest.json_parser import StreamingJSONParser
from beans.ingest.xml_parser import StreamingXMLParser
from beans.report.pdf_export import CaseReportGenerator


def test_multi_format_ingestion_equality(dataset):
    """R1: CSV, JSON and XML versions of the same dataset parse to identical records."""
    csv_recs = list(StreamingCSVParser().parse(dataset / "transactions.csv"))
    json_recs = list(StreamingJSONParser().parse(dataset / "transactions.json"))
    xml_recs = list(StreamingXMLParser().parse(dataset / "transactions.xml"))
    assert len(csv_recs) == len(json_recs) == len(xml_recs) > 100
    for a, b, c in zip(csv_recs[:50], json_recs[:50], xml_recs[:50]):
        assert a.txid == b.txid == c.txid and a.output_amounts == b.output_amounts == c.output_amounts


def test_offline_enrichment_uses_real_asn_and_types():
    """R3: offline DB-IP country + ASN, infrastructure type from the intel snapshots."""
    e = OfflineGeoIPEnricher()
    tor = e.enrich("185.220.101.4")
    assert tor["country"] == "DE" and tor["asn"] == "AS60729" and tor["asn_type"] == "TOR_EXIT"
    aws = e.enrich("3.5.140.2")
    assert aws["asn"] == "AS16509" and aws["asn_type"] == "DATACENTER"
    jio = e.enrich("49.36.12.7")
    assert jio["country"] == "IN" and jio["asn_type"] == "RESIDENTIAL"
    assert e.enrich("not-an-ip")["asn_type"] == "UNKNOWN"


def test_case_evidence_pack_export():
    """S3: evidence pack carries source-file hashes and a verifiable evidence SHA-256"""
    alert = {"alert_id": "ALT-1", "entity_type": "WALLET", "entity_id": "bc1qSuspect1", "alert_type": "RANSOMWARE",
             "severity": "CRITICAL", "risk_score": 92.0, "calibrated_confidence": 0.90, "status": "OPEN",
             "reasons": ["Ransomware collection pattern"], "engine_scores": {}, "evidence": {"txid": "ab" * 32},
             "shap_top_features": [{"feature": "taint", "value": 0.6, "impact": 0.32}]}
    case = {"id": 1, "case_name": "Test Case", "incident_type": "RANSOMWARE", "status": "OPEN", "notes": "n"}
    pack = CaseReportGenerator.build(case, [alert], [{"file": "tx.csv", "sha256": "f" * 64, "records": 10}], [])
    assert len(pack["evidence_sha256"]) == 64
    assert "f" * 64 in pack["markdown"] and "bc1qSuspect1" in pack["html"]
