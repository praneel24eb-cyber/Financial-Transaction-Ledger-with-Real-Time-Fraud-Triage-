# Local setup on this machine

How this repo is wired up here, so the stack can be started again without re-deriving it.
The upstream README's two options (Docker Compose, or an existing PostgreSQL install) did not
apply: Docker is not installed, and the machine's PostgreSQL 18 service requires a password
that was not available.

## What runs

| Component | How |
|---|---|
| PostgreSQL 18 | Project-local cluster in `.pgdata/` (gitignored), port **5433**, trust auth for local connections, database `ledger_db`, role `ledger_user` / `ledger_password` |
| FastAPI + UI | `.venv`, `http://127.0.0.1:8000` |
| Redis | Not installed — app uses its in-memory velocity-counter fallback |
| MongoDB | Not installed — app uses its in-memory fraud-evidence fallback |

The separate `postgresql-x64-18` Windows service (port 5432) is untouched and unused by this app.

## Start / stop

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-stack.ps1   # PG cluster + uvicorn
powershell -ExecutionPolicy Bypass -File .\scripts\stop-stack.ps1    # stop both
```

Then open <http://127.0.0.1:8000> (UI) or <http://127.0.0.1:8000/docs> (OpenAPI).

## One-time setup that was performed

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

& "D:\PostgreSQL\18\bin\initdb.exe" -D .pgdata -U postgres -A trust -E UTF8
& "D:\PostgreSQL\18\bin\pg_ctl.exe" -D .pgdata -l .pgdata\server.log -o "-p 5433" start

# as postgres on port 5433
CREATE ROLE ledger_user LOGIN CREATEDB CREATEROLE PASSWORD 'ledger_password';
CREATE DATABASE ledger_db OWNER ledger_user;
ALTER ROLE ledger_user SUPERUSER;   # needed for CREATE EXTENSION pgcrypto in schema.sql

psql -h 127.0.0.1 -p 5433 -U ledger_user -d ledger_db -f backend/app/database/schema.sql
psql -h 127.0.0.1 -p 5433 -U ledger_user -d ledger_db -f backend/app/database/triggers.sql
```

`.env` points the app at port 5433. On first startup the app seeds 10 customers / 15 accounts /
40 transactions and retrains the Isolation Forest model.

## Code fixes required to get it running

These were real defects, not environment quirks:

1. **`backend/app/main.py` — startup self-deadlock.** `seed_database()` was called while the
   startup connection/cursor was still open, so its schema DDL (`CREATE TABLE IF NOT EXISTS`)
   waited forever on the `ACCESS SHARE` lock that connection held. Seeding now runs after the
   connection closes.
2. **`backend/app/repositories/db.py` — `get_connection()` swallowed caller errors.** Any
   exception raised inside the `with` block was caught and turned into a SQLite fallback plus a
   second `yield`, producing `RuntimeError: generator didn't stop after throw()`. Only connection
   failures fall back now. Also added the `use_postgres` property the tests expect.
3. **`backend/app/services/audit_service.py` — two incompatible hash canonicalizations.**
   Rows written by the SQL trigger hash `jsonb::text`; rows written by the Python service hashed
   Python's `json.dumps(sort_keys=True)`, so `/api/v1/audit/verify/chain` always reported
   tampering at row 1. Both paths and the verifier now hash in PostgreSQL, giving one chain.
4. **`backend/app/main.py` — Jinja2 render signature.** `TemplateResponse(name, context)` no
   longer works with current Starlette (the request is now the first argument); all six UI routes
   returned HTTP 500. Updated to `TemplateResponse(request, name, context)`.
5. **`backend/app/database/schema.sql` — `LEDGER_ENTRY.direction CHAR(6)`.** `CHAR` pads `DEBIT`
   to `DEBIT `, so Python comparisons against `'DEBIT'` failed and padded values leaked into API
   responses. Changed to `VARCHAR(6)` (and altered the live table).
6. **`backend/app/database/seed.py`** — truncation now uses `RESTART IDENTITY` so seeded IDs are
   deterministic; **`benchmarking/demo_concurrency.py`** — added repo-root `sys.path` bootstrap
   and UTF-8 stdout so the documented `python benchmarking/demo_concurrency.py` command works on
   Windows.
7. **`requirements.txt`** — added `email-validator` (required by `EmailStr`, previously missing)
   and capped `pytest<9` (pytest 9 crashes on startup with the installed `anyio` plugin).

## Login portal & demo accounts

The app now requires authentication; visiting any page while signed out redirects to `/login`.

| Username | Password | Role |
|---|---|---|
| `customer` | `customer123` | customer (own accounts, transfers, history) |
| `analyst` | `analyst123` | analyst (alert queue, ML evidence, reviews) |
| `admin` | `admin123` | admin (everything, audit chain, benchmarks, seeding) |

Credentials live in the `APP_USER` table as PBKDF2-SHA256 hashes. The browser session is an
HMAC-signed, HttpOnly cookie (`ledger_session`, 8h). `X-User-Role` is only honoured when
`ALLOW_ROLE_HEADER=true`; the test suite enables it in `tests/conftest.py`, while the running app
requires a real sign-in. Customers are row-scoped: they cannot read or debit another customer's
account, and customer transfer responses omit `risk_score`, `decision`, and `model_version`.

## Verified

- `pytest tests/` → **21 passed**
- Signed-out UI routes redirect to `/login`; all three demo logins work end to end
- All UI routes (`/`, `/ui/transfer`, `/ui/history`, `/ui/alerts`, `/ui/audit`, `/ui/benchmarks`) → 200 for permitted roles
- Customer sees no ML scores / fraud queue; analyst cannot read balances; analyst review returns 201
- Customer transfer → 201 with `source_balance` / `destination_balance`, no ML fields
- Customer cannot read a foreign account (404) or debit it (403)
- Outbox worker drains `PENDING` events and attaches evidence to fraud alerts
- `GET /api/v1/audit/verify/chain` → chain valid across trigger- and app-written rows
- `python benchmarking/demo_concurrency.py` → zero lost updates, `₹20,000.00` preserved

## Notes / caveats

- `ledger_user` is a superuser in this throwaway local cluster only (needed for `pgcrypto`).
  Production use should follow the README's restricted `ledger_app_role` model.
- The README lists `GET /api/v1/accounts/{id}/balance`; the implemented route is
  `GET /api/v1/accounts/{id}`, and transfers are `POST /api/v1/transactions`.
- Data is not persisted across machines; `.pgdata/` can be deleted to start from a clean database
  (the app reseeds on the next startup).
