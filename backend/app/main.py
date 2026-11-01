import os
import threading
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Query, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.repositories.db import db_manager
from backend.app.database.seed import seed_database
from backend.app.workers.outbox_worker import run_outbox_worker_loop

# Import Routers
from backend.app.api.customers import router as customers_router
from backend.app.api.accounts import router as accounts_router
from backend.app.api.transactions import router as transactions_router
from backend.app.api.fraud import router as fraud_router
from backend.app.api.audit import router as audit_router
from backend.app.api.admin import router as admin_router, get_benchmark_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("TESTING") == "1":
        yield
        return
    # Startup logic: Initialize PostgreSQL schema and seed dataset if empty
    logger.info("Initializing Financial Ledger PostgreSQL Database & Models...")
    try:
        db_manager.init_db()
        count = 0
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) as cnt FROM ACCOUNT;")
                row = cur.fetchone()
                count = row['cnt'] if row else 0
        if count == 0:
            logger.info("Empty database detected. Seeding initial synthetic records & training model...")
            seed_database()
    except Exception as e:
        logger.warning(f"Database connection or init on startup: {e}")

    # Start Outbox Worker Daemon Thread
    if os.getenv("TESTING") != "1":
        outbox_thread = threading.Thread(target=run_outbox_worker_loop, daemon=True)
        outbox_thread.start()
        logger.info("Outbox worker thread started in background.")

    yield

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Academic DBMS Project PRD: Double-entry ledger in PostgreSQL 15+, Isolation Forest real-time fraud triage, hash-chained audit log, and transactional outbox.",
    lifespan=lifespan
)

# Static & Templates setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
STATIC_DIR = os.path.join(FRONTEND_DIR, "static")
TEMPLATES_DIR = os.path.join(FRONTEND_DIR, "templates")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Include API Routers
api_prefix = "/api/v1"
app.include_router(customers_router, prefix=api_prefix)
app.include_router(accounts_router, prefix=api_prefix)
app.include_router(transactions_router, prefix=api_prefix)
app.include_router(fraud_router, prefix=api_prefix)
app.include_router(audit_router, prefix=api_prefix)
app.include_router(admin_router, prefix=api_prefix)

def get_ui_role(request: Request) -> str:
    """Helper to extract active role from cookie or default to customer."""
    role = request.cookies.get("user_role", "customer").lower()
    return role if role in ["customer", "analyst", "admin"] else "customer"

class RoleSwitchPayload(BaseModel):
    role: str

@app.post("/api/v1/auth/role")
def set_active_role(payload: RoleSwitchPayload, response: Response):
    """Sets the active demonstration role in cookie."""
    new_role = payload.role.lower()
    if new_role not in ["customer", "analyst", "admin"]:
        new_role = "customer"
    response.set_cookie(key="user_role", value=new_role, path="/", max_age=86400, samesite="lax")
    return {"status": "success", "role": new_role}

# -------------------------------------------------------------------
# UI Page Routes (Jinja2 Server-Rendered Views)
# -------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def page_dashboard(request: Request):
    role = get_ui_role(request)
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(balance), 0.0) as total_bal FROM ACCOUNT;")
                r1 = cur.fetchone()
                total_accounts = r1['cnt'] if r1 else 0
                total_balance = float(r1['total_bal'] if r1 else 0.0)

                cur.execute("SELECT COUNT(*) as cnt FROM FRAUD_ALERT WHERE status = 'OPEN';")
                r2 = cur.fetchone()
                open_alerts = r2['cnt'] if r2 else 0

                cur.execute("SELECT COUNT(*) as cnt FROM OUTBOX WHERE status = 'PENDING';")
                r3 = cur.fetchone()
                outbox_pending = r3['cnt'] if r3 else 0

                cur.execute("SELECT account_id, customer_id, account_type, balance, status FROM ACCOUNT ORDER BY account_id ASC LIMIT 10;")
                accs = [dict(a) for a in cur.fetchall()]
    except Exception:
        total_accounts, total_balance, open_alerts, outbox_pending, accs = 0, 0.0, 0, 0, []

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "active_page": "dashboard",
            "current_role": role,
            "total_accounts": total_accounts,
            "total_balance": total_balance,
            "open_alerts": open_alerts,
            "outbox_pending": outbox_pending,
            "accounts": accs
        }
    )

@app.get("/ui/transfer", response_class=HTMLResponse)
def page_transfer(request: Request):
    role = get_ui_role(request)
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT account_id, customer_id, balance, status FROM ACCOUNT ORDER BY account_id ASC;")
                accs = [dict(a) for a in cur.fetchall()]
    except Exception:
        accs = []
    return templates.TemplateResponse(request=request, name="transfer.html", context={"active_page": "transfer", "current_role": role, "accounts": accs})

@app.get("/ui/history", response_class=HTMLResponse)
def page_history(request: Request, account_id: int = Query(default=None)):
    role = get_ui_role(request)
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT account_id FROM ACCOUNT ORDER BY account_id ASC;")
                accs = [dict(a) for a in cur.fetchall()]

                if account_id:
                    query = """
                        SELECT l.entry_id, l.txn_id, l.account_id, l.direction, l.amount, l.created_at, t.status, t.txn_type
                        FROM LEDGER_ENTRY l
                        JOIN TRANSACTION t ON l.txn_id = t.txn_id
                        WHERE l.account_id = %s
                        ORDER BY l.entry_id DESC LIMIT 50;
                    """
                    cur.execute(query, (account_id,))
                else:
                    query = """
                        SELECT l.entry_id, l.txn_id, l.account_id, l.direction, l.amount, l.created_at, t.status, t.txn_type
                        FROM LEDGER_ENTRY l
                        JOIN TRANSACTION t ON l.txn_id = t.txn_id
                        ORDER BY l.entry_id DESC LIMIT 50;
                    """
                    cur.execute(query)

                entries = [dict(e) for e in cur.fetchall()]
    except Exception:
        accs, entries = [], []

    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "active_page": "history",
            "current_role": role,
            "accounts": accs,
            "selected_account": account_id,
            "ledger_entries": entries
        }
    )

@app.get("/ui/alerts", response_class=HTMLResponse)
def page_alerts(request: Request):
    role = get_ui_role(request)
    if role not in ["analyst", "admin"]:
        return templates.TemplateResponse(
            request=request,
            name="forbidden.html",
            context={
                "active_page": "alerts",
                "current_role": role,
                "required_roles": "Fraud Analyst or System Admin",
                "feature_name": "Fraud Alerts & Risk Triage Console"
            },
            status_code=403
        )
    from backend.app.api.fraud import list_fraud_alerts
    try:
        alerts = list_fraud_alerts()
    except Exception:
        alerts = []
    return templates.TemplateResponse(request=request, name="alerts.html", context={"active_page": "alerts", "current_role": role, "alerts": alerts})

@app.get("/ui/audit", response_class=HTMLResponse)
def page_audit(request: Request):
    role = get_ui_role(request)
    if role != "admin":
        return templates.TemplateResponse(
            request=request,
            name="forbidden.html",
            context={
                "active_page": "audit",
                "current_role": role,
                "required_roles": "System Admin",
                "feature_name": "SHA-256 Cryptographic Audit Trail"
            },
            status_code=403
        )
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT audit_id, table_name, operation, prev_hash, row_hash, created_at FROM AUDIT_LOG ORDER BY audit_id DESC LIMIT 50;")
                rows = [dict(r) for r in cur.fetchall()]
    except Exception:
        rows = []
    return templates.TemplateResponse(request=request, name="audit.html", context={"active_page": "audit", "current_role": role, "audit_rows": rows})

@app.get("/ui/benchmarks", response_class=HTMLResponse)
def page_benchmarks(request: Request):
    role = get_ui_role(request)
    if role != "admin":
        return templates.TemplateResponse(
            request=request,
            name="forbidden.html",
            context={
                "active_page": "benchmarks",
                "current_role": role,
                "required_roles": "System Admin",
                "feature_name": "DBMS Concurrency & Latency Benchmarks"
            },
            status_code=403
        )
    report = get_benchmark_report()
    return templates.TemplateResponse(request=request, name="benchmarks.html", context={"active_page": "benchmarks", "current_role": role, "benchmarks": report})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
