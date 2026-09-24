import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta
import hashlib
from typing import List, Dict, Any

from beans.config import settings
from beans.schema import CanonicalRecord
from beans.synth.ledger import UTXOPool
from beans.synth.typologies import ForensicTypologyGenerator
from beans.synth.actors import LegitimateActorGenerator

class SyntheticDatasetWriter:
    """
    Generates and writes complete multi-format forensic datasets (CSV, JSON, XML)
    with ground-truth labels and seed lists (R1, R5, R12).
    """

    @classmethod
    def generate_dataset(
        cls,
        output_dir: Path,
        n_tx: int = 5000,
        illicit_rate: float = 0.05,
        seed: int = 42
    ) -> Dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        pool = UTXOPool()
        now = datetime.utcnow()
        records: List[CanonicalRecord] = []
        labels: List[Dict] = []
        seeds: List[Dict] = []

        # 1. Generate Illicit Typologies
        num_illicit_txs = max(5, int(n_tx * illicit_rate))
        
        # Ransomware
        r_recs, r_labels, r_seeds = ForensicTypologyGenerator.generate_ransomware_scenario(
            pool, now - timedelta(hours=6), "LockBit_3.0_Campaign"
        )
        records.extend(r_recs)
        labels.extend(r_labels)
        seeds.extend(r_seeds)

        # Peel Chain
        p_recs, p_labels, p_seeds = ForensicTypologyGenerator.generate_peel_chain_scenario(
            pool, now - timedelta(hours=4), chain_length=10
        )
        records.extend(p_recs)
        labels.extend(p_labels)
        seeds.extend(p_seeds)

        # CoinJoin
        cj_recs, cj_labels, cj_seeds = ForensicTypologyGenerator.generate_coinjoin_scenario(
            pool, now - timedelta(hours=2), num_participants=10
        )
        records.extend(cj_recs)
        labels.extend(cj_labels)
        seeds.extend(cj_seeds)

        # 2. Exchange sweeps (2 sweeps)
        sw_rec1, sw_lbl1 = LegitimateActorGenerator.generate_exchange_sweep(pool, now - timedelta(hours=8), 20)
        sw_rec2, sw_lbl2 = LegitimateActorGenerator.generate_exchange_sweep(pool, now - timedelta(hours=1), 15)
        records.extend([sw_rec1, sw_rec2])
        labels.extend([sw_lbl1, sw_lbl2])

        # 3. Fill with retail legitimate background traffic
        needed_retail = max(10, n_tx - len(records))
        for i in range(needed_retail):
            t = now - timedelta(minutes=int(i * 1.5))
            r_rec, r_lbl = LegitimateActorGenerator.generate_retail_transaction(pool, t)
            records.append(r_rec)
            labels.append(r_lbl)

        # Sort all chronologically
        records.sort(key=lambda r: r.timestamp)

        # Write CSV
        csv_file = output_dir / "transactions.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "src_ip", "src_port", "dst_ip", "dst_port",
                "txid", "input_addresses", "input_amounts", "output_addresses",
                "output_amounts", "fee", "script_type"
            ])
            for r in records:
                writer.writerow([
                    r.timestamp.isoformat(),
                    r.src_ip,
                    r.src_port,
                    r.dst_ip or "",
                    r.dst_port,
                    r.txid,
                    ";".join(r.input_addresses),
                    ";".join(str(a) for a in r.input_amounts),
                    ";".join(r.output_addresses),
                    ";".join(str(a) for a in r.output_amounts),
                    r.fee,
                    r.script_type
                ])

        # Write JSON
        json_file = output_dir / "transactions.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json_list = [
                {
                    "timestamp": r.timestamp.isoformat(),
                    "src_ip": r.src_ip,
                    "src_port": r.src_port,
                    "dst_ip": r.dst_ip,
                    "dst_port": r.dst_port,
                    "txid": r.txid,
                    "input_addresses": r.input_addresses,
                    "input_amounts": r.input_amounts,
                    "output_addresses": r.output_addresses,
                    "output_amounts": r.output_amounts,
                    "fee": r.fee,
                    "script_type": r.script_type
                }
                for r in records
            ]
            json.dump(json_list, f, indent=2)

        # Write XML
        xml_file = output_dir / "transactions.xml"
        root_elem = ET.Element("transactions")
        for r in records:
            tx_elem = ET.SubElement(root_elem, "tx", {
                "txid": r.txid,
                "timestamp": r.timestamp.isoformat(),
                "fee": str(r.fee),
                "script_type": r.script_type
            })
            ET.SubElement(tx_elem, "net", {
                "src_ip": r.src_ip,
                "src_port": str(r.src_port),
                "dst_ip": r.dst_ip or "",
                "dst_port": str(r.dst_port)
            })
            inputs_elem = ET.SubElement(tx_elem, "inputs")
            for addr, amt in zip(r.input_addresses, r.input_amounts):
                ET.SubElement(inputs_elem, "in", {"address": addr, "amount": str(amt)})
            outputs_elem = ET.SubElement(tx_elem, "outputs")
            for addr, amt in zip(r.output_addresses, r.output_amounts):
                ET.SubElement(outputs_elem, "out", {"address": addr, "amount": str(amt)})

        tree = ET.ElementTree(root_elem)
        tree.write(xml_file, encoding="utf-8", xml_declaration=True)

        # Write labels.csv
        labels_file = output_dir / "labels.csv"
        with open(labels_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["txid", "address", "typology", "cluster_id"])
            for l in labels:
                writer.writerow([l["txid"], l["address"], l["typology"], l["cluster_id"]])

        # Write seeds.csv
        seeds_file = output_dir / "seeds.csv"
        with open(seeds_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["address", "threat_type", "incident_name", "confidence", "source"])
            for s in seeds:
                writer.writerow([s["address"], s["threat_type"], s["incident_name"], s["confidence"], s["source"]])

        # Also copy seeds to data/seeds/
        settings.SEEDS_DIR.mkdir(parents=True, exist_ok=True)
        global_seeds_file = settings.SEEDS_DIR / "illicit_seeds.csv"
        with open(global_seeds_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["address", "threat_type", "incident_name", "confidence", "source"])
            for s in seeds:
                writer.writerow([s["address"], s["threat_type"], s["incident_name"], s["confidence"], s["source"]])

        # Compute SHA256 of CSV
        with open(csv_file, "rb") as f:
            csv_hash = hashlib.sha256(f.read()).hexdigest()

        manifest = {
            "dataset_name": output_dir.name,
            "total_transactions": len(records),
            "illicit_transactions": len([l for l in labels if l["typology"] != "NORMAL" and l["typology"] != "EXCHANGE_SWEEP"]),
            "seeds_count": len(seeds),
            "csv_sha256": csv_hash,
            "generated_at": now.isoformat()
        }
        with open(output_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return manifest
