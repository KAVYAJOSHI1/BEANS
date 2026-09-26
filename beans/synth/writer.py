"""Write a labelled synthetic dataset (generator v2, see beans/synth/sim.py).

Files in output_dir:
  transactions.csv / .json / .xml   one row per network observation (same tx seen from several peers)
  labels_address.csv                address, typology, entity_id, is_illicit        (ground truth)
  labels_tx.csv                     txid, tx_class, typology, is_illicit, entity_id (ground truth)
  labels.csv                        txid, address, typology, cluster_id             (legacy format)
  seeds.csv                         address, threat_type, incident_name, confidence, source
                                    (addresses of ~30% of illicit entities; the rest stay hidden)
  known_entities.csv                address, entity_name, entity_type, country, in_jurisdiction, source
                                    (partial exchange / mining-pool attribution, used by the action rules)
  manifest.json
Ground truth is for training and evaluation only. It is never used as a model input.
"""
import csv
import hashlib
import json
import math
import random
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any, Dict

from beans.synth.sim import ILLICIT, Sim

COLS = ["timestamp", "src_ip", "src_port", "dst_ip", "dst_port", "txid", "input_addresses", "input_amounts",
        "output_addresses", "output_amounts", "fee", "script_type", "tx_version", "locktime", "rbf"]


class SyntheticDatasetWriter:
    @classmethod
    def generate_dataset(cls, output_dir: Path, n_tx: int = 5000, illicit_rate: float = 0.05,
                         seed: int = 42) -> Dict[str, Any]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        sim = Sim(seed=seed)
        sim.run(n_tx)
        rows = sim.observations()

        def rec(o):
            return {
                "timestamp": o["ts"].strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "src_ip": o["src_ip"], "src_port": o["src_port"], "dst_ip": o["dst_ip"], "dst_port": o["dst_port"],
                "txid": o["txid"],
                "input_addresses": [a for a, _ in o["inputs"]], "input_amounts": [v for _, v in o["inputs"]],
                "output_addresses": [a for a, _ in o["outputs"]], "output_amounts": [v for _, v in o["outputs"]],
                "fee": o["fee"], "script_type": o["script"],
                "tx_version": o["tx_version"], "locktime": o["locktime"], "rbf": int(o["rbf"]),
            }

        records = [rec(o) for o in rows]
        with open(output_dir / "transactions.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(COLS)
            for r in records:
                w.writerow([";".join(map(str, r[c])) if isinstance(r[c], list) else r[c] for c in COLS])
        with open(output_dir / "transactions.json", "w", encoding="utf-8") as fh:
            json.dump(records, fh)
        root = ET.Element("transactions")
        for r in records:
            tx = ET.SubElement(root, "tx", {"txid": r["txid"], "timestamp": r["timestamp"], "fee": str(r["fee"]),
                                            "script_type": r["script_type"], "tx_version": str(r["tx_version"]),
                                            "locktime": str(r["locktime"]), "rbf": str(r["rbf"])})
            ET.SubElement(tx, "net", {k: str(r[k]) for k in ("src_ip", "src_port", "dst_ip", "dst_port")})
            ins = ET.SubElement(tx, "inputs")
            for a, v in zip(r["input_addresses"], r["input_amounts"]):
                ET.SubElement(ins, "in", {"address": a, "amount": str(v)})
            outs = ET.SubElement(tx, "outputs")
            for a, v in zip(r["output_addresses"], r["output_amounts"]):
                ET.SubElement(outs, "out", {"address": a, "amount": str(v)})
        ET.ElementTree(root).write(output_dir / "transactions.xml", encoding="utf-8", xml_declaration=True)

        # ---- ground truth
        with open(output_dir / "labels_address.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["address", "typology", "entity_id", "is_illicit"])
            for a, eid in sim.owner.items():
                e = sim.entities[eid]
                w.writerow([a, e.typology, eid, int(e.illicit)])
        with open(output_dir / "labels_tx.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["txid", "tx_class", "typology", "is_illicit", "entity_id"])
            for t in sim.txs:
                w.writerow([t["txid"], t["tx_class"], t["typology"], int(t["illicit"]), t["entity"]])
        with open(output_dir / "labels.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["txid", "address", "typology", "cluster_id"])
            for t in sim.txs:
                for a in {a for a, _ in t["inputs"]} | {a for a, _ in t["outputs"]}:
                    e = sim.entities[sim.owner[a]]
                    w.writerow([t["txid"], a, e.typology, e.eid])

        # ---- seeds: the investigator knows some addresses of ~30% of illicit entities
        rng = random.Random(seed + 1)
        used = {a for t in sim.txs for a, _ in t["inputs"] + t["outputs"]}
        illicit_ents = [e for e in sim.entities.values() if e.illicit and any(a in used for a in e.addresses)]
        known = rng.sample(illicit_ents, max(1, math.ceil(0.3 * len(illicit_ents))))
        seeds = []
        for e in known:
            addrs = [a for a in e.addresses if a in used]
            for a in rng.sample(addrs, min(len(addrs), rng.randint(1, 3))):
                seeds.append([a, e.typology, f"SYNTH-{e.eid}", round(rng.uniform(0.8, 0.99), 2), "SYNTHETIC_SEED"])
        with open(output_dir / "seeds.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["address", "threat_type", "incident_name", "confidence", "source"])
            w.writerows(seeds)

        # ---- known attribution (intel, not ground truth): the investigator's list of exchange and mining-pool
        # addresses. Partial on purpose (~80% of exchange deposit addresses), like a real attribution feed.
        vasps = [("Synthetic Indian VASP A", "IN", 1), ("Synthetic Indian VASP B", "IN", 1),
                 ("Synthetic Offshore VASP C", "SC", 0)]
        known_rows = []
        for ex, (name, country, in_jur) in zip(sim.exchanges, vasps):
            for a in ex.addresses:
                if a in used and (a in (ex.hot, ex.cold) or rng.random() < 0.8):
                    known_rows.append([a, name, "VASP", country, in_jur, "SYNTHETIC_ATTRIBUTION"])
        for i, m in enumerate(sim.miners):
            known_rows += [[a, f"Synthetic Mining Pool {i + 1}", "MINING_POOL", "XX", 0, "SYNTHETIC_ATTRIBUTION"]
                           for a in m.addresses if a in used]
        with open(output_dir / "known_entities.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["address", "entity_name", "entity_type", "country", "in_jurisdiction", "source"])
            w.writerows(known_rows)

        n_ill_addr = sum(1 for a in used if sim.entities[sim.owner[a]].illicit)
        manifest = {
            "generator": "beans-sim-v2", "dataset_name": output_dir.name, "seed": seed,
            "total_transactions": len(sim.txs), "observation_rows": len(records),
            "wallets": len(used), "illicit_wallets": n_ill_addr,
            "illicit_wallet_share": round(n_ill_addr / max(len(used), 1), 4),
            "illicit_transactions": sum(1 for t in sim.txs if t["illicit"]),
            "entities": dict(Counter(e.typology for e in sim.entities.values())),
            "tx_classes": dict(Counter(t["tx_class"] for t in sim.txs)),
            "seed_wallets": len(seeds), "known_entity_addresses": len(known_rows), "known_illicit_entities": len(known), "illicit_entities": len(illicit_ents),
            "csv_sha256": hashlib.sha256((output_dir / "transactions.csv").read_bytes()).hexdigest(),
        }
        (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        return manifest
