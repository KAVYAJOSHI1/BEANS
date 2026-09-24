import json
from pathlib import Path
from typing import Generator, Tuple, Optional
from datetime import datetime
from beans.schema import CanonicalRecord
from beans.ingest.mapping import ColumnMapper
from beans.ingest.quarantine import QuarantineLogger

class StreamingJSONParser:
    """
    Parses JSON array or NDJSON (JSON Lines) files in streaming mode.
    """

    def __init__(self, mapper: Optional[ColumnMapper] = None):
        self.mapper = mapper or ColumnMapper()

    def parse(self, file_path: Path) -> Generator[CanonicalRecord, None, Tuple[int, int]]:
        total = 0
        valid = 0

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            # Check if JSON array or NDJSON
            first_char = ""
            while True:
                ch = f.read(1)
                if not ch:
                    break
                if not ch.isspace():
                    first_char = ch
                    break
            f.seek(0)

            if first_char == "[":
                # JSON array format
                try:
                    data = json.load(f)
                    for item in data:
                        total += 1
                        rec = self._process_dict(item, file_path)
                        if rec:
                            valid += 1
                            yield rec
                except Exception as e:
                    QuarantineLogger.log_bad_row(f"Entire JSON parse error: {str(e)}", "INVALID_JSON_FILE", str(file_path))
            else:
                # NDJSON line-by-line format
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    total += 1
                    try:
                        item = json.loads(line)
                        rec = self._process_dict(item, file_path)
                        if rec:
                            valid += 1
                            yield rec
                    except Exception as e:
                        QuarantineLogger.log_bad_row(line, f"NDJSON line parse error: {str(e)}", str(file_path))

        return total, valid

    def _process_dict(self, raw_item: dict, file_path: Path) -> Optional[CanonicalRecord]:
        try:
            norm = self.mapper.normalize_row(raw_item)
            ts = norm.get("timestamp")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            
            in_amts = [float(x) for x in norm.get("input_amounts", [])]
            out_amts = [float(x) for x in norm.get("output_amounts", [])]

            record = CanonicalRecord(
                timestamp=ts,
                src_ip=str(norm.get("src_ip", "127.0.0.1")).strip(),
                src_port=int(norm.get("src_port", 8333)),
                dst_ip=str(norm.get("dst_ip", "")) if norm.get("dst_ip") else None,
                dst_port=int(norm.get("dst_port", 8333)),
                txid=str(norm.get("txid", "")).strip(),
                input_addresses=[str(a) for a in norm.get("input_addresses", [])],
                input_amounts=in_amts,
                output_addresses=[str(a) for a in norm.get("output_addresses", [])],
                output_amounts=out_amts,
                fee=float(norm.get("fee", 0.0)),
                script_type=norm.get("script_type", "P2WPKH")
            )
            return record
        except Exception as e:
            QuarantineLogger.log_bad_row(raw_item, f"JSON record validation error: {str(e)}", str(file_path))
            return None
