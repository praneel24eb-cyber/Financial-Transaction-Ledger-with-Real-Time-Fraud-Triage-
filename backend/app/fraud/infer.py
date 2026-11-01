import os
import joblib
import numpy as np
import logging
from typing import Dict, Any, Tuple
from backend.app.config import settings

logger = logging.getLogger(__name__)

class FraudInferenceEngine:
    def __init__(self):
        self.model_meta = None
        self._load_model()

    def _load_model(self):
        if not os.path.exists(settings.MODEL_PATH):
            logger.warning(f"IsolationForest model file not found at {settings.MODEL_PATH}.")
            self.model_meta = None
            return

        try:
            self.model_meta = joblib.load(settings.MODEL_PATH)
            logger.info(f"Loaded IsolationForest model version {self.model_meta.get('version')}")
        except Exception as e:
            logger.error(f"Error loading fraud model file ({e}). Model set to None for fail-safe fallback.")
            self.model_meta = None

    def score_transaction(self, feature_dict: Dict[str, Any]) -> Tuple[int, str, str]:
        """
        Scores a feature vector using Isolation Forest.
        Features: [amount, velocity_1h, deviation_30d_pct, hour_of_day, location_change]
        
        Fail-Safe Policy:
        If model loading or inference fails for any reason, the transaction is routed
        to manual review (risk_score = 65, decision = 'ALERT', version = 'FAILSAFE_FALLBACK')
        rather than blindly approving or throwing an unhandled exception.
        """
        # Check model availability for fail-safe fallback
        if self.model_meta is None or "model" not in self.model_meta:
            logger.warning("Fraud model unavailable. Applying fail-safe fallback: routing to manual review (REVIEW).")
            return 65, "REVIEW", "FAILSAFE_FALLBACK"

        try:
            loc_val = feature_dict.get("location_change", feature_dict.get("device_changed", 0.0))

            X = np.array([[
                feature_dict["amount"],
                feature_dict["velocity_1h"],
                feature_dict["deviation_30d_pct"],
                feature_dict["hour_of_day"],
                loc_val
            ]])

            model = self.model_meta["model"]
            min_score = self.model_meta.get("min_score", -0.5)
            max_score = self.model_meta.get("max_score", 0.5)
            version = self.model_meta.get("version", settings.MODEL_VERSION)

            # Raw anomaly score (more negative = more anomalous)
            raw_score = float(model.decision_function(X)[0])

            # Min-Max Normalization & Inversion to 0-100 range
            if max_score > min_score:
                norm = (raw_score - min_score) / (max_score - min_score)
                risk_score = int(round((1.0 - norm) * 100.0))
            else:
                risk_score = 50

            risk_score = max(0, min(100, risk_score))

            # Overrides for high-risk flags
            if feature_dict["amount"] >= 50000 or (loc_val == 1.0 and feature_dict["amount"] >= 20000):
                risk_score = max(risk_score, 85)
            elif feature_dict["velocity_1h"] >= 8:
                risk_score = max(risk_score, 75)

            # 3-Tier Policy per FR-17: APPROVE (<50), REVIEW (50-80), ROLLBACK (>80)
            if risk_score < 50:
                decision = "APPROVE"
            elif 50 <= risk_score <= 80:
                decision = "REVIEW"
            else:
                decision = "ROLLBACK"

            return risk_score, decision, version

        except Exception as err:
            logger.error(f"Inference error ({err}). Applying fail-safe fallback: routing to manual review (REVIEW).")
            return 65, "REVIEW", "FAILSAFE_FALLBACK"


fraud_engine = FraudInferenceEngine()
