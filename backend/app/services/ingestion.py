import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.app.models.schema import Transaction, NetworkObservation, ThreatIntel, WalletProfile, Alert, AuditLog
from backend.app.services.pattern_matcher import ThreatPatternMatcher
from backend.app.services.scoring_engine import CompositeScoringEngine
from backend.app.services.geo_math import calculate_geo_velocity
from backend.app.services.clustering import EntityClusterService

class IngestionPipeline:

    @classmethod
    def ingest_transactions(cls, db: Session, tx_data_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Ingests transactions, updates wallet profiles, recalculates clusters, 
        and evaluates automated threat detection rules.
        """
        inserted_count = 0
        all_touched_addresses = set()

        for raw_tx in tx_data_list:
            txid = raw_tx["txid"]
            existing = db.query(Transaction).filter(Transaction.txid == txid).first()
            
            inputs = raw_tx.get("input_addresses", [])
            outputs = raw_tx.get("output_addresses", [])
            in_amts = raw_tx.get("input_amounts", [])
            out_amts = raw_tx.get("output_amounts", [])
            total_in = sum(float(x) for x in in_amts) if in_amts else 0.0
            total_out = sum(float(x) for x in out_amts) if out_amts else 0.0
            ts = raw_tx["timestamp"]
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))

            if not existing:
                tx_obj = Transaction(
                    txid=txid,
                    timestamp=ts,
                    input_addresses=json.dumps(inputs),
                    output_addresses=json.dumps(outputs),
                    input_amounts=json.dumps(in_amts),
                    output_amounts=json.dumps(out_amts),
                    total_input=total_in,
                    total_output=total_out,
                    fee=float(raw_tx.get("fee", 0.0)),
                    script_type=raw_tx.get("script_type", "P2WPKH"),
                    block_height=raw_tx.get("block_height", 0),
                    observed_ips=json.dumps(raw_tx.get("observed_ips", []))
                )
                db.add(tx_obj)
                inserted_count += 1
            else:
                existing.observed_ips = json.dumps(raw_tx.get("observed_ips", []))

            for addr in inputs + outputs:
                all_touched_addresses.add(addr)

        db.commit()

        # Update Wallet Profiles & Balances
        cls._refresh_wallet_profiles(db, list(all_touched_addresses))
        
        # Trigger Correlation & Threat Engine
        alerts_generated = cls.run_correlation_engine(db)

        # Audit log
        db.add(AuditLog(
            action="INGEST_TRANSACTIONS",
            investigator="System Ingestion Engine",
            details=json.dumps({"inserted_txs": inserted_count, "touched_wallets": len(all_touched_addresses), "alerts_triggered": len(alerts_generated)})
        ))
        db.commit()

        return {
            "status": "success",
            "transactions_processed": len(tx_data_list),
            "new_transactions": inserted_count,
            "alerts_generated": len(alerts_generated)
        }

    @classmethod
    def ingest_network_observations(cls, db: Session, net_data_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Ingests SIGINT network logs and updates geo/IP profiles"""
        count = 0
        for obs in net_data_list:
            ts = obs["timestamp"]
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            
            n_obj = NetworkObservation(
                timestamp=ts,
                src_ip=obs["src_ip"],
                dst_ip=obs.get("dst_ip"),
                src_port=obs.get("src_port", 8333),
                dst_port=obs.get("dst_port", 8333),
                src_asn=obs.get("src_asn", "AS_UNKNOWN"),
                src_asn_name=obs.get("src_asn_name", "Unknown"),
                src_country=obs.get("src_country", "XX"),
                src_city=obs.get("src_city", "Unknown"),
                src_lat=float(obs.get("src_lat", 0.0)),
                src_lon=float(obs.get("src_lon", 0.0)),
                protocol=obs.get("protocol", "TCP"),
                isp_type=obs.get("isp_type", "RESIDENTIAL")
            )
            db.add(n_obj)
            count += 1
        db.commit()

        # Run correlation after network update
        cls.run_correlation_engine(db)
        return {"status": "success", "network_observations_added": count}

    @classmethod
    def ingest_threat_intel(cls, db: Session, threat_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Ingests OSINT threat records and updates wallet classifications"""
        count = 0
        for t in threat_list:
            t_obj = ThreatIntel(
                entity_type=t.get("entity_type", "WALLET"),
                entity_id=t["entity_id"],
                source=t["source"],
                threat_type=t["threat_type"],
                incident_name=t["incident_name"],
                confidence=float(t.get("confidence", 0.9)),
                notes=t.get("notes", "")
            )
            db.add(t_obj)
            count += 1
        db.commit()

        cls.run_correlation_engine(db)
        return {"status": "success", "threat_intel_records_added": count}

    @classmethod
    def _refresh_wallet_profiles(cls, db: Session, addresses: List[str]):
        """Recalculates balances, tx counts, and first/last seen for addresses"""
        all_txs = db.query(Transaction).all()
        
        # Prepare clustering map
        tx_dicts = []
        for tx in all_txs:
            tx_dicts.append({
                "input_addresses": tx.get_input_addrs(),
                "output_addresses": tx.get_output_addrs(),
                "is_coinjoin": False
            })
        cluster_map = EntityClusterService.compute_clusters(tx_dicts)

        for addr in addresses:
            profile = db.query(WalletProfile).filter(WalletProfile.address == addr).first()
            if not profile:
                profile = WalletProfile(address=addr)
                db.add(profile)

            # Compute stats
            in_txs = [tx for tx in all_txs if addr in tx.get_input_addrs()]
            out_txs = [tx for tx in all_txs if addr in tx.get_output_addrs()]
            related_txs = list(set(in_txs + out_txs))

            if related_txs:
                timestamps = [tx.timestamp for tx in related_txs]
                profile.first_seen = min(timestamps)
                profile.last_seen = max(timestamps)
                profile.transaction_count = len(related_txs)

                # Total received
                total_rcv = 0.0
                for tx in out_txs:
                    outs = tx.get_output_addrs()
                    amts = tx.get_output_amts()
                    for idx, o in enumerate(outs):
                        if o == addr and idx < len(amts):
                            total_rcv += float(amts[idx])
                profile.total_received = round(total_rcv, 4)

                # Total sent
                total_snt = 0.0
                for tx in in_txs:
                    ins = tx.get_input_addrs()
                    amts = tx.get_input_amts()
                    for idx, i in enumerate(ins):
                        if i == addr and idx < len(amts):
                            total_snt += float(amts[idx])
                profile.total_sent = round(total_snt, 4)

                profile.balance = max(0.0, round(profile.total_received - profile.total_sent, 4))
                profile.cluster_id = cluster_map.get(addr)

        db.commit()

    @classmethod
    def run_correlation_engine(cls, db: Session) -> List[Alert]:
        """
        Executes multi-layer correlation across Transactions, NetworkObservations, and OSINT:
        1. Checks OSINT Threat Intel matches
        2. Evaluates structural playbooks (Ransomware, CoinJoin, Peel Chain, Exchange Sweep)
        3. Correlates SIGINT network observations (Geo-velocity impossible travel, Bulletproof ASNs)
        4. Calculates dynamic composite risk score
        5. Emits/Updates Alerts
        """
        wallets = db.query(WalletProfile).all()
        transactions = db.query(Transaction).all()
        net_obs = db.query(NetworkObservation).order_by(NetworkObservation.timestamp.asc()).all()
        threat_intel = db.query(ThreatIntel).all()

        osint_by_entity = {}
        for ti in threat_intel:
            osint_by_entity.setdefault(ti.entity_id, []).append({
                "source": ti.source,
                "threat_type": ti.threat_type,
                "incident_name": ti.incident_name,
                "confidence": ti.confidence
            })

        generated_alerts = []

        # 1. Transaction-level patterns (CoinJoin, Sweeps)
        for tx in transactions:
            tx_dict = {
                "txid": tx.txid,
                "timestamp": tx.timestamp,
                "input_addresses": tx.get_input_addrs(),
                "output_addresses": tx.get_output_addrs(),
                "output_amounts": tx.get_output_amts(),
                "fee": tx.fee
            }

            # Check CoinJoin
            cj_conf, cj_evidence, cj_details = ThreatPatternMatcher.evaluate_coinjoin_mixing(tx_dict)
            if cj_conf >= 0.5:
                # Find or create Alert
                alert_key = f"MIX_{tx.txid[:16]}"
                existing_alert = db.query(Alert).filter(Alert.entity_id == tx.txid).first()
                
                score, sev, breakdown, bullets = CompositeScoringEngine.calculate_score(
                    pattern_confidence=cj_conf,
                    osint_hits=[],
                    sigint_features={},
                    temporal_features={}
                )

                if not existing_alert:
                    alert = Alert(
                        entity_type="TRANSACTION",
                        entity_id=tx.txid,
                        alert_type="MIXING_DETECTED",
                        severity=sev,
                        reason=f"CoinJoin privacy mixing signature detected ({cj_details.get('max_equal_outputs')} equal outputs)",
                        evidence_breakdown=json.dumps(cj_evidence + bullets),
                        score_components=json.dumps(breakdown),
                        automated_score=score,
                        status="OPEN"
                    )
                    db.add(alert)
                    generated_alerts.append(alert)

        # 2. Wallet-level patterns (Ransomware, Peel Chain Laundering, Geo-Anomalies)
        for w in wallets:
            w_dict = {
                "address": w.address,
                "first_seen": w.first_seen,
                "last_seen": w.last_seen,
                "total_received": w.total_received,
                "total_sent": w.total_sent,
                "transaction_count": w.transaction_count
            }

            # Gather related txs
            w_txs = [
                {
                    "txid": tx.txid,
                    "timestamp": tx.timestamp,
                    "input_addresses": tx.get_input_addrs(),
                    "output_addresses": tx.get_output_addrs(),
                    "output_amounts": tx.get_output_amts(),
                    "fee": tx.fee,
                    "observed_ips": tx.get_observed_ips()
                }
                for tx in transactions
                if w.address in tx.get_input_addrs() or w.address in tx.get_output_addrs()
            ]

            # Correlate SIGINT network observations
            w_ips = set()
            for tx in w_txs:
                for ip in tx.get("observed_ips", []):
                    w_ips.add(ip)
            
            w.associated_ips = json.dumps(list(w_ips))
            w_net_obs = [n for n in net_obs if n.src_ip in w_ips]

            # Geo velocity check across network hops
            has_impossible_travel = False
            travel_speed = 0.0
            if len(w_net_obs) >= 2:
                for i in range(1, len(w_net_obs)):
                    n1, n2 = w_net_obs[i-1], w_net_obs[i]
                    loc1 = {"lat": n1.src_lat, "lon": n1.src_lon}
                    loc2 = {"lat": n2.src_lat, "lon": n2.src_lon}
                    d_km, spd, is_imp = calculate_geo_velocity(loc1, loc2, n1.timestamp, n2.timestamp)
                    if is_imp:
                        has_impossible_travel = True
                        travel_speed = max(travel_speed, spd)

            sigint_feats = {
                "has_bulletproof": any(n.isp_type == "BULLETPROOF" for n in w_net_obs),
                "is_tor_or_vpn": any(n.isp_type in ["VPN", "TOR_EXIT"] for n in w_net_obs),
                "has_impossible_travel": has_impossible_travel,
                "travel_speed_kmh": travel_speed,
                "src_asn": w_net_obs[0].src_asn if w_net_obs else "UNKNOWN"
            }

            # Evaluate Ransomware Signature
            r_conf, r_evidence, r_details = ThreatPatternMatcher.evaluate_ransomware_signature(
                w_dict, w_txs, [{"isp_type": n.isp_type} for n in w_net_obs]
            )

            # Evaluate Peel Chain Signature
            p_conf, p_evidence, p_details = ThreatPatternMatcher.evaluate_theft_laundering_peel_chain(
                w_dict, w_txs, [{"isp_type": n.isp_type} for n in w_net_obs]
            )

            # Check OSINT
            osint_hits = osint_by_entity.get(w.address, [])

            # Highest pattern confidence
            best_pattern_conf = max(r_conf, p_conf)
            pattern_type = "RANSOMWARE_SIG" if r_conf >= p_conf and r_conf > 0.3 else "THEFT_LAUNDERING" if p_conf > 0.3 else "SUSPICIOUS_ENTITY"
            pattern_evidence = r_evidence if r_conf >= p_conf else p_evidence

            # Temporal features
            temporal_feats = {
                "lifespan_hours": r_details.get("lifespan_hours"),
                "avg_hop_interval_minutes": p_details.get("avg_hop_interval_minutes")
            }

            score, sev, breakdown, bullets = CompositeScoringEngine.calculate_score(
                pattern_confidence=best_pattern_conf,
                osint_hits=osint_hits,
                sigint_features=sigint_feats,
                temporal_features=temporal_feats
            )

            w.risk_score = score
            if osint_hits:
                w.threat_classification = osint_hits[0].get("threat_type", "SUSPICIOUS")
            elif r_conf >= 0.5:
                w.threat_classification = "RANSOMWARE"
            elif p_conf >= 0.5:
                w.threat_classification = "THEFT_HACK"
            elif score >= 60.0:
                w.threat_classification = "HIGH_RISK"

            # Create or update Alert if score meets threshold
            if score >= 35.0:
                existing_alert = db.query(Alert).filter(Alert.entity_id == w.address).first()
                all_evidence = pattern_evidence + bullets

                if not existing_alert:
                    alert = Alert(
                        entity_type="WALLET",
                        entity_id=w.address,
                        alert_type=pattern_type,
                        severity=sev,
                        reason=f"Multi-factor alert: {pattern_type.replace('_', ' ')} detected with {score:.0f} risk score",
                        evidence_breakdown=json.dumps(all_evidence),
                        score_components=json.dumps(breakdown),
                        automated_score=score,
                        status="OPEN"
                    )
                    db.add(alert)
                    generated_alerts.append(alert)
                else:
                    existing_alert.automated_score = score
                    existing_alert.severity = sev
                    existing_alert.score_components = json.dumps(breakdown)
                    existing_alert.evidence_breakdown = json.dumps(all_evidence)

        db.commit()
        return generated_alerts
