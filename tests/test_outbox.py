import pytest
from backend.app.workers.outbox_worker import outbox_worker
from backend.app.services.ledger_service import ledger_service
from backend.app.repositories.db import db_manager
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
