import os
import threading
import logging
from contextlib import asynccontextmanager
from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, Request, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.app.config import settings
from backend.app.repositories.db import db_manager
from backend.app.database.seed import seed_database
from backend.app.workers.outbox_worker import run_outbox_worker_loop
from backend.app.services.auth_service import (
    SESSION_COOKIE,
    authenticate,
    create_session_token,
    ensure_demo_users,
)
from backend.app.api.security import (
    ADMIN_ROLES,
    ANALYST_ROLES,
    CUSTOMER_ROLES,
    get_session_user,
    home_for_role,
    page_guard,
)

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
        count = 0
        # Read inside a short-lived connection: seeding runs its own DDL, and holding
        # this connection open would block those ALTER/CREATE locks on PostgreSQL.
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) as cnt FROM ACCOUNT;")
                row = cur.fetchone()
                count = row['cnt'] if row else 0
        if count == 0:
            logger.info("Empty database detected. Seeding initial synthetic records & training model...")
            seed_database()
        ensure_demo_users()
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
# Authentication (login portal + signed session cookie)
# -------------------------------------------------------------------

def _safe_next(next_url: Optional[str], default: str) -> str:
    """Only allow same-site relative redirects (prevents open redirects)."""
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return default


def render(request: Request, template_name: str, context: dict) -> HTMLResponse:
    """Renders a page with the session identity injected into every template."""
    user = get_session_user(request) or {}
    payload = {
        "request": request,
        "current_user": user or None,
        "role": (user.get("role") or "anonymous") if user else "anonymous",
        "can_triage": (user.get("role") in ANALYST_ROLES) if user else False,
        "can_admin": (user.get("role") in ADMIN_ROLES) if user else False,
        "can_transfer": (user.get("role") in CUSTOMER_ROLES) if user else False,
    }
    payload.update(context)
    return templates.TemplateResponse(request, template_name, payload)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: Optional[str] = Query(default=None)):
    user = get_session_user(request)
    if user:
        return RedirectResponse(
            url=_safe_next(next, home_for_role(user.get("role"))), status_code=303
        )
    return templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "next": _safe_next(next, ""), "error": None},
    )


@app.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: Optional[str] = Form(default=None),
):
    user = authenticate(username.strip(), password)

    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "request": request,
                "next": _safe_next(next, ""),
                "error": "Invalid username or password.",
                "username_value": username,
            },
            status_code=401,
        )

    redirect_to = _safe_next(next, home_for_role(user["role"]))
    response = RedirectResponse(url=redirect_to, status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session_token(user),
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )
    logger.info(f"User '{user['username']}' signed in with role '{user['role']}'.")
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


# -------------------------------------------------------------------
# UI Page Routes (Jinja2 Server-Rendered Views)
# -------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def page_dashboard(request: Request):
    denied = page_guard(request, ["customer", "analyst", "admin"])
    if denied:
        return denied

    user = get_session_user(request) or {}
    role = user.get("role")
    # Customers only ever see their own accounts; staff see the whole book.
    scope_customer_id = user.get("customer_id") if role == "customer" else None
    where_own = " WHERE customer_id = %s" if scope_customer_id else ""

    total_accounts, total_balance, open_alerts, high_alerts, outbox_pending = 0, 0.0, 0, 0, 0
    accs, recent_alerts = [], []

    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                if scope_customer_id:
                    cur.execute(
                        f"SELECT COUNT(*) as cnt, COALESCE(SUM(balance), 0.0) as total_bal FROM ACCOUNT{where_own};",
                        (scope_customer_id,),
                    )
                else:
                    cur.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(balance), 0.0) as total_bal FROM ACCOUNT;")
                r1 = cur.fetchone()
                total_accounts = r1['cnt'] if r1 else 0
                total_balance = float(r1['total_bal'] if r1 else 0.0)

                if role in ANALYST_ROLES:
                    cur.execute("SELECT COUNT(*) as cnt FROM FRAUD_ALERT WHERE status = 'OPEN';")
                    r2 = cur.fetchone()
                    open_alerts = r2['cnt'] if r2 else 0

                    cur.execute("SELECT COUNT(*) as cnt FROM FRAUD_ALERT WHERE status = 'OPEN' AND severity = 'HIGH';")
                    r3 = cur.fetchone()
                    high_alerts = r3['cnt'] if r3 else 0

                    cur.execute(
                        "SELECT alert_id, txn_id, severity, status, created_at FROM FRAUD_ALERT "
                        "ORDER BY alert_id DESC LIMIT 6;"
                    )
                    recent_alerts = [dict(r) for r in cur.fetchall()]

                if role in ADMIN_ROLES:
                    cur.execute("SELECT COUNT(*) as cnt FROM OUTBOX_EVENT WHERE status = 'PENDING';")
                    r4 = cur.fetchone()
                    outbox_pending = r4['cnt'] if r4 else 0

                if scope_customer_id:
                    cur.execute(
                        "SELECT account_id, customer_id, type, balance, status FROM ACCOUNT WHERE customer_id = %s ORDER BY account_id ASC;",
                        (scope_customer_id,),
                    )
                else:
                    cur.execute("SELECT account_id, customer_id, type, balance, status FROM ACCOUNT ORDER BY account_id ASC LIMIT 10;")
                accs = [dict(a) for a in cur.fetchall()]

                cur.execute(
                    "SELECT account_id, customer_id, balance FROM ACCOUNT WHERE status = 'ACTIVE' ORDER BY account_id ASC;"
                )
                destinations = [
                    {**dict(a), "balance": float(a["balance"])} for a in cur.fetchall()
                ]
                if role == "customer":
                    destinations = [
                        {"account_id": d["account_id"], "customer_id": d["customer_id"]}
                        for d in destinations
                    ]
    except Exception as e:
        logger.warning(f"Dashboard query failed: {e}")
        destinations = []

    return render(request, "index.html", {
        "active_page": "dashboard",
        "denied": request.query_params.get("denied") == "1",
        "total_accounts": total_accounts,
        "total_balance": total_balance,
        "open_alerts": open_alerts,
        "high_alerts": high_alerts,
        "outbox_pending": outbox_pending,
        "accounts": accs,
        "destination_accounts": destinations,
        "recent_alerts": recent_alerts,
    })


@app.get("/ui/transfer", response_class=HTMLResponse)
def page_transfer(request: Request):
    denied = page_guard(request, CUSTOMER_ROLES)
    if denied:
        return denied

    user = get_session_user(request) or {}
    scope_customer_id = user.get("customer_id") if user.get("role") == "customer" else None

    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                if scope_customer_id:
                    cur.execute(
                        "SELECT account_id, customer_id, balance, status FROM ACCOUNT WHERE customer_id = %s ORDER BY account_id ASC;",
                        (scope_customer_id,),
                    )
                else:
                    cur.execute("SELECT account_id, customer_id, balance, status FROM ACCOUNT ORDER BY account_id ASC;")
                # DECIMAL balances are rendered in JS via |tojson, so coerce to float.
                accs = [
                    {**dict(a), "balance": float(a["balance"])} for a in cur.fetchall()
                ]

                cur.execute("SELECT account_id, customer_id, balance FROM ACCOUNT WHERE status = 'ACTIVE' ORDER BY account_id ASC;")
                destinations = [
                    {**dict(a), "balance": float(a["balance"])} for a in cur.fetchall()
                ]

                if user.get("role") == "customer":
                    # Do not expose other customers' balances in the recipient picker.
                    destinations = [
                        {"account_id": d["account_id"], "customer_id": d["customer_id"]}
                        for d in destinations
                    ]

                cur.execute("SELECT d.device_id, d.customer_id FROM DEVICE d ORDER BY d.device_id ASC;")
                devices = [dict(d) for d in cur.fetchall()]
    except Exception:
        accs, destinations, devices = [], [], []

    return render(request, "transfer.html", {
        "active_page": "transfer",
        "accounts": accs,
        "destination_accounts": destinations,
        "devices": devices,
    })


@app.get("/ui/history", response_class=HTMLResponse)
def page_history(request: Request, account_id: int = Query(default=None)):
    denied = page_guard(request, CUSTOMER_ROLES)
    if denied:
        return denied

    user = get_session_user(request) or {}
    scope_customer_id = user.get("customer_id") if user.get("role") == "customer" else None

    accs, entries = [], []
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                if scope_customer_id:
                    cur.execute(
                        "SELECT account_id FROM ACCOUNT WHERE customer_id = %s ORDER BY account_id ASC;",
                        (scope_customer_id,),
                    )
                else:
                    cur.execute("SELECT account_id FROM ACCOUNT ORDER BY account_id ASC;")
                accs = [dict(a) for a in cur.fetchall()]

                own_ids = [a["account_id"] for a in accs]
                if scope_customer_id and account_id and account_id not in own_ids:
                    # A customer may not inspect someone else's ledger.
                    entries = []
                elif account_id:
                    cur.execute(
                        """
                        SELECT l.entry_id, l.txn_id, l.account_id, l.direction, l.amount, l.created_at, t.status
                        FROM LEDGER_ENTRY l
                        JOIN TRANSACTION t ON l.txn_id = t.txn_id
                        WHERE l.account_id = %s
                        ORDER BY l.entry_id DESC LIMIT 50;
                        """,
                        (account_id,),
                    )
                    entries = [dict(e) for e in cur.fetchall()]
                elif scope_customer_id:
                    cur.execute(
                        """
                        SELECT l.entry_id, l.txn_id, l.account_id, l.direction, l.amount, l.created_at, t.status
                        FROM LEDGER_ENTRY l
                        JOIN TRANSACTION t ON l.txn_id = t.txn_id
                        WHERE l.account_id = ANY(%s)
                        ORDER BY l.entry_id DESC LIMIT 50;
                        """,
                        (own_ids,),
                    )
                    entries = [dict(e) for e in cur.fetchall()]
                else:
                    cur.execute(
                        """
                        SELECT l.entry_id, l.txn_id, l.account_id, l.direction, l.amount, l.created_at, t.status
                        FROM LEDGER_ENTRY l
                        JOIN TRANSACTION t ON l.txn_id = t.txn_id
                        ORDER BY l.entry_id DESC LIMIT 50;
                        """
                    )
                    entries = [dict(e) for e in cur.fetchall()]
    except Exception as e:
        logger.warning(f"History query failed: {e}")

    return render(request, "history.html", {
        "active_page": "history",
        "accounts": accs,
        "selected_account": account_id,
        "ledger_entries": entries,
    })


@app.get("/ui/alerts", response_class=HTMLResponse)
def page_alerts(request: Request):
    denied = page_guard(request, ANALYST_ROLES)
    if denied:
        return denied

    from backend.app.api.fraud import list_fraud_alerts
    try:
        alerts = list_fraud_alerts()
    except Exception:
        alerts = []

    user = get_session_user(request) or {}
    return render(request, "alerts.html", {
        "active_page": "alerts",
        "alerts": alerts,
        "analyst_default": user.get("name") or user.get("sub") or "analyst",
    })


@app.get("/ui/audit", response_class=HTMLResponse)
def page_audit(request: Request):
    denied = page_guard(request, ADMIN_ROLES)
    if denied:
        return denied

    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT audit_id, table_name, operation, prev_hash, row_hash, created_at FROM AUDIT_LOG ORDER BY audit_id DESC LIMIT 50;")
                rows = [dict(r) for r in cur.fetchall()]
    except Exception:
        rows = []
    return render(request, "audit.html", {"active_page": "audit", "audit_rows": rows})


@app.get("/ui/benchmarks", response_class=HTMLResponse)
def page_benchmarks(request: Request):
    denied = page_guard(request, ADMIN_ROLES)
    if denied:
        return denied

    report = get_benchmark_report()
    return render(request, "benchmarks.html", {"active_page": "benchmarks", "benchmarks": report})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
