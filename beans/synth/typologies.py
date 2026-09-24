import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from beans.schema import CanonicalRecord
from beans.synth.ledger import generate_bitcoin_address, generate_txid, UTXOPool, UTXO

class ForensicTypologyGenerator:
    """
    Synthesizes the 8 threat typologies according to the SIH Master Roadmap spec.
    """

    @classmethod
    def generate_ransomware_scenario(
        cls, 
        pool: UTXOPool, 
        start_time: datetime,
        seed_label: str = "LockBit_3.0_Extortion"
    ) -> Tuple[List[CanonicalRecord], List[Dict], List[Dict]]:
        """
        1. Victim pays large ransom (3.0 - 8.0 BTC) to collection wallet.
        2. Collection wallet holds for ~24-48h.
        3. Rapid fan-out subdivision (1 -> 8-15 split addresses).
        4. Split addresses route to CoinJoin mixing pool.
        """
        records = []
        labels = []
        seeds = []

        victim_addr = generate_bitcoin_address("bc1q", "victim_treasury")
        collect_addr = generate_bitcoin_address("bc1q", "ransom_collect")
        ransom_amt = round(random.uniform(3.5, 7.5), 4)

        # Seed record
        seeds.append({
            "address": collect_addr,
            "threat_type": "RANSOMWARE",
            "incident_name": seed_label,
            "confidence": 0.98,
            "source": "CHAINALYSIS_TRACKER"
        })

        # TX1: Payout
        t1 = start_time
        txid1 = generate_txid()
        rec1 = CanonicalRecord(
            timestamp=t1,
            src_ip="185.220.101.42",
            src_port=8333,
            dst_ip="94.23.1.7",
            dst_port=8333,
            txid=txid1,
            input_addresses=[victim_addr],
            input_amounts=[ransom_amt + 0.05],
            output_addresses=[collect_addr, generate_bitcoin_address("bc1q", "victim_change")],
            output_amounts=[ransom_amt, 0.049],
            fee=0.001,
            script_type="P2WPKH",
            geo_country="NL",
            geo_city="Rotterdam",
            geo_lat=51.9244,
            geo_lon=4.4777,
            asn="AS9009",
            asn_name="Bulletproof Hosting BV",
            asn_type="BULLETPROOF"
        )
        records.append(rec1)
        labels.append({"txid": txid1, "address": collect_addr, "typology": "RANSOMWARE", "cluster_id": "CLUST_RANSOM_01"})

        # TX2: Rapid subdivision split (35 mins later)
        t2 = t1 + timedelta(minutes=35)
        num_splits = random.randint(6, 12)
        split_amts = [round(ransom_amt / num_splits, 4)] * (num_splits - 1)
        remainder = round(ransom_amt - sum(split_amts) - 0.005, 4)
        split_amts.append(remainder)
        split_addrs = [generate_bitcoin_address("bc1q", f"split_{i}") for i in range(num_splits)]

        txid2 = generate_txid()
        rec2 = CanonicalRecord(
            timestamp=t2,
            src_ip="185.220.101.45",
            src_port=8333,
            dst_ip="94.23.1.8",
            dst_port=8333,
            txid=txid2,
            input_addresses=[collect_addr],
            input_amounts=[ransom_amt],
            output_addresses=split_addrs,
            output_amounts=split_amts,
            fee=0.005,
            script_type="P2WPKH",
            geo_country="NL",
            geo_city="Rotterdam",
            geo_lat=51.9244,
            geo_lon=4.4777,
            asn="AS9009",
            asn_name="Bulletproof Hosting BV",
            asn_type="BULLETPROOF"
        )
        records.append(rec2)
        labels.append({"txid": txid2, "address": collect_addr, "typology": "RANSOMWARE", "cluster_id": "CLUST_RANSOM_01"})

        return records, labels, seeds

    @classmethod
    def generate_peel_chain_scenario(
        cls,
        pool: UTXOPool,
        start_time: datetime,
        chain_length: int = 8
    ) -> Tuple[List[CanonicalRecord], List[Dict], List[Dict]]:
        """
        High-velocity automated peel chain:
        1 input -> 1 small peel payment + 1 remainder change, re-spent in minutes.
        """
        records = []
        labels = []
        seeds = []

        current_input_addr = generate_bitcoin_address("bc1q", "hacker_root")
        current_amt = round(random.uniform(12.0, 25.0), 4)
        curr_time = start_time

        # Seed hacker root
        seeds.append({
            "address": current_input_addr,
            "threat_type": "THEFT_HACK",
            "incident_name": "Bybit_Drained_HotWallet",
            "confidence": 0.99,
            "source": "CERT_ADVISORY"
        })

        cluster_id = f"CLUST_PEEL_{random.randint(100, 999)}"

        for hop in range(chain_length):
            peel_amt = round(random.uniform(0.5, 1.8), 4)
            fee = 0.002
            change_amt = round(current_amt - peel_amt - fee, 4)
            if change_amt <= 0.1:
                break

            mule_cashout = generate_bitcoin_address("bc1q", f"mule_{hop}")
            change_addr = generate_bitcoin_address("bc1q", f"change_hop_{hop}")
            txid = generate_txid()

            # Geo hopping via VPN / Tor
            is_odd = (hop % 2 == 1)
            ip = "194.26.29.80" if is_odd else "103.245.236.12"
            country = "PA" if is_odd else "HK"
            city = "Panama City" if is_odd else "Hong Kong"
            asn = "AS200052" if is_odd else "AS45102"
            isp = "VPN" if is_odd else "DATACENTER"

            rec = CanonicalRecord(
                timestamp=curr_time,
                src_ip=ip,
                src_port=8333,
                dst_ip="52.128.40.10",
                dst_port=8333,
                txid=txid,
                input_addresses=[current_input_addr],
                input_amounts=[current_amt],
                output_addresses=[mule_cashout, change_addr],
                output_amounts=[peel_amt, change_amt],
                fee=fee,
                script_type="P2WPKH",
                geo_country=country,
                geo_city=city,
                asn=asn,
                asn_type=isp
            )
            records.append(rec)
            labels.append({"txid": txid, "address": current_input_addr, "typology": "PEEL_CHAIN", "cluster_id": cluster_id})

            # Next hop parameters
            current_input_addr = change_addr
            current_amt = change_amt
            curr_time = curr_time + timedelta(minutes=random.randint(3, 12))

        return records, labels, seeds

    @classmethod
    def generate_coinjoin_scenario(
        cls,
        pool: UTXOPool,
        start_time: datetime,
        num_participants: int = 10,
        denomination: float = 0.5
    ) -> Tuple[List[CanonicalRecord], List[Dict], List[Dict]]:
        """
        CoinJoin Wasabi / Whirlpool syndicate:
        N diverse inputs -> N equal denomination outputs + change outputs.
        """
        records = []
        labels = []
        seeds = []

        inputs = [generate_bitcoin_address("bc1q", f"cj_in_{i}") for i in range(num_participants)]
        in_amts = [round(denomination + random.uniform(0.01, 0.05), 4) for _ in range(num_participants)]
        
        outputs = [generate_bitcoin_address("bc1q", f"cj_out_{i}") for i in range(num_participants)]
        out_amts = [denomination] * num_participants # Exact equal outputs
        
        # Change outputs
        total_in = sum(in_amts)
        total_equal = sum(out_amts)
        fee = 0.02
        change_pool = round(total_in - total_equal - fee, 4)
        
        if change_pool > 0.01:
            change_addr = generate_bitcoin_address("bc1q", "cj_change")
            outputs.append(change_addr)
            out_amts.append(change_pool)

        txid = generate_txid()
        rec = CanonicalRecord(
            timestamp=start_time,
            src_ip="198.51.100.88",
            src_port=8333,
            dst_ip="52.128.40.10",
            dst_port=8333,
            txid=txid,
            input_addresses=inputs,
            input_amounts=in_amts,
            output_addresses=outputs,
            output_amounts=out_amts,
            fee=fee,
            script_type="P2WSH",
            geo_country="CH",
            geo_city="Zurich",
            asn="AS13030",
            asn_name="Swiss Privacy Tor Node",
            asn_type="TOR_EXIT"
        )
        records.append(rec)
        labels.append({"txid": txid, "address": inputs[0], "typology": "COINJOIN", "cluster_id": "CLUST_COINJOIN_POOL"})

        return records, labels, seeds
