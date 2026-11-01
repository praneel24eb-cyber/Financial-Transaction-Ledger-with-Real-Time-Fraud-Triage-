import pytest
from backend.app.fraud.infer import fraud_engine, FraudInferenceEngine
from backend.app.services.ledger_service import ledger_service
from backend.app.repositories.db import db_manager
from backend.app.database.seed import seed_database
from fastapi import HTTPException

@pytest.fixture(autouse=True)
def setup_db():
    try:
        seed_database()
    except Exception:
        pass
    yield

def test_fraud_scoring_normal_transaction():
    features = {
        "amount": 250.0,
        "velocity_1h": 1,
        "deviation_30d_pct": 10.0,
        "hour_of_day": 14,
        "location_change": 0.0,
        "device_changed": 0.0
    }
    risk_score, decision, version = fraud_engine.score_transaction(features)
    assert risk_score < 50
    assert decision == "APPROVE"

def test_fraud_model_failure_failsafe_fallback():
    # Force model exception by setting model_meta to None
    original_meta = fraud_engine.model_meta
    try:
        fraud_engine.model_meta = None
        features = {
            "amount": 100.0,
            "velocity_1h": 1,
            "deviation_30d_pct": 0.0,
            "hour_of_day": 12,
            "location_change": 0.0
        }
        risk_score, decision, version = fraud_engine.score_transaction(features)
        
        # Assert fail-safe manual review fallback (50-80 band per FR-17)
        assert risk_score == 65
        assert decision == "REVIEW"
        assert version == "FAILSAFE_FALLBACK"
    finally:
        fraud_engine.model_meta = original_meta
