from datetime import datetime
import logging
from typing import Dict, Any, Optional
from backend.app.repositories.db import db_manager
from backend.app.repositories.redis_repo import redis_repo

logger = logging.getLogger(__name__)

def extract_fraud_features(
    source_account_id: int,
    amount: float,
    device_id: int,
    merchant_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Extracts the 5 core features specified in the PRD for real-time fraud triage:
    1. amount: Transaction amount (₹).
    2. velocity_1h: Rolling 1-hour transaction velocity (from Redis atomic INCR counter).
    3. deviation_30d_pct: Percentage deviation from account's 30-day average transaction amount.
    4. hour_of_day: Time-of-day feature (0-23).
    5. location_change: Binary flag (1 if merchant country differs from customer home country 'IN' or foreign location, 0 otherwise).
    
    Implementation Note:
    'device_changed' is also extracted as a supporting fingerprint flag. 'location_change' is derived from
    MERCHANT.country inspection relative to the customer's registered country.
    """
    now = datetime.now()
    hour_of_day = float(now.hour)

    # 1. Rolling Velocity (1-hour window from Redis)
    velocity_1h = float(redis_repo.get_velocity(source_account_id, window_seconds=3600) + 1)

    # 2. Known device check
    is_known_device = redis_repo.is_known_device(source_account_id, device_id)
    device_changed = 0.0 if is_known_device else 1.0

    # 3. Location Change check (inspect merchant country vs home country 'IN')
    location_change = 0.0
    avg_amount_30d = 0.0

    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            # 30-day average calculation
            avg_query = """
                SELECT AVG(l.amount) as avg_amt
                FROM LEDGER_ENTRY l
                WHERE l.account_id = %s
                  AND l.direction = 'DEBIT'
                  AND l.created_at >= NOW() - INTERVAL '30 days';
            """
            cur.execute(avg_query, (source_account_id,))
            row = cur.fetchone()
            if row and row['avg_amt'] is not None:
                avg_amount_30d = float(row['avg_amt'])

            # Location check if merchant_id provided
            if merchant_id:
                cur.execute("SELECT country FROM MERCHANT WHERE merchant_id = %s;", (merchant_id,))
                mrow = cur.fetchone()
                if mrow and mrow['country'] and mrow['country'] != 'IN':
                    location_change = 1.0

    # Compute deviation percentage
    if avg_amount_30d > 0:
        deviation_30d_pct = max(0.0, ((amount - avg_amount_30d) / avg_amount_30d) * 100.0)
    else:
        deviation_30d_pct = 0.0

    # If device changed and high amount, mark location/device anomaly
    if device_changed == 1.0 and location_change == 0.0 and amount >= 25000:
        location_change = 1.0

    return {
        "amount": float(amount),
        "velocity_1h": velocity_1h,
        "deviation_30d_pct": float(deviation_30d_pct),
        "hour_of_day": hour_of_day,
        "location_change": float(location_change),
        "device_changed": device_changed,
        "avg_amount_30d": float(avg_amount_30d)
    }
