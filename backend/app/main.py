import os
import threading
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

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
    # Startup logic: Initialize PostgreSQL schema and seed dataset if empty
    logger.info("Initializing Financial Ledger PostgreSQL Database & Models...")
    try:
        db_manager.init_db()
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
STATIC_DIR = os.path.join(BASE_DIR, "..", "frontend", "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "..", "frontend", "templates")

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

# -------------------------------------------------------------------
# UI Page Routes (Jinja2 Server-Rendered Views)
# -------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def page_dashboard(request: Request):
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
        "index.html",
        {
            "request": request,
            "active_page": "dashboard",
            "total_accounts": total_accounts,
            "total_balance": total_balance,
            "open_alerts": open_alerts,
            "outbox_pending": outbox_pending,
            "accounts": accs
        }
    )

@app.get("/ui/transfer", response_class=HTMLResponse)
def page_transfer(request: Request):
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT account_id, customer_id, balance, status FROM ACCOUNT ORDER BY account_id ASC;")
                accs = [dict(a) for a in cur.fetchall()]
    except Exception:
        accs = []
    return templates.TemplateResponse("transfer.html", {"request": request, "active_page": "transfer", "accounts": accs})

@app.get("/ui/history", response_class=HTMLResponse)
def page_history(request: Request, account_id: int = Query(default=None)):
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
        "history.html",
        {
            "request": request,
            "active_page": "history",
            "accounts": accs,
            "selected_account": account_id,
            "ledger_entries": entries
        }
    )

@app.get("/ui/alerts", response_class=HTMLResponse)
def page_alerts(request: Request):
    from backend.app.api.fraud import list_fraud_alerts
    try:
        alerts = list_fraud_alerts()
    except Exception:
        alerts = []
    return templates.TemplateResponse("alerts.html", {"request": request, "active_page": "alerts", "alerts": alerts})

@app.get("/ui/audit", response_class=HTMLResponse)
def page_audit(request: Request):
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT audit_id, table_name, operation, prev_hash, row_hash, created_at FROM AUDIT_LOG ORDER BY audit_id DESC LIMIT 50;")
                rows = [dict(r) for r in cur.fetchall()]
    except Exception:
        rows = []
    return templates.TemplateResponse("audit.html", {"request": request, "active_page": "audit", "audit_rows": rows})

@app.get("/ui/benchmarks", response_class=HTMLResponse)
def page_benchmarks(request: Request):
    report = get_benchmark_report()
    return templates.TemplateResponse("benchmarks.html", {"request": request, "active_page": "benchmarks", "benchmarks": report})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
