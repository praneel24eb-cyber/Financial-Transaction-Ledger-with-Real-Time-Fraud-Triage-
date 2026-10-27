import os
import re
import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from typing import Generator, Any, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
from backend.app.config import settings

logger = logging.getLogger(__name__)

class SQLiteCursorWrapper:
    """Cursor wrapper that translates PostgreSQL SQL dialect to SQLite 3."""
    def __init__(self, cursor):
        self._cur = cursor

    def execute(self, query, params=None):
        q = query.replace('%s', '?')
        q = re.sub(r'\s+FOR\s+UPDATE\b', '', q, flags=re.IGNORECASE)
        q = re.sub(r"\bNOW\(\)\s*-\s*INTERVAL\s*'30\s*days'", "datetime('now', '-30 days')", q, flags=re.IGNORECASE)
        q = re.sub(r'\bNOW\(\)', "datetime('now')", q, flags=re.IGNORECASE)
        q = re.sub(r'(?<!")\bTRANSACTION\b(?!")', '"TRANSACTION"', q, flags=re.IGNORECASE)
        if params is not None:
            if not isinstance(params, (list, tuple)):
                params = (params,)
            return self._cur.execute(q, params)
        return self._cur.execute(q)

    def fetchone(self):
        row = self._cur.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(r) for r in self._cur.fetchall()]

    def __iter__(self):
        for r in self._cur:
            yield dict(r)

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

class SQLiteConnectionWrapper:
    """Connection wrapper ensuring transaction semantics and dict rows."""
    def __init__(self, conn):
        self._conn = conn

    def cursor(self, *args, **kwargs):
        return SQLiteCursorWrapper(self._conn.cursor())

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._conn.rollback()
        else:
            self._conn.commit()

class DatabaseManager:
    """
    Unified Database Manager.
    Targets PostgreSQL 15+ by default, with automatic built-in SQLite fallback (ledger.db)
    when running locally without PostgreSQL service.
    """
    def __init__(self):
        self.host = settings.POSTGRES_HOST
        self.port = settings.POSTGRES_PORT
        self.db_name = settings.POSTGRES_DB
        self.user = settings.POSTGRES_USER
        self.password = settings.POSTGRES_PASSWORD
        
        # Locate local ledger.db
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        candidate_path = os.path.join(base_dir, "ledger.db")
        if os.path.exists(candidate_path):
            self.sqlite_path = candidate_path
        else:
            self.sqlite_path = os.path.abspath("ledger.db")
            
        self._use_sqlite = None

    def init_db(self):
        """Initializes database schema and triggers."""
        # Detect database backend
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
        except Exception:
            pass

        if self._use_sqlite:
            logger.info(f"SQLite fallback active ({self.sqlite_path}). Tables ready.")
            return

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
        if self._use_sqlite is True:
            conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            wrapper = SQLiteConnectionWrapper(conn)
            try:
                yield wrapper
            finally:
                wrapper.close()
            return

        # Attempt PostgreSQL connection
        try:
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                dbname=self.db_name,
                user=self.user,
                password=self.password,
                connect_timeout=1,
                cursor_factory=RealDictCursor
            )
            self._use_sqlite = False
            try:
                yield conn
            finally:
                conn.close()
        except Exception as pg_err:
            if self._use_sqlite is None:
                logger.info(f"PostgreSQL unavailable on localhost:5432 ({pg_err}). Switching to built-in SQLite fallback (ledger.db).")
                self._use_sqlite = True
            conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            wrapper = SQLiteConnectionWrapper(conn)
            try:
                yield wrapper
            finally:
                wrapper.close()

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
