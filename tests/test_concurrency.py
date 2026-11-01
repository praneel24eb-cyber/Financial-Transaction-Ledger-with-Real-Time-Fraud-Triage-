import pytest
from concurrent.futures import ThreadPoolExecutor
from backend.app.services.ledger_service import ledger_service
from backend.app.repositories.db import db_manager
from backend.app.database.seed import seed_database

@pytest.fixture(autouse=True)
def setup_db():
    seed_database(num_customers=5, num_accounts=5)
    yield

def test_concurrent_transfers_no_deadlock():
    # Fetch two active account IDs dynamically
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT account_id FROM ACCOUNT WHERE status = 'ACTIVE' LIMIT 2;")
        rows = cur.fetchall()
        acc1 = rows[0]['account_id'] if isinstance(rows[0], dict) or hasattr(rows[0], '__getitem__') else rows[0][0]
        acc2 = rows[1]['account_id'] if isinstance(rows[1], dict) or hasattr(rows[1], '__getitem__') else rows[1][0]

        cur.execute("UPDATE ACCOUNT SET balance = 10000.00, status = 'ACTIVE' WHERE account_id IN (%s, %s);", (acc1, acc2))
        conn.commit()

    def transfer_a_to_b():
        try:
            return ledger_service.execute_transfer(source_account_id=acc1, destination_account_id=acc2, amount=100.00, device_id=1)
        except Exception as e:
            return str(e)

    def transfer_b_to_a():
        try:
            return ledger_service.execute_transfer(source_account_id=acc2, destination_account_id=acc1, amount=100.00, device_id=2)
        except Exception as e:
            return str(e)

    # Execute opposite transfers concurrently in threads
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for _ in range(5):
            futures.append(executor.submit(transfer_a_to_b))
            futures.append(executor.submit(transfer_b_to_a))

        results = [f.result() for f in futures]

    # Verify final total system balance remains 20,000.00 (no lost updates!)
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT SUM(balance) as total_bal FROM ACCOUNT WHERE account_id IN (%s, %s);", (acc1, acc2))
        row = cur.fetchone()
        tot = float(row['total_bal'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[0])
        assert tot == 20000.00
