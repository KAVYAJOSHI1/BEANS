import csv
import json
from pathlib import Path
from typing import Generator, Tuple, Optional, List
from datetime import datetime
from beans.schema import CanonicalRecord
from beans.ingest.mapping import ColumnMapper
from beans.ingest.quarantine import QuarantineLogger

def _parse_list_field(val: any, target_type=str) -> List:
    if val is None or val == "":
        return []
    if isinstance(val, list):
        return [target_type(x) for x in val]
    if isinstance(val, str):
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            try:
                parsed = json.loads(val)
                return [target_type(x) for x in parsed]
            except Exception:
                pass
        # Semicolon or comma separated
        parts = [p.strip() for p in val.replace(";", ",").split(",") if p.strip()]
        return [target_type(p) for p in parts]
    return [target_type(val)]

class StreamingCSVParser:
    """
    Streams CSV records with high throughput, parses array fields, validates against CanonicalRecord.
    """

    def __init__(self, mapper: Optional[ColumnMapper] = None):
        self.mapper = mapper or ColumnMapper()

    def parse(self, file_path: Path) -> Generator[CanonicalRecord, None, Tuple[int, int]]:
        """Yields valid records; invalid rows go to quarantine with the reason. Counts in self.total / self.valid."""
        self.total = self.valid = 0
        with open(file_path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
            for row in csv.DictReader(f):
                self.total += 1
                try:
                    rec = self.mapper.build_record(row)
                except Exception as e:
                    QuarantineLogger.log_bad_row(row, f"CSV row rejected: {e}", str(file_path))
                    continue
                self.valid += 1
                yield rec
        return self.total, self.valid
