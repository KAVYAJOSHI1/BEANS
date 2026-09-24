"""Paths and settings. Override any of them with environment variables (BEANS_*)."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("BEANS_ROOT", Path(__file__).resolve().parent.parent))
DATA_DIR = ROOT / "data"
DB_PATH = Path(os.environ.get("BEANS_DB", DATA_DIR / "beans.duckdb"))
GEOIP_COUNTRY = Path(os.environ.get("BEANS_GEOIP_COUNTRY", DATA_DIR / "geoip" / "dbip-country-lite.mmdb"))
GEOIP_ASN = Path(os.environ.get("BEANS_GEOIP_ASN", DATA_DIR / "geoip" / "dbip-asn-lite.mmdb"))
INTEL_DIR = DATA_DIR / "intel"
SEEDS_DIR = DATA_DIR / "seeds"
SYNTH_DIR = DATA_DIR / "synth"
MODELS_DIR = Path(os.environ.get("BEANS_MODELS", ROOT / "models"))
UI_DIST = ROOT / "ui" / "dist"

API_HOST = os.environ.get("BEANS_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("BEANS_PORT", "8000"))
MOCK = os.environ.get("BEANS_MOCK", "0") == "1"  # API serves data/samples/mock_*.json instead of the DB

RANDOM_SEED = int(os.environ.get("BEANS_SEED", "42"))
