import time
import json
import logging
from typing import List, Dict, Any
from backend.app.repositories.db import db_manager
from backend.app.repositories.redis_repo import redis_repo
from backend.app.repositories.mongo_repo import mongo_repo

logger = logging.getLogger(__name__)

"""
IDEMPOTENCY & REDELIVERY DESIGN NOTE:
- MongoDB Fraud Evidence & Raw Event Writes: Fully idempotent. Uses upsert-by-txn_id
  (`replace_one({"_id": f"txn_{txn_id}"}, ..., upsert=True)`).
- Redis Velocity Counter Writes: INCR operations are NOT strictly idempotent under
  true message redelivery (a retried event could increment velocity again).
  This is an accepted, documented trade-off for high-throughput fast counter caching in this project.
"""

class OutboxWorker:
    def __init__(self, max_attempts: int = 5):
        self.max_attempts = max_attempts

    def process_pending_events(self) -> int:
        """
        Polls OUTBOX table for events in PENDING state.
        Propagates events to Redis & MongoDB asynchronously.
        Returns the number of events processed.
        """
        processed_count = 0
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                query = """
                    SELECT outbox_id, txn_id, event_type, payload, status, attempts
                    FROM OUTBOX
                    WHERE status = 'PENDING' AND attempts < %s
                    ORDER BY outbox_id ASC
                    LIMIT 20;
                """
                cur.execute(query, (self.max_attempts,))
                rows = cur.fetchall()

                for r in rows:
                    outbox_id = r['outbox_id']
                    txn_id = r['txn_id']
                    event_type = r['event_type']
                    payload_raw = r['payload']
                    attempts = r['attempts']

                    payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw

                    success = self._dispatch_event(outbox_id, txn_id, event_type, payload)

                    if success:
                        cur.execute("UPDATE OUTBOX SET status = 'SENT' WHERE outbox_id = %s;", (outbox_id,))
                        processed_count += 1
                    else:
                        new_attempts = attempts + 1
                        new_status = 'FAILED' if new_attempts >= self.max_attempts else 'PENDING'
                        cur.execute("UPDATE OUTBOX SET status = %s, attempts = %s WHERE outbox_id = %s;", (new_status, new_attempts, outbox_id))

                conn.commit()

        return processed_count

    def _dispatch_event(self, outbox_id: int, txn_id: int, event_type: str, payload: Dict[str, Any]) -> bool:
        try:
            src_acc = payload.get("source_account_id")
            device_id = payload.get("device_id")
            merchant_id = payload.get("merchant_id")
            alert_id = payload.get("alert_id")

            # 1. Update Redis velocity and recent device/merchant history (FR-27, FR-28)
            if src_acc:
                redis_repo.increment_velocity(src_acc, window_seconds=600)
            if src_acc and device_id:
                redis_repo.add_recent_device(src_acc, device_id)
            if src_acc and merchant_id:
                redis_repo.add_recent_merchant(src_acc, merchant_id)

            # 2. MongoDB Alert Evidence Document (FR-29, ER schema: _id = alert_id)
            evidence_doc = {
                "alert_id": alert_id,
                "txn_id": txn_id,
                "outbox_id": outbox_id,
                "event_type": event_type,
                "risk_score": payload.get("risk_score"),
                "decision": payload.get("decision"),
                "model_version": payload.get("model_version", "if-v1.0"),
                "features": payload.get("features", {}),
                "rule_hits": ["HIGH_VELOCITY"] if (payload.get("features", {}).get("velocity_1h", 0) > 5) else [],
                "analyst_notes": "",
                "explanation": f"Isolation Forest score: {payload.get('risk_score')}/100 ({payload.get('decision')})",
                "raw_event_ref": f"outbox:{outbox_id}",
                "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }

            if alert_id:
                mongo_repo.upsert_alert_evidence(alert_id, evidence_doc)

            mongo_repo.upsert_fraud_evidence(txn_id, evidence_doc)
            mongo_repo.insert_raw_event(outbox_id, payload)

            return True
        except Exception as e:
            logger.warning(f"Failed to propagate outbox event {outbox_id} to Redis/Mongo: {e}")
            return False

outbox_worker = OutboxWorker()

def run_outbox_worker_loop(poll_interval: float = 2.0):
    logger.info("Starting Outbox Worker loop...")
    db_warned = False
    while True:
        try:
            count = outbox_worker.process_pending_events()
            if count > 0:
                logger.info(f"Outbox Worker processed {count} events successfully.")
            db_warned = False
        except Exception as e:
            err_msg = str(e)
            if "connection to server at" in err_msg or "timeout expired" in err_msg:
                if not db_warned:
                    logger.warning("Outbox Worker: PostgreSQL is offline. Waiting for database to connect...")
                    db_warned = True
                time.sleep(10.0)
            else:
                logger.error(f"Outbox Worker loop error: {e}")
                time.sleep(5.0)
            continue
        time.sleep(poll_interval)
