import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.repositories.db import db_manager
from backend.app.database.seed import seed_database
from backend.app.services.auth_service import ensure_demo_users

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def auth_tables():
    # Login tests need a seeded ledger plus APP_USER demo accounts; skip cleanly when
    # PostgreSQL is offline so the API-only tests can still run on SQLite fallback.
    try:
        db_manager.init_db()
        seed_database(num_customers=4, num_accounts=8)
        ensure_demo_users()
    except Exception:
        pytest.skip("PostgreSQL database is offline; skipping login portal tests.")
    yield

def test_customer_role_forbidden_on_analyst_review():
    # Customer token / role trying to submit analyst review -> 403 Forbidden
    payload = {
        "analyst_id": "cust_123",
        "decision": "CONFIRMED_FRAUD"
    }
    headers = {"X-User-Role": "customer"}
    response = client.post("/api/v1/fraud/alerts/1/review", json=payload, headers=headers)
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"] or "Required role" in response.json()["detail"]

def test_customer_role_forbidden_on_audit_chain_verify():
    # Customer trying to verify audit chain -> 403 Forbidden
    headers = {"X-User-Role": "customer"}
    response = client.get("/api/v1/audit/verify/chain", headers=headers)
    assert response.status_code == 403

def test_analyst_role_permitted_on_analyst_review():
    # Analyst role submitting review -> passes security role gating (does not return 403)
    payload = {
        "analyst_id": "analyst_99",
        "decision": "FALSE_POSITIVE"
    }
    headers = {"X-User-Role": "analyst"}
    response = client.post("/api/v1/fraud/alerts/99999/review", json=payload, headers=headers)
    assert response.status_code != 403

def test_admin_role_permitted_on_audit_verify():
    # Admin role verifying audit chain -> passes security role gating (does not return 403)
    headers = {"X-User-Role": "admin"}
    response = client.get("/api/v1/audit/verify/chain", headers=headers)
    assert response.status_code != 403

def test_unauthenticated_api_calls_are_rejected():
    # No session cookie and no X-User-Role header -> 401, never an implicit "customer".
    response = client.get("/api/v1/fraud/alerts")
    assert response.status_code == 401

    response = client.get("/api/v1/accounts")
    assert response.status_code == 401

def test_analyst_cannot_read_account_balances():
    headers = {"X-User-Role": "analyst"}
    response = client.get("/api/v1/accounts/1", headers=headers)
    assert response.status_code == 403

def test_customer_cannot_list_fraud_alerts():
    headers = {"X-User-Role": "customer"}
    response = client.get("/api/v1/fraud/alerts", headers=headers)
    assert response.status_code == 403

def test_ui_pages_redirect_anonymous_visitors_to_login():
    for path in ["/", "/ui/transfer", "/ui/history", "/ui/alerts", "/ui/audit", "/ui/benchmarks"]:
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303, path
        assert response.headers["location"].startswith("/login"), path

def test_login_portal_rejects_bad_credentials():
    response = client.post(
        "/login", data={"username": "analyst", "password": "wrong-password"}, follow_redirects=False
    )
    assert response.status_code == 401
    assert "Invalid username or password" in response.text

def test_login_portal_sets_session_and_scopes_navigation():
    local_client = TestClient(app)
    response = local_client.post(
        "/login", data={"username": "analyst", "password": "analyst123"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/ui/alerts"
    assert "ledger_session" in response.cookies

    page = local_client.get("/")
    assert page.status_code == 200
    assert "Fraud Analyst Dashboard" in page.text
    # Analyst navigation must not expose customer or admin-only pages.
    assert "/ui/audit" not in page.text
    assert "/ui/transfer" not in page.text

    local_client.cookies.clear()


def test_customer_session_is_scoped_to_own_accounts():
    local_client = TestClient(app)
    login = local_client.post(
        "/login",
        data={"username": "customer", "password": "customer123"},
        follow_redirects=False,
    )
    assert login.status_code == 303

    accounts = local_client.get("/api/v1/accounts").json()
    assert accounts, "expected the demo customer to own at least one account"
    customer_ids = {a["customer_id"] for a in accounts}
    assert len(customer_ids) == 1, "customer must only ever see their own accounts"
    own_customer_id = customer_ids.pop()

    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT account_id FROM ACCOUNT WHERE customer_id <> %s LIMIT 1;",
                (own_customer_id,),
            )
            row = cur.fetchone()
    assert row, "expected another customer's account to exist in the seeded dataset"
    foreign_account_id = row["account_id"]

    # Row-level authorization: reading and debiting other customers' accounts is refused.
    assert local_client.get(f"/api/v1/accounts/{foreign_account_id}").status_code == 404
    transfer = local_client.post(
        "/api/v1/transactions",
        json={
            "source_account_id": foreign_account_id,
            "destination_account_id": accounts[0]["account_id"],
            "amount": 10.0,
            "device_id": 1,
        },
    )
    assert transfer.status_code == 403

    local_client.cookies.clear()
