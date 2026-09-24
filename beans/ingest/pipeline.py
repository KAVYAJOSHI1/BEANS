from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
import json

from beans.schema import CanonicalRecord, AlertRecord
from beans.ingest.csv_parser import StreamingCSVParser
from beans.ingest.json_parser import StreamingJSONParser
from beans.ingest.xml_parser import StreamingXMLParser
from beans.enrich.geoip import OfflineGeoIPEnricher
from beans.enrich.asn_classifier import ASNClassifier
from beans.store.duck import DuckStore
from beans.graph.build import HeterogeneousGraphBuilder
from beans.graph.firstspy import FirstSpyEstimator
from beans.features.extractors import FeatureExtractor
from beans.engines.e1_cluster import EntityClusteringEngine
from beans.engines.e2_anomaly import AnomalyDetectionEngine
from beans.engines.e3_peelmix import PeelingAndMixingClassifier
from beans.engines.e4_propagate import RiskPropagationEngine
from beans.score.fuse import MetaFusionEngine
from beans.explain.reasons import PlainEnglishReasonGenerator
from beans.explain.shap_explain import SHAPExplainerService

class ForensicPipeline:
    """
    Master pipeline executing the full ingestion -> enrich -> graph -> 4 engines -> fusion -> XAI -> alert cycle.
    """

    def __init__(self, store: Optional[DuckStore] = None):
        self.store = store or DuckStore()
        self.enricher = OfflineGeoIPEnricher()
        self.e2_engine = AnomalyDetectionEngine()
        self.e3_engine = PeelingAndMixingClassifier()

    def run_file_ingestion(self, file_path: Path) -> Dict[str, Any]:
        """Parses file (CSV/JSON/XML), enriches, stores, and runs full ML pipeline"""
        p = Path(file_path)
        suffix = p.suffix.lower()

        if suffix == ".csv":
            parser = StreamingCSVParser()
        elif suffix in [".json", ".ndjson", ".jsonl"]:
            parser = StreamingJSONParser()
        elif suffix == ".xml":
            parser = StreamingXMLParser()
        else:
            raise ValueError(f"Unsupported file extension: {suffix}")

        records: List[CanonicalRecord] = []
        for rec in parser.parse(p):
            # Offline enrichment
            geo_info = self.enricher.enrich(rec.src_ip)
            rec.geo_country = geo_info["country"]
            rec.geo_city = geo_info["city"]
            rec.geo_lat = geo_info["lat"]
            rec.geo_lon = geo_info["lon"]
            rec.asn = geo_info["asn"]
            rec.asn_name = geo_info["asn_name"]
            rec.asn_type = ASNClassifier.classify(geo_info["asn"])
            records.append(rec)

        # Store in DuckDB
        self.store.insert_records(records)

        # Run AI/ML pipeline
        pipeline_stats = self.execute_ml_pipeline(records)
        return {
            "file": p.name,
            "records_ingested": len(records),
            "pipeline_stats": pipeline_stats
        }

    def execute_ml_pipeline(self, records: List[CanonicalRecord]) -> Dict[str, Any]:
        if not records:
            return {"status": "empty_records"}

        # 1. Graph & First-Spy Attribution
        first_spies = FirstSpyEstimator.estimate_originators(records)

        # 2. Engine 2: Anomaly Detection
        e2_scores = self.e2_engine.fit_predict(records)

        # 3. Engine 3: Peeling-Chain & Mixing Typology
        e3_predictions = self.e3_engine.predict_probabilities(records)

        # Identify CoinJoin TXIDs for CIOH bypass
        coinjoin_txids = {txid for txid, pred in e3_predictions.items() if pred["predicted_typology"] == "COINJOIN"}

        # 4. Engine 1: Entity Clustering (CIOH)
        cluster_map = EntityClusteringEngine.compute_clusters(records, coinjoin_txids=coinjoin_txids)

        # 5. Engine 4: Risk Propagation from Seeds
        # Load seeds from DuckDB or default seeds
        conn = self.store.get_connection()
        try:
            seeds_df = conn.execute("SELECT address FROM seeds").fetchdf()
            seed_addrs = set(seeds_df["address"].tolist()) if not seeds_df.empty else set()
        except Exception:
            seed_addrs = set()
        finally:
            conn.close()

        # If no seeds loaded, pick high-anomaly wallets as initial seeds for demo
        if not seed_addrs:
            for r in records:
                if r.asn_type == "BULLETPROOF" and r.input_addresses:
                    seed_addrs.add(r.input_addresses[0])

        e4_ppr, e4_taint, e4_paths = RiskPropagationEngine.compute_ppr_and_taint(records, seed_addrs)

        # 6. Meta-Fusion, Scoring & Alert Generation
        alerts: List[AlertRecord] = []
        alert_idx = 1

        # Track wallet profile aggregates
        wallet_stats = {}
        for r in records:
            # First spy info
            spy_info = first_spies.get(r.txid, {})
            e3_info = e3_predictions.get(r.txid, {"predicted_typology": "NORMAL", "confidence": 0.5})
            e2_val = e2_scores.get(r.txid, 0.0)

            # Input wallets evaluation
            for w in r.input_addresses:
                cid = cluster_map.get(w, "SOLO")
                ppr_val = e4_ppr.get(w, 0.0)
                taint_val = e4_taint.get(w, 0.0)
                path_seed = e4_paths.get(w, [])

                net_meta = {
                    "asn": r.asn,
                    "asn_type": r.asn_type,
                    "geo_country": r.geo_country,
                    "has_impossible_travel": False,
                    "travel_speed_kmh": 0.0
                }

                risk_score, cal_conf, severity, components = MetaFusionEngine.fuse_entity_score(
                    address=w,
                    cluster_id=cid,
                    e2_anomaly=e2_val,
                    e3_typology=e3_info["predicted_typology"],
                    e3_conf=e3_info["confidence"],
                    e4_ppr=ppr_val,
                    e4_taint=taint_val,
                    network_meta=net_meta
                )

                wallet_stats[w] = {
                    "risk_score": risk_score,
                    "threat_classification": e3_info["predicted_typology"],
                    "cluster_id": cid,
                    "associated_ip": r.src_ip
                }

                # Trigger alert if risk exceeds medium threshold
                if risk_score >= 35.0:
                    feats = FeatureExtractor.extract_tx_features(r)
                    shap_top = SHAPExplainerService.compute_top_features(feats, risk_score)
                    reasons = PlainEnglishReasonGenerator.generate_reasons(
                        typology=e3_info["predicted_typology"],
                        typology_conf=e3_info["confidence"],
                        taint_pct=taint_val,
                        path_to_seed=path_seed,
                        network_meta=net_meta,
                        anomaly_score=e2_val,
                        fan_out_ratio=feats.get("fan_out_ratio", 1.0)
                    )

                    alert = AlertRecord(
                        alert_id=f"ALT-{alert_idx:05d}",
                        entity_id=w,
                        entity_type="WALLET",
                        alert_type=f"{e3_info['predicted_typology']}_PATTERN",
                        risk_score=risk_score,
                        calibrated_confidence=cal_conf,
                        severity=severity,
                        reasons=reasons,
                        shap_top_features=shap_top,
                        engine_scores=components,
                        evidence={
                            "txid": r.txid,
                            "path_to_seed": path_seed,
                            "first_spy_ip": spy_info.get("first_spy_ip"),
                            "first_spy_confidence": spy_info.get("confidence")
                        },
                        status="OPEN"
                    )
                    alerts.append(alert)
                    alert_idx += 1

        # Deduplicate alerts per entity, keeping highest score
        unique_alerts = {}
        for a in alerts:
            if a.entity_id not in unique_alerts or a.risk_score > unique_alerts[a.entity_id].risk_score:
                unique_alerts[a.entity_id] = a

        # Store alerts in DuckDB
        conn = self.store.get_connection()
        for a in unique_alerts.values():
            conn.execute("""
            INSERT OR REPLACE INTO alerts (
                alert_id, entity_id, entity_type, alert_type, risk_score, calibrated_confidence,
                severity, reasons, shap_top_features, engine_scores, evidence, status, assigned_to
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                a.alert_id, a.entity_id, a.entity_type, a.alert_type, a.risk_score, a.calibrated_confidence,
                a.severity, a.reasons, json.dumps(a.shap_top_features), json.dumps(a.engine_scores),
                json.dumps(a.evidence), a.status, a.assigned_to
            ])

        # Update wallet profiles in DuckDB
        for w, st in wallet_stats.items():
            conn.execute("""
            INSERT OR REPLACE INTO wallet_profiles (
                address, risk_score, threat_classification, cluster_id, associated_ips, tags
            ) VALUES (?, ?, ?, ?, ?, ?)
            """, [
                w, st["risk_score"], st["threat_classification"], st["cluster_id"], [st["associated_ip"]], [st["threat_classification"]]
            ])

        conn.close()

        return {
            "total_transactions": len(records),
            "clusters_computed": len(set(cluster_map.values())),
            "alerts_generated": len(unique_alerts),
            "seeds_propagated": len(seed_addrs)
        }
