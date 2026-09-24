import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from beans.schema import CanonicalRecord
from beans.synth.ledger import generate_bitcoin_address, generate_txid, UTXOPool

class LegitimateActorGenerator:
    """
    Generates standard background legitimate transactions (Retail, Exchanges, Merchants).
    """

    @classmethod
    def generate_retail_transaction(cls, pool: UTXOPool, timestamp: datetime) -> Tuple[CanonicalRecord, Dict]:
        sender = generate_bitcoin_address("bc1q", "retail_user")
        recipient = generate_bitcoin_address("bc1q", "retail_merchant")
        change = generate_bitcoin_address("bc1q", "retail_change")

        amount = round(random.uniform(0.005, 0.45), 5)
        fee = 0.0001
        in_amt = round(amount + random.uniform(0.01, 0.1), 5)
        change_amt = round(in_amt - amount - fee, 5)

        txid = generate_txid()
        rec = CanonicalRecord(
            timestamp=timestamp,
            src_ip="24.120.45.12",
            src_port=8333,
            dst_ip="86.128.90.4",
            dst_port=8333,
            txid=txid,
            input_addresses=[sender],
            input_amounts=[in_amt],
            output_addresses=[recipient, change],
            output_amounts=[amount, change_amt],
            fee=fee,
            script_type="P2WPKH",
            geo_country="US",
            geo_city="New York",
            asn="AS7018",
            asn_name="AT&T Residential",
            asn_type="RESIDENTIAL"
        )
        label = {"txid": txid, "address": sender, "typology": "NORMAL", "cluster_id": "CLUST_RETAIL"}
        return rec, label

    @classmethod
    def generate_exchange_sweep(cls, pool: UTXOPool, timestamp: datetime, num_inputs: int = 15) -> Tuple[CanonicalRecord, Dict]:
        deposit_addrs = [generate_bitcoin_address("bc1q", f"binance_user_{i}") for i in range(num_inputs)]
        in_amts = [round(random.uniform(0.05, 0.5), 4) for _ in range(num_inputs)]
        cold_vault = generate_bitcoin_address("bc1q", "binance_cold_storage_master")
        
        fee = 0.001
        total_out = round(sum(in_amts) - fee, 4)

        txid = generate_txid()
        rec = CanonicalRecord(
            timestamp=timestamp,
            src_ip="52.128.40.10",
            src_port=8333,
            dst_ip="142.250.190.1",
            dst_port=8333,
            txid=txid,
            input_addresses=deposit_addrs,
            input_amounts=in_amts,
            output_addresses=[cold_vault],
            output_amounts=[total_out],
            fee=fee,
            script_type="P2WPKH",
            geo_country="US",
            geo_city="Seattle",
            asn="AS16509",
            asn_name="Amazon AWS Datacenter",
            asn_type="DATACENTER"
        )
        label = {"txid": txid, "address": cold_vault, "typology": "EXCHANGE_SWEEP", "cluster_id": "CLUST_BINANCE_COLD"}
        return rec, label
