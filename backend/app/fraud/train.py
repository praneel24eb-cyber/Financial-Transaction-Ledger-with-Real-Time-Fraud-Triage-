import os
import joblib
import numpy as np
import logging
from sklearn.ensemble import IsolationForest
from backend.app.config import settings
from backend.app.repositories.db import db_manager

logger = logging.getLogger(__name__)

def train_isolation_forest_model():
    """
    Fits the IsolationForest model on generated transaction dataset in PostgreSQL.
    Features: [amount, velocity_1h, deviation_30d_pct, hour_of_day, location_change]
    Serializes model artifact to settings.MODEL_PATH tagged with model_version.
    """
    logger.info("Extracting feature vectors from database to train IsolationForest...")

    feature_matrix = []

    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Query historical transaction legs joined with device and merchant data
                query = """
                    SELECT 
                        l.amount,
                        EXTRACT(HOUR FROM t.initiated_at) as hour_of_day,
                        COALESCE(m.country, 'IN') as merchant_country,
                        t.device_id,
                        l.account_id
                    FROM LEDGER_ENTRY l
                    JOIN TRANSACTION t ON l.txn_id = t.txn_id
                    LEFT JOIN MERCHANT m ON t.merchant_id = m.merchant_id
                    WHERE l.direction = 'DEBIT';
                """
                cur.execute(query)
                rows = cur.fetchall()

                for r in rows:
                    amt = float(r['amount'])
                    hr = float(r['hour_of_day']) if r['hour_of_day'] is not None else 12.0
                    loc_change = 1.0 if r['merchant_country'] != 'IN' else 0.0
                    # Velocity & deviation estimates from seeded data
                    vel = 1.0 if amt < 10000 else 5.0
                    dev = 10.0 if amt < 10000 else 250.0
                    feature_matrix.append([amt, vel, dev, hr, loc_change])
    except Exception as e:
        logger.warning(f"Could not read historical DB rows for training ({e}). Synthetic fallback generated.")

    # Generate robust training dataset if DB records are minimal
    np.random.seed(42)
    n_normal = 1000
    n_anomaly = 50  # ~5% injected anomalous patterns

    # Normal pattern distribution
    normal_amt = np.random.exponential(scale=1000, size=n_normal) + 50
    normal_vel = np.random.poisson(lam=1.5, size=n_normal) + 1
    normal_dev = np.random.exponential(scale=15, size=n_normal)
    normal_hr = np.random.randint(8, 22, size=n_normal)
    normal_loc = np.zeros(n_normal)

    # Injected anomalous patterns (high amounts, high velocity, night hours, foreign merchant location)
    anom_amt = np.random.uniform(20000, 100000, size=n_anomaly)
    anom_vel = np.random.randint(6, 20, size=n_anomaly)
    anom_dev = np.random.uniform(200, 800, size=n_anomaly)
    anom_hr = np.random.choice([1, 2, 3, 4, 23], size=n_anomaly)
    anom_loc = np.ones(n_anomaly)

    syn_X = np.column_stack([
        np.concatenate([normal_amt, anom_amt]),
        np.concatenate([normal_vel, anom_vel]),
        np.concatenate([normal_dev, anom_dev]),
        np.concatenate([normal_hr, anom_hr]),
        np.concatenate([normal_loc, anom_loc])
    ])

    if feature_matrix:
        db_X = np.array(feature_matrix)
        X = np.vstack([db_X, syn_X])
    else:
        X = syn_X

    # Fit Isolation Forest
    model = IsolationForest(
        n_estimators=100,
        contamination=0.05,
        random_state=42
    )
    model.fit(X)

    # Compute bounds for min-max scaling
    scores = model.decision_function(X)
    min_score = float(np.min(scores))
    max_score = float(np.max(scores))

    model_metadata = {
        "model": model,
        "min_score": min_score,
        "max_score": max_score,
        "version": settings.MODEL_VERSION
    }

    os.makedirs(os.path.dirname(settings.MODEL_PATH), exist_ok=True)
    joblib.dump(model_metadata, settings.MODEL_PATH)
    logger.info(f"Successfully trained and serialized IsolationForest model to {settings.MODEL_PATH} (version: {settings.MODEL_VERSION})")

if __name__ == "__main__":
    train_isolation_forest_model()
