import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "Financial Transaction Ledger with Real-Time Fraud Triage"
    DEBUG: bool = True
    
    # PostgreSQL Database Settings (Primary Source of Truth)
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "ledger_db")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "ledger_user")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "ledger_password")

    # Redis Settings
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    
    # MongoDB Settings
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "fraud_triage_db")

    # ML Model Settings
    MODEL_PATH: str = os.getenv("MODEL_PATH", "backend/app/fraud/isolation_forest.joblib")
    MODEL_VERSION: str = "if-v1.0"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
