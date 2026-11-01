import os
os.environ["TESTING"] = "1"
import pytest
try:
    import psycopg2
except ImportError:
    psycopg2 = None

from backend.app.config import settings

def is_postgres_available() -> bool:
    if psycopg2 is None:
        return False
    try:
        conn = psycopg2.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            dbname=settings.POSTGRES_DB,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            connect_timeout=2
        )
        conn.close()
        return True
    except Exception:
        return False

@pytest.fixture(autouse=True)
def check_postgres_db(request):
    # Allow pure unit tests (like security role gating or model scoring unit test) to run without DB
    if not is_postgres_available() and request.node.name not in ["test_fraud_scoring_normal_transaction", "test_fraud_model_failure_failsafe_fallback"]:
        pytest.skip("PostgreSQL database is offline on localhost:5432. Run 'docker-compose up postgres' or start PostgreSQL to run live DB tests.")
