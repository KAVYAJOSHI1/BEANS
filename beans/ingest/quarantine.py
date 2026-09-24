import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from beans.config import settings

class QuarantineLogger:
    """
    Logs invalid or corrupt input rows to quarantine.csv with explicit diagnostic reasons (R1).
    """

    @classmethod
    def log_bad_row(cls, row_data: Any, error_reason: str, source_file: str = "unknown"):
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        file_path = settings.QUARANTINE_FILE
        file_exists = file_path.exists()

        with open(file_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["quarantine_timestamp", "source_file", "error_reason", "raw_payload"])
            
            writer.writerow([
                datetime.utcnow().isoformat(),
                source_file,
                error_reason,
                str(row_data)[:1000]
            ])
