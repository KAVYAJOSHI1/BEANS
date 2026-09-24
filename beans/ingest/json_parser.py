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
        self.total = self.valid = 0

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
                        self.total = total
                        rec = self._process_dict(item, file_path)
                        if rec:
                            valid += 1
                            self.valid = valid
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
                    self.total = total
                    try:
                        item = json.loads(line)
                        rec = self._process_dict(item, file_path)
                        if rec:
                            valid += 1
                            self.valid = valid
                            yield rec
                    except Exception as e:
                        QuarantineLogger.log_bad_row(line, f"NDJSON line parse error: {str(e)}", str(file_path))

        return total, valid

    def _process_dict(self, raw_item: dict, file_path: Path) -> Optional[CanonicalRecord]:
        try:
            return self.mapper.build_record(raw_item)
        except Exception as e:
            QuarantineLogger.log_bad_row(raw_item, f"JSON record rejected: {e}", str(file_path))
            return None
