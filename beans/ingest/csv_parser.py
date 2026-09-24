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
        """
        Yields valid CanonicalRecord objects.
        Returns total_processed, valid_count upon completion.
        """
        total = 0
        valid = 0

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total += 1
                norm_row = self.mapper.normalize_row(row)
                
                try:
                    # Convert types
                    ts = norm_row.get("timestamp")
                    if isinstance(ts, str):
                        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    
                    in_addrs = _parse_list_field(norm_row.get("input_addresses", []), str)
                    in_amts = _parse_list_field(norm_row.get("input_amounts", []), float)
                    out_addrs = _parse_list_field(norm_row.get("output_addresses", []), str)
                    out_amts = _parse_list_field(norm_row.get("output_amounts", []), float)
                    
                    record = CanonicalRecord(
                        timestamp=ts,
                        src_ip=str(norm_row.get("src_ip", "127.0.0.1")).strip(),
                        src_port=int(norm_row.get("src_port", 8333)),
                        dst_ip=str(norm_row.get("dst_ip", "")) if norm_row.get("dst_ip") else None,
                        dst_port=int(norm_row.get("dst_port", 8333)),
                        txid=str(norm_row.get("txid", "")).strip(),
                        input_addresses=in_addrs,
                        input_amounts=in_amts,
                        output_addresses=out_addrs,
                        output_amounts=out_amts,
                        fee=float(norm_row.get("fee", 0.0)),
                        script_type=norm_row.get("script_type", "P2WPKH")
                    )
                    valid += 1
                    yield record
                except Exception as e:
                    QuarantineLogger.log_bad_row(row, f"CSV Parse/Validation Error: {str(e)}", str(file_path))

        return total, valid
