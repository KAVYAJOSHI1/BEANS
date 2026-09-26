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
    
    # Alert list
    ALERT_MIN_PROBABILITY: float = 0.40   # a wallet becomes an alert candidate at this calibrated P(illicit)
    MAX_ALERTS: int = 300                 # one alert per cluster, highest risk first

    # Network & Velocity Constraints
    IMPOSSIBLE_TRAVEL_KMH: float = 900.0  # Max realistic commercial flight speed
    # first-spy confidence = 1 - exp(-Δt / τ), Δt = gap to the second relay. Model feature: retrain after changing.
    FIRST_SPY_TAU_SEC: float = 1.5

    # Action directive rules (beans/decision/actions.py)
    ACTION_FREEZE_WINDOW_MIN: float = 30.0  # exchange deposit within this many minutes of receipt → freeze draft
    ACTION_FREEZE_MIN_RISK: float = 65.0    # … and at least this risk
    ACTION_MAX_HOPS: int = 4                # how far funds are traced forward to an exchange
    ACTION_LAYERING_MIN_BTC: float = 1.0    # FIU referral: value moved by the cluster
    ACTION_DORMANT_H: float = 6.0           # taint watch: unspent balance idle at least this long
    ACTION_SEED_LINK_HOPS: int = 4          # taint watch: "linked to a seed" = taint > 0 or within this many hops
    ACTION_MIN_PEEL_CHAIN: int = 3          # FIU referral: a peel chain this long counts as layering
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = BeansSettings()

# Module-level path aliases for contract compatibility
BASE_DIR = settings.BASE_DIR
DATA_DIR = settings.DATA_DIR
DB_PATH = settings.DB_PATH
GEOIP_DIR = settings.GEOIP_DIR
INTEL_DIR = settings.INTEL_DIR
SEEDS_DIR = settings.SEEDS_DIR
SYNTH_DIR = settings.SYNTH_DIR
MODELS_DIR = settings.MODELS_DIR
QUARANTINE_FILE = settings.QUARANTINE_FILE
