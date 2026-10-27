import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_customer_role_forbidden_on_analyst_review():
    # Customer token / role trying to submit analyst review -> 403 Forbidden
    payload = {
        "analyst_id": 1,
        "decision": "CONFIRM_FRAUD"
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
        "analyst_id": 1,
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
