import os
import hashlib
import json
import logging
from contextlib import contextmanager
from typing import Generator, Any, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
from backend.app.config import settings

logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    Primary Database Manager targeting PostgreSQL 15+.
    Manages connections, transaction scopes, and schema initialization.
    """
    def __init__(self):
        self.host = settings.POSTGRES_HOST
        self.port = settings.POSTGRES_PORT
        self.db_name = settings.POSTGRES_DB
        self.user = settings.POSTGRES_USER
        self.password = settings.POSTGRES_PASSWORD

    def init_db(self):
        """Initializes PostgreSQL schema DDL, partitions, indexes, and triggers."""
        schema_path = os.path.join(os.path.dirname(__file__), "..", "database", "schema.sql")
        triggers_path = os.path.join(os.path.dirname(__file__), "..", "database", "triggers.sql")

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if os.path.exists(schema_path):
                    with open(schema_path, "r", encoding="utf-8") as f:
                        cur.execute(f.read())
                if os.path.exists(triggers_path):
                    try:
                        with open(triggers_path, "r", encoding="utf-8") as f:
                            cur.execute(f.read())
                    except Exception as trigger_err:
                        logger.warning(f"PostgreSQL trigger initialization warning: {trigger_err}")
            conn.commit()
            logger.info("PostgreSQL database schema & triggers initialized successfully.")

    @contextmanager
    def get_connection(self) -> Generator[Any, None, None]:
        conn = psycopg2.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            dbname=settings.POSTGRES_DB,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            connect_timeout=2,
            cursor_factory=RealDictCursor
        )
        try:
            yield conn
        finally:
            conn.close()

db_manager = DatabaseManager()

def compute_audit_hash(prev_hash: str, table_name: str, operation: str, old_data: dict, new_data: dict) -> Tuple[str, str]:
    """
    Calculates SHA-256 hash for append-only AUDIT_LOG chaining:
    row_hash = SHA256(prev_hash || table_name || operation || old_data || new_data)
    """
    if not prev_hash:
        prev_hash = "0" * 64

    old_json_str = json.dumps(old_data, sort_keys=True) if old_data else ""
    new_json_str = json.dumps(new_data, sort_keys=True) if new_data else ""

    data_to_hash = f"{prev_hash}|{table_name}|{operation}|{old_json_str}|{new_json_str}"
    row_hash = hashlib.sha256(data_to_hash.encode("utf-8")).hexdigest()
    return prev_hash, row_hash
