import os
import re
import socket
import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from typing import Generator, Any, Tuple
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None
from backend.app.config import settings

logger = logging.getLogger(__name__)

def _is_port_open(host: str, port: int, timeout: float = 0.15) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False

class SQLiteCursorWrapper:
    """Cursor wrapper that translates PostgreSQL SQL dialect to SQLite 3."""
    def __init__(self, cursor):
        self._cur = cursor

    def execute(self, query, params=None):
        if re.match(r'^\s*SET\s+', query, flags=re.IGNORECASE):
            return self
        q = query.replace('%s', '?')
        q = re.sub(r'\s+FOR\s+UPDATE\b', '', q, flags=re.IGNORECASE)
        q = re.sub(r"\bNOW\(\)\s*-\s*INTERVAL\s*'30\s*days'", "datetime('now', '-30 days')", q, flags=re.IGNORECASE)
        q = re.sub(r'\bNOW\(\)', "datetime('now')", q, flags=re.IGNORECASE)
        q = re.sub(r'EXTRACT\(HOUR FROM ([^)]+)\)', r"cast(strftime('%H', \1) as integer)", q, flags=re.IGNORECASE)
        q = re.sub(r'(?<!")\bTRANSACTION\b(?!")', '"TRANSACTION"', q, flags=re.IGNORECASE)
        # Handle PostgreSQL RETURNING in SQLite
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
    Primary Database Manager targeting PostgreSQL 15+ with automatic local SQLite fallback.
    Manages connections, transaction scopes, and schema initialization.
    """
    def __init__(self):
        self.host = settings.POSTGRES_HOST
        self.port = settings.POSTGRES_PORT
        self.db_name = settings.POSTGRES_DB
        self.user = settings.POSTGRES_USER
        self.password = settings.POSTGRES_PASSWORD
        self.use_postgres = True
        self._use_sqlite = None

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        candidate_path = os.path.join(base_dir, "ledger.db")
        if os.path.exists(candidate_path):
            self.sqlite_path = candidate_path
        else:
            self.sqlite_path = os.path.abspath("ledger.db")

    def _init_sqlite_schema(self, conn):
        """Initializes SQLite schema matching branch2 specifications."""
        cur = conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS CUSTOMER (
                customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                kyc_status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS DEVICE (
                device_id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                fingerprint TEXT NOT NULL UNIQUE,
                first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES CUSTOMER(customer_id)
            );

            CREATE TABLE IF NOT EXISTS MERCHANT (
                merchant_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT,
                country TEXT DEFAULT 'IN',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS ACCOUNT (
                account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                account_type TEXT NOT NULL,
                balance REAL NOT NULL DEFAULT 0.00,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES CUSTOMER(customer_id)
            );

            CREATE TABLE IF NOT EXISTS "TRANSACTION" (
                txn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER,
                merchant_id INTEGER,
                txn_type TEXT NOT NULL DEFAULT 'TRANSFER',
                status TEXT NOT NULL DEFAULT 'PENDING',
                initiated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (device_id) REFERENCES DEVICE(device_id),
                FOREIGN KEY (merchant_id) REFERENCES MERCHANT(merchant_id)
            );

            CREATE TABLE IF NOT EXISTS LEDGER_ENTRY (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                txn_id INTEGER NOT NULL,
                direction TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES ACCOUNT(account_id),
                FOREIGN KEY (txn_id) REFERENCES "TRANSACTION"(txn_id)
            );

            CREATE TABLE IF NOT EXISTS FRAUD_RESULT (
                result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                txn_id INTEGER NOT NULL,
                risk_score INTEGER NOT NULL,
                decision TEXT NOT NULL,
                model_version TEXT NOT NULL,
                features_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (txn_id) REFERENCES "TRANSACTION"(txn_id)
            );

            CREATE TABLE IF NOT EXISTS FRAUD_ALERT (
                alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
                result_id INTEGER NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (result_id) REFERENCES FRAUD_RESULT(result_id)
            );

            CREATE TABLE IF NOT EXISTS ANALYST (
                analyst_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                role TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS ANALYST_REVIEW (
                review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id INTEGER NOT NULL,
                analyst_id INTEGER NOT NULL,
                decision TEXT NOT NULL,
                reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (alert_id) REFERENCES FRAUD_ALERT(alert_id),
                FOREIGN KEY (analyst_id) REFERENCES ANALYST(analyst_id)
            );

            CREATE TABLE IF NOT EXISTS AUDIT_LOG (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT NOT NULL,
                operation TEXT NOT NULL,
                old_data TEXT,
                new_data TEXT,
                prev_hash TEXT,
                row_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS OUTBOX (
                outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
                txn_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                attempts INTEGER DEFAULT 0,
                last_attempt_at TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            DROP VIEW IF EXISTS mv_account_balances;
            CREATE VIEW mv_account_balances AS
            SELECT 
                a.account_id,
                a.customer_id,
                a.account_type,
                a.status,
                a.balance AS cached_balance,
                COALESCE(SUM(CASE WHEN l.direction = 'CREDIT' THEN l.amount ELSE -l.amount END), 0.00) AS calculated_ledger_balance,
                COUNT(l.entry_id) AS total_ledger_entries,
                MAX(l.created_at) AS last_activity_at
            FROM ACCOUNT a
            LEFT JOIN LEDGER_ENTRY l ON a.account_id = l.account_id
            GROUP BY a.account_id, a.customer_id, a.account_type, a.status, a.balance;

            DROP VIEW IF EXISTS mv_daily_transaction_summary;
            CREATE VIEW mv_daily_transaction_summary AS
            SELECT 
                DATE(t.initiated_at) AS summary_date,
                t.txn_type,
                t.status,
                COUNT(t.txn_id) AS total_transactions,
                COALESCE(SUM(l.amount), 0.00) AS total_volume,
                COALESCE(AVG(l.amount), 0.00) AS avg_amount,
                COUNT(fa.alert_id) AS total_alerts
            FROM "TRANSACTION" t
            LEFT JOIN LEDGER_ENTRY l ON t.txn_id = l.txn_id AND l.direction = 'DEBIT'
            LEFT JOIN FRAUD_RESULT fr ON t.txn_id = fr.txn_id
            LEFT JOIN FRAUD_ALERT fa ON fr.result_id = fa.result_id
            GROUP BY DATE(t.initiated_at), t.txn_type, t.status;
        """)
        conn.commit()

    def init_db(self):
        """Initializes database schema, partitions, indexes, and triggers."""
        # Detect database backend
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
        except Exception:
            pass

        if self._use_sqlite:
            conn = sqlite3.connect(self.sqlite_path)
            self._init_sqlite_schema(conn)
            conn.close()
            logger.info(f"SQLite database schema & views initialized successfully ({self.sqlite_path}).")
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

        # Attempt PostgreSQL connection if port is open
        if psycopg2 is not None and _is_port_open(self.host, self.port):
            try:
                conn = psycopg2.connect(
                    host=self.host,
                    port=self.port,
                    dbname=self.db_name,
                    user=self.user,
                    password=self.password,
                    connect_timeout=2,
                    cursor_factory=RealDictCursor
                )
                self._use_sqlite = False
                try:
                    yield conn
                finally:
                    conn.close()
                return
            except Exception as pg_err:
                logger.info(f"PostgreSQL connection failed ({pg_err}). Switching to local SQLite fallback.")
                self._use_sqlite = True
                self.use_postgres = False
        else:
            if self._use_sqlite is None:
                logger.info("PostgreSQL service not detected on localhost:5432. Active fallback: SQLite (ledger.db).")
                self._use_sqlite = True
                self.use_postgres = False

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
