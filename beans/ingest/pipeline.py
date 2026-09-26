from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
import json

from beans.schema import CanonicalRecord
from beans.ingest.csv_parser import StreamingCSVParser
from beans.ingest.json_parser import StreamingJSONParser
from beans.ingest.xml_parser import StreamingXMLParser
from beans.enrich.geoip import OfflineGeoIPEnricher
from beans.store.duck import DuckStore

class ForensicPipeline:
    """
    Master pipeline executing the full ingestion -> enrich -> graph -> 5 engines -> fusion -> XAI -> alert cycle.
    """

    def __init__(self, store: Optional[DuckStore] = None, mapping: Optional[Path] = None):
        self.store = store or DuckStore()
        from beans.ingest.mapping import ColumnMapper
        self.mapper = ColumnMapper(mapping)
        self.enricher = OfflineGeoIPEnricher()

    def run_file_ingestion(self, file_path: Path) -> Dict[str, Any]:
        """Parses file (CSV/JSON/XML), enriches, stores, and runs full ML pipeline"""
        p = Path(file_path)
        suffix = p.suffix.lower()

        if suffix == ".csv":
            parser = StreamingCSVParser(self.mapper)
        elif suffix in [".json", ".ndjson", ".jsonl"]:
            parser = StreamingJSONParser(self.mapper)
        elif suffix == ".xml":
            parser = StreamingXMLParser()
        else:
            raise ValueError(f"Unsupported file extension: {suffix}")

        records: List[CanonicalRecord] = []
        for rec in parser.parse(p):
            geo = self.enricher.enrich(rec.src_ip)  # offline DB-IP country + ASN + infrastructure type
            rec.geo_country, rec.geo_city, rec.geo_lat, rec.geo_lon = geo["country"], geo["city"], geo["lat"], geo["lon"]
            rec.asn, rec.asn_name, rec.asn_type = geo["asn"], geo["asn_name"], geo["asn_type"]
            records.append(rec)

        self.store.insert_records(records)
        sidecars = self.load_sidecars(p.parent)
        pipeline_stats = self.execute_ml_pipeline(records)
        return {
            "file": p.name,
            "records_ingested": len(records),
            "rows_read": getattr(parser, "total", len(records)),
            "rows_quarantined": getattr(parser, "total", len(records)) - len(records),
            "sidecars_loaded": sidecars,
            "pipeline_stats": pipeline_stats
        }

    def load_sidecars(self, folder: Path) -> List[str]:
        """Seed list and (synthetic) ground truth shipped next to the input file."""
        loaded = []
        seeds = folder / "seeds.csv"
        if seeds.exists():
            import csv as _csv
            with open(seeds, newline="") as fh:
                cols = {c.strip().lower() for c in (next(_csv.reader(fh), []) or [])}
            if "address" in cols:   # tolerate minimal seed lists (address[,label])
                pick = lambda *names: next((n for n in names if n in cols), None)
                t, i, c, src = pick("threat_type", "label", "typology"), pick("incident_name", "incident"), \
                    pick("confidence"), pick("source")
                conn = self.store.get_connection()
                conn.execute(f"""INSERT OR REPLACE INTO seeds (address, threat_type, incident_name, confidence, source)
                    SELECT address, {t or "'UNKNOWN'"}, {i or "'seed list'"}, {f"TRY_CAST({c} AS DOUBLE)" if c else "0.9"},
                           {src or "'SEED_FILE'"}
                    FROM read_csv_auto(?, all_varchar=true)""", [str(seeds)])
                conn.close()
                loaded.append(seeds.name)
        known = folder / "known_entities.csv"
        if known.exists():
            self.store.load_known_entities(known)
            loaded.append(known.name)
        for name, table in (("labels_address.csv", "labels_address"), ("labels_tx.csv", "labels_tx")):
            if (folder / name).exists():
                self.store.load_sidecar(table, folder / name, [])
                loaded.append(name)
        return loaded

    def execute_ml_pipeline(self, records: Optional[List[CanonicalRecord]] = None) -> Dict[str, Any]:
        """Score the WHOLE database (all ingested files), not just the latest batch."""
        from beans.score.run import run_ml
        return run_ml(self.store)
