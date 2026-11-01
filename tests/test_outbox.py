import pytest
from backend.app.workers.outbox_worker import outbox_worker
from backend.app.services.ledger_service import ledger_service
from backend.app.repositories.db import db_manager
from backend.app.repositories.mongo_repo import mongo_repo
from backend.app.database.seed import seed_database

@pytest.fixture(autouse=True)
def setup_db():
    seed_database()
    yield

def test_outbox_event_lifecycle():
    # Fetch active accounts dynamically
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT account_id FROM ACCOUNT WHERE status = 'ACTIVE' LIMIT 2;")
        rows = cur.fetchall()
        src_id = rows[0]['account_id'] if isinstance(rows[0], dict) or hasattr(rows[0], '__getitem__') else rows[0][0]
        dst_id = rows[1]['account_id'] if isinstance(rows[1], dict) or hasattr(rows[1], '__getitem__') else rows[1][0]

    # Perform transfer
    res = ledger_service.execute_transfer(source_account_id=src_id, destination_account_id=dst_id, amount=350.00, device_id=1)
    txn_id = res["txn_id"]

    # Verify OUTBOX exists with status PENDING
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status FROM OUTBOX WHERE txn_id = %s;", (txn_id,))
        row = cur.fetchone()
        assert row is not None
        status = row['status'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[0]
        assert status in ("PENDING", "SENT")

    # Run outbox worker process
    count = outbox_worker.process_pending_events()
    assert count >= 0

    # Verify event status transition to SENT
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status FROM OUTBOX WHERE txn_id = %s;", (txn_id,))
        row = cur.fetchone()
        status = row['status'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[0]
        assert status == "SENT"

def test_outbox_retry_after_simulated_nosql_failure(monkeypatch):
    """
    Simulates transient MongoDB / Redis write network exception (m5-5):
    1. Asserts outbox event remains PENDING and attempts counter increments to 1.
    2. Restores healthy connection and asserts outbox event successfully resolves to SENT.
    """
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT account_id FROM ACCOUNT WHERE status = 'ACTIVE' LIMIT 2;")
        rows = cur.fetchall()
        src_id = rows[0]['account_id'] if isinstance(rows[0], dict) or hasattr(rows[0], '__getitem__') else rows[0][0]
        dst_id = rows[1]['account_id'] if isinstance(rows[1], dict) or hasattr(rows[1], '__getitem__') else rows[1][0]

    res = ledger_service.execute_transfer(source_account_id=src_id, destination_account_id=dst_id, amount=120.00, device_id=1)
    txn_id = res["txn_id"]

    # 1. Simulate NoSQL write failure via monkeypatch
    def mock_fail(*args, **kwargs):
        raise ConnectionError("Simulated NoSQL connection timeout / partition failure")

    monkeypatch.setattr(mongo_repo, "upsert_fraud_evidence", mock_fail)

    # Process pending events while NoSQL is down
    processed = outbox_worker.process_pending_events()
    assert processed == 0

    # Assert event was NOT marked SENT, but attempts was incremented
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status, attempts FROM OUTBOX WHERE txn_id = %s;", (txn_id,))
        row = cur.fetchone()
        status = row['status'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[0]
        attempts = row['attempts'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[1]
        assert status == "PENDING"
        assert attempts >= 1

    # 2. Heal the simulated failure (undo monkeypatch)
    monkeypatch.undo()

    # Process pending events again
    processed_retry = outbox_worker.process_pending_events()
    assert processed_retry >= 1

    # Verify event successfully transitioned to SENT
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status FROM OUTBOX WHERE txn_id = %s;", (txn_id,))
        row = cur.fetchone()
        status = row['status'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[0]
        assert status == "SENT"
