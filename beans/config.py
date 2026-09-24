import os
from pathlib import Path
from pydantic_settings import BaseSettings

class BeansSettings(BaseSettings):
    PROJECT_NAME: str = "BEANS — Bitcoin Forensic Intelligence Framework"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    
    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    DB_PATH: Path = DATA_DIR / "beans.duckdb"
    GEOIP_DIR: Path = DATA_DIR / "geoip"
    INTEL_DIR: Path = DATA_DIR / "intel"
    SEEDS_DIR: Path = DATA_DIR / "seeds"
    SYNTH_DIR: Path = DATA_DIR / "synth"
    MODELS_DIR: Path = BASE_DIR / "models"
    QUARANTINE_FILE: Path = DATA_DIR / "quarantine.csv"
    
    # Forensic Scoring Thresholds
    RISK_CRITICAL_MIN: float = 85.0
    RISK_HIGH_MIN: float = 65.0
    RISK_MEDIUM_MIN: float = 40.0
    
    # Network & Velocity Constraints
    IMPOSSIBLE_TRAVEL_KMH: float = 900.0  # Max realistic commercial flight speed
    FIRST_SPY_WINDOW_SEC: float = 120.0   # Propagation delta threshold
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = BeansSettings()
