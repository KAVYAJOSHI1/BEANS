import os
from pydantic_settings import BaseSettings if "BaseSettings" in globals() else object

class Settings:
    PROJECT_NAME: str = "Blockchain Forensics Intelligence Framework (BEANS)"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    
    # Database: SQLite by default for plug-and-play zero config, or PostgreSQL if DATABASE_URL provided
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./forensics.db")
    
    # Forensic Scoring Weights (Configurable, no hardcoded scores)
    WEIGHT_PATTERN: float = 40.0
    WEIGHT_OSINT: float = 30.0
    WEIGHT_SIGINT_GEO: float = 20.0
    WEIGHT_TEMPORAL_VELOCITY: float = 10.0
    
    # Correlation Thresholds
    CORRELATION_TIME_WINDOW_SEC: int = 180  # Max delta between tx broadcast and observed IP log
    GEO_VELOCITY_ANOMALY_KMH: float = 900.0  # Impossible travel threshold (commercial flight speed)
    COINJOIN_MIN_EQUAL_OUTPUTS: int = 3     # Min equal outputs to trigger CoinJoin entropy check
    FAN_OUT_RATIO_THRESHOLD: float = 5.0    # Ratio of outputs to inputs indicating rapid fan-out
    
    # Risk Categories
    RISK_CRITICAL_MIN: float = 80.0
    RISK_HIGH_MIN: float = 60.0
    RISK_MEDIUM_MIN: float = 35.0

settings = Settings()
