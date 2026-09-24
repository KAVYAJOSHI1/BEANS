"""CSV/JSON/XML ingestion into DuckDB. OWNER: Dharmik."""
from pathlib import Path


def ingest_files(con, paths: list[Path], mapping: Path | None = None, reset: bool = False) -> dict:
    """Parse, validate (bad rows -> quarantine), enrich (GeoIP/ASN), and load net_obs/tx/tx_input/tx_output/
    wallet/ip. If a labels_*.csv / seeds.csv sits next to the input file, load those too.
    Returns {"rows_ok": int, "rows_bad": int, "files": [...]}."""
    raise NotImplementedError("Dharmik: beans.ingest.ingest_files")
