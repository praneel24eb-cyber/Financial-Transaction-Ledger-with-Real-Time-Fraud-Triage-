import pytest
from backend.app.services.audit_service import audit_service
from backend.app.repositories.db import db_manager
from backend.app.database.seed import seed_database

@pytest.fixture(autouse=True)
def setup_db():
    seed_database()
    yield

def test_audit_hash_chain_valid():
    res = audit_service.verify_hash_chain()
    assert res["is_valid"] is True
    assert res["tampered_audit_id"] is None

def test_audit_hash_chain_tamper_detection():
    # Insert a valid audit entry
    with db_manager.get_connection() as conn:
        audit_service.record_audit_entry(conn, "ACCOUNT", "UPDATE", old_data={"balance": 1000}, new_data={"balance": 500})
        conn.commit()

    # Mutate stored row_hash to simulate attacker tampering
    with db_manager.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE AUDIT_LOG SET row_hash = 'badhash00000000000000000000000000000000000000000000000000000000' WHERE audit_id = (SELECT MAX(audit_id) FROM AUDIT_LOG);")
        conn.commit()

    # Re-verify hash chain -> assert tamper detection!
    res = audit_service.verify_hash_chain()
    assert res["is_valid"] is False
    assert res["tampered_audit_id"] is not None
