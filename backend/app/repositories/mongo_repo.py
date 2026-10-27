import logging
from typing import Dict, Any, Optional, List
try:
    import pymongo
except ImportError:
    pymongo = None

from backend.app.config import settings

logger = logging.getLogger(__name__)

class MongoRepository:
    def __init__(self):
        self.enabled = False
        self._memory_evidence = {}
        self._memory_events = {}

        if pymongo is not None:
            try:
                self.client = pymongo.MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=1000)
                self.client.admin.command('ping')
                self.db = self.client[settings.MONGO_DB_NAME]
                self.evidence_col = self.db["fraud_evidence"]
                self.events_col = self.db["raw_events"]
                self.enabled = True
                logger.info("Connected to MongoDB 6+")
            except Exception as e:
                logger.warning(f"MongoDB unavailable ({e}). Using in-memory store for fraud evidence documents.")
        else:
            logger.info("pymongo package not installed. Using in-memory store for fraud evidence documents.")

    def upsert_alert_evidence(self, alert_id: int, evidence_doc: Dict[str, Any]):
        doc_id = int(alert_id)
        evidence_doc["_id"] = doc_id
        evidence_doc["alert_id"] = alert_id

        if self.enabled:
            try:
                self.evidence_col.replace_one({"_id": doc_id}, evidence_doc, upsert=True)
                return
            except Exception as e:
                logger.warning(f"MongoDB replace_one error: {e}")

        # In-memory fallback
        self._memory_evidence[doc_id] = evidence_doc

    def get_alert_evidence(self, alert_id: int) -> Optional[Dict[str, Any]]:
        doc_id = int(alert_id)
        if self.enabled:
            try:
                res = self.evidence_col.find_one({"_id": doc_id})
                return res
            except Exception as e:
                logger.warning(f"MongoDB find_one error: {e}")

        return self._memory_evidence.get(doc_id)

    # Backward compatibility aliases
    def upsert_fraud_evidence(self, txn_id: int, evidence_doc: Dict[str, Any]):
        doc_id = f"txn_{txn_id}"
        evidence_doc["_id"] = doc_id
        evidence_doc["txn_id"] = txn_id

        if self.enabled:
            try:
                self.evidence_col.replace_one({"_id": doc_id}, evidence_doc, upsert=True)
                return
            except Exception as e:
                logger.warning(f"MongoDB replace_one error: {e}")

        self._memory_evidence[doc_id] = evidence_doc

    def get_fraud_evidence(self, txn_id: int) -> Optional[Dict[str, Any]]:
        doc_id = f"txn_{txn_id}"
        if self.enabled:
            try:
                res = self.evidence_col.find_one({"_id": doc_id})
                return res
            except Exception as e:
                logger.warning(f"MongoDB find_one error: {e}")

        return self._memory_evidence.get(doc_id)

    def insert_raw_event(self, event_id: int, event_doc: Dict[str, Any]):
        doc_id = f"event_{event_id}"
        event_doc["_id"] = doc_id
        if self.enabled:
            try:
                self.events_col.replace_one({"_id": doc_id}, event_doc, upsert=True)
                return
            except Exception as e:
                logger.warning(f"MongoDB insert raw event error: {e}")

        self._memory_events[doc_id] = event_doc

mongo_repo = MongoRepository()

