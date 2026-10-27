import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database.seed import seed_database
from backend.app.repositories.db import db_manager

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db():
    seed_database(num_customers=5, num_accounts=10)
    yield

def test_successful_transfer():
    # Fetch two active accounts
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT account_id, balance FROM ACCOUNT WHERE status = 'ACTIVE' LIMIT 2;")
        rows = cur.fetchall()
        src_id = rows[0]['account_id'] if isinstance(rows[0], dict) or hasattr(rows[0], '__getitem__') else rows[0][0]
        dst_id = rows[1]['account_id'] if isinstance(rows[1], dict) or hasattr(rows[1], '__getitem__') else rows[1][0]

    payload = {
        "source_account_id": src_id,
        "destination_account_id": dst_id,
        "amount": 500.00,
        "device_id": 1
    }

    response = client.post("/api/v1/transactions", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert "txn_id" in data

    # Verify double-entry ledger balance
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT direction, amount FROM LEDGER_ENTRY WHERE txn_id = %s;" if db_manager.use_postgres else "SELECT direction, amount FROM LEDGER_ENTRY WHERE txn_id = ?;", (data["txn_id"],))
        entries = cur.fetchall()
        assert len(entries) == 2
        debits = sum(e['amount'] if isinstance(e, dict) or hasattr(e, '__getitem__') else e[1] for e in entries if (e['direction'] if isinstance(e, dict) or hasattr(e, '__getitem__') else e[0]) == 'DEBIT')
        credits = sum(e['amount'] if isinstance(e, dict) or hasattr(e, '__getitem__') else e[1] for e in entries if (e['direction'] if isinstance(e, dict) or hasattr(e, '__getitem__') else e[0]) == 'CREDIT')
        assert debits == credits == 500.00

def test_insufficient_balance():
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT account_id FROM ACCOUNT LIMIT 2;")
        rows = cur.fetchall()
        src_id = rows[0]['account_id'] if isinstance(rows[0], dict) or hasattr(rows[0], '__getitem__') else rows[0][0]
        dst_id = rows[1]['account_id'] if isinstance(rows[1], dict) or hasattr(rows[1], '__getitem__') else rows[1][0]

    payload = {
        "source_account_id": src_id,
        "destination_account_id": dst_id,
        "amount": 999999999.00,  # Exceeds balance
        "device_id": 1
    }

    response = client.post("/api/v1/transactions", json=payload)
    assert response.status_code == 402

def test_invalid_account():
    payload = {
        "source_account_id": 99999,
        "destination_account_id": 1,
        "amount": 100.00,
        "device_id": 1
    }
    response = client.post("/api/v1/transactions", json=payload)
    assert response.status_code == 404

def test_self_transfer_rejected():
    payload = {
        "source_account_id": 1,
        "destination_account_id": 1,
        "amount": 100.00,
        "device_id": 1
    }
    response = client.post("/api/v1/transactions", json=payload)
    assert response.status_code == 400
