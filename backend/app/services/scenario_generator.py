from datetime import datetime, timedelta
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from backend.app.services.ingestion import IngestionPipeline
from backend.app.models.schema import CaseFile

class ScenarioGenerator:
    """
    Generates realistic, interconnected multi-hop forensic scenarios
    demonstrating Ransomware, CoinJoin Mixing, Exchange Hack Peel Chains, and Exchange Sweeps.
    """

    @classmethod
    def load_all_scenarios(cls, db: Session) -> Dict[str, Any]:
        """Loads and correlates the full suite of forensic investigation scenarios"""
        res_ransom = cls.load_lockbit_ransomware(db)
        res_mixing = cls.load_coinjoin_syndicate(db)
        res_peel = cls.load_exchange_hack_peel_chain(db)
        res_sweep = cls.load_exchange_consolidation_sweep(db)

        # Create default investigation cases
        case1 = CaseFile(
            case_name="Operation LockBit Eclipse - 2024 Extortion Ring",
            incident_type="RANSOMWARE",
            suspect_entities='["1LockBitRansomVictimCollect4812x", "1LockBitIntermediarySplit01aaaaaa", "1LockBitIntermediarySplit02bbbbbb"]',
            notes="Critical ransomware campaign active in Q3. Victim paid 4.85 BTC ransom. Funds rapidly fanned out and routed toward CoinJoin mixer.",
            investigator="Lead Forensics Special Agent",
            priority="CRITICAL",
            status="INVESTIGATING"
        )
        db.add(case1)

        case2 = CaseFile(
            case_name="Bybit Hot Wallet Drain - Rapid Peel Laundering",
            incident_type="THEFT_HACK",
            suspect_entities='["1HackerDrainPrimaryVictim999999", "1PeelHop01ChangeAddress888888", "1PeelHop02ChangeAddress777777"]',
            notes="Unauthorized private key compromise. 18.5 BTC drained with high-velocity automated peel chain and VPN hopping.",
            investigator="Senior Cyber Crime Analyst",
            priority="HIGH",
            status="OPEN"
        )
        db.add(case2)
        db.commit()

        return {
            "status": "success",
            "scenarios_loaded": [
                "LockBit Ransomware Extortion",
                "CoinJoin Wasabi Mixing Syndicate",
                "High-Velocity Exchange Hack Peel Chain",
                "Legitimate Binance Exchange Sweep"
            ]
        }

    @classmethod
    def load_lockbit_ransomware(cls, db: Session) -> Dict[str, Any]:
        now = datetime.utcnow()
        t0 = now - timedelta(hours=3, minutes=45)
        t1 = now - timedelta(hours=3, minutes=10)
        t2 = now - timedelta(hours=2, minutes=20)

        # 1. Network observations
        net_logs = [
            {
                "timestamp": t0.isoformat(),
                "src_ip": "185.220.101.42",
                "src_port": 8333,
                "src_asn": "AS9009",
                "src_asn_name": "Bulletproof Hosting BV",
                "src_country": "NL",
                "src_city": "Rotterdam",
                "src_lat": 51.9244,
                "src_lon": 4.4777,
                "isp_type": "BULLETPROOF"
            },
            {
                "timestamp": t1.isoformat(),
                "src_ip": "185.220.101.43",
                "src_port": 8333,
                "src_asn": "AS9009",
                "src_asn_name": "Bulletproof Hosting BV",
                "src_country": "NL",
                "src_city": "Rotterdam",
                "src_lat": 51.9244,
                "src_lon": 4.4777,
                "isp_type": "BULLETPROOF"
            }
        ]

        # 2. Blockchain transactions
        victim_addr = "1CorporateVictimTreasuryWallet01"
        collect_addr = "1LockBitRansomVictimCollect4812x"
        split_addrs = [f"1LockBitIntermediarySplit0{i}aaaaaa" for i in range(1, 9)]

        txs = [
            # Ransom payout tx
            {
                "txid": "7a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b",
                "timestamp": t0.isoformat(),
                "input_addresses": [victim_addr],
                "output_addresses": [collect_addr, "1CorporateVictimChangeReturn99"],
                "input_amounts": [5.0],
                "output_amounts": [4.85, 0.149],
                "fee": 0.001,
                "script_type": "P2WPKH",
                "block_height": 860100,
                "observed_ips": ["185.220.101.42"]
            },
            # Rapid subdivision split tx
            {
                "txid": "9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e",
                "timestamp": t1.isoformat(),
                "input_addresses": [collect_addr],
                "output_addresses": split_addrs,
                "input_amounts": [4.85],
                "output_amounts": [0.605] * 8,
                "fee": 0.01,
                "script_type": "P2WPKH",
                "block_height": 860103,
                "observed_ips": ["185.220.101.43"]
            }
        ]

        # 3. OSINT Threat Intel
        threats = [
            {
                "entity_type": "WALLET",
                "entity_id": collect_addr,
                "source": "CHAINALYSIS_PUBLIC_TRACKER",
                "threat_type": "RANSOMWARE",
                "incident_name": "LockBit_3.0_Healthcare_Campaign",
                "confidence": 0.98,
                "notes": "Verified LockBit negotiation ransom collection address reported by incident response firm."
            },
            {
                "entity_type": "WALLET",
                "entity_id": victim_addr,
                "source": "FBI_CYBER_ADVISORY",
                "threat_type": "VICTIM_ENTITY",
                "incident_name": "LockBit_Healthcare_Extortion",
                "confidence": 0.95,
                "notes": "Compromised enterprise treasury source."
            }
        ]

        IngestionPipeline.ingest_network_observations(db, net_logs)
        IngestionPipeline.ingest_threat_intel(db, threats)
        return IngestionPipeline.ingest_transactions(db, txs)

    @classmethod
    def load_coinjoin_syndicate(cls, db: Session) -> Dict[str, Any]:
        now = datetime.utcnow()
        t = now - timedelta(hours=1, minutes=45)

        inputs = [f"1WasabiParticipantInput0{i:02d}xxxxxx" for i in range(1, 11)]
        outputs = [f"1WasabiMixedAnonymizedOutput0{i:02d}yy" for i in range(1, 11)]

        txs = [
            {
                "txid": "3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d",
                "timestamp": t.isoformat(),
                "input_addresses": inputs,
                "output_addresses": outputs,
                "input_amounts": [0.505] * 10,
                "output_amounts": [0.500] * 10, # Uniform 0.5 BTC outputs
                "fee": 0.05,
                "script_type": "P2WSH",
                "block_height": 860115,
                "observed_ips": ["198.51.100.88"]
            }
        ]

        threats = [
            {
                "entity_type": "WALLET",
                "entity_id": outputs[0],
                "source": "ELLIPTIC_MIXER_MONITOR",
                "threat_type": "MIXING",
                "incident_name": "Wasabi_Whirlpool_Pool_Round_942",
                "confidence": 0.88,
                "notes": "Identified mixing anonymity set output."
            }
        ]

        IngestionPipeline.ingest_threat_intel(db, threats)
        return IngestionPipeline.ingest_transactions(db, txs)

    @classmethod
    def load_exchange_hack_peel_chain(cls, db: Session) -> Dict[str, Any]:
        now = datetime.utcnow()
        t0 = now - timedelta(hours=5)
        t1 = now - timedelta(hours=4, minutes=40)
        t2 = now - timedelta(hours=4, minutes=15)

        hacker_root = "1HackerDrainPrimaryVictim999999"
        hop1_change = "1PeelHop01ChangeAddress888888"
        hop2_change = "1PeelHop02ChangeAddress777777"
        cashout_target = "1HighRiskNoKycOtcDeskCashout01"

        net_logs = [
            {
                "timestamp": t0.isoformat(),
                "src_ip": "103.245.236.12",
                "src_port": 54201, # Non-standard high port
                "src_asn": "AS45102",
                "src_asn_name": "Alibaba Cloud Datacenter",
                "src_country": "HK",
                "src_city": "Hong Kong",
                "src_lat": 22.3193,
                "src_lon": 114.1694,
                "isp_type": "DATACENTER"
            },
            {
                "timestamp": t1.isoformat(),
                "src_ip": "194.26.29.80",
                "src_port": 8333,
                "src_asn": "AS200052",
                "src_asn_name": "Panama Privacy VPN Node",
                "src_country": "PA",
                "src_city": "Panama City",
                "src_lat": 8.9824,
                "src_lon": -79.5199,
                "isp_type": "VPN"
            }
        ]

        txs = [
            {
                "txid": "11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff",
                "timestamp": t0.isoformat(),
                "input_addresses": [hacker_root],
                "output_addresses": ["1MuleCashoutAddressA1", hop1_change],
                "input_amounts": [18.5],
                "output_amounts": [2.5, 15.99],
                "fee": 0.01,
                "script_type": "P2WPKH",
                "block_height": 860080,
                "observed_ips": ["103.245.236.12"]
            },
            {
                "txid": "aabbccddeeff11223344556677889900aabbccddeeff11223344556677889900",
                "timestamp": t1.isoformat(),
                "input_addresses": [hop1_change],
                "output_addresses": ["1MuleCashoutAddressB2", hop2_change],
                "input_amounts": [15.99],
                "output_amounts": [3.0, 12.98],
                "fee": 0.01,
                "script_type": "P2WPKH",
                "block_height": 860085,
                "observed_ips": ["194.26.29.80"]
            },
            {
                "txid": "556677889900aabbccddeeff11223344556677889900aabbccddeeff11223344",
                "timestamp": t2.isoformat(),
                "input_addresses": [hop2_change],
                "output_addresses": [cashout_target, "1ChangeReturnFinalClean77"],
                "input_amounts": [12.98],
                "output_amounts": [10.0, 2.97],
                "fee": 0.01,
                "script_type": "P2WPKH",
                "block_height": 860090,
                "observed_ips": ["194.26.29.80"]
            }
        ]

        threats = [
            {
                "entity_type": "WALLET",
                "entity_id": hacker_root,
                "source": "CERT_ALERT_FEED",
                "threat_type": "THEFT_HACK",
                "incident_name": "Bybit_Exchange_Drain_Incident",
                "confidence": 0.99,
                "notes": "Target hot wallet compromise reported in major security advisory."
            }
        ]

        IngestionPipeline.ingest_network_observations(db, net_logs)
        IngestionPipeline.ingest_threat_intel(db, threats)
        return IngestionPipeline.ingest_transactions(db, txs)

    @classmethod
    def load_exchange_consolidation_sweep(cls, db: Session) -> Dict[str, Any]:
        now = datetime.utcnow()
        t = now - timedelta(hours=8)

        inputs = [f"1BinanceUserDepositWallet_{i:03d}xx" for i in range(1, 26)]
        outputs = ["1BinanceMasterColdStorageVault01"]

        txs = [
            {
                "txid": "eeff00112233445566778899aabbccddeeff00112233445566778899aabbccdd",
                "timestamp": t.isoformat(),
                "input_addresses": inputs,
                "output_addresses": outputs,
                "input_amounts": [0.15] * 25,
                "output_amounts": [3.748],
                "fee": 0.002,
                "script_type": "P2WPKH",
                "block_height": 860050,
                "observed_ips": ["52.128.40.10"]
            }
        ]

        threats = [
            {
                "entity_type": "WALLET",
                "entity_id": outputs[0],
                "source": "PUBLIC_EXCHANGE_REGISTRY",
                "threat_type": "EXCHANGE",
                "incident_name": "Binance_Cold_Storage_Vault",
                "confidence": 0.99,
                "notes": "Verified verified exchange cold wallet."
            }
        ]

        IngestionPipeline.ingest_threat_intel(db, threats)
        return IngestionPipeline.ingest_transactions(db, txs)
