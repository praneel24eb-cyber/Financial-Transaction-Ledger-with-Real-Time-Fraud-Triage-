# Financial Transaction Ledger with Real-Time Fraud Triage

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![PostgreSQL 15+](https://img.shields.io/badge/PostgreSQL-15+-336791.svg?logo=postgresql)](https://www.postgresql.org/)
[![Redis 7+](https://img.shields.io/badge/Redis-7+-DC382D.svg?logo=redis)](https://redis.io/)
[![MongoDB 6+](https://img.shields.io/badge/MongoDB-6+-47A248.svg?logo=mongodb)](https://www.mongodb.com/)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED.svg?logo=docker)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An enterprise-grade, academic DBMS implementation simulating an **ACID-compliant digital payment ledger** with **real-time ML fraud triage**, **append-only SHA-256 hash-chained audit trails**, and **eventual consistency via the transactional outbox pattern**.

Repository: [Financial-Transaction-Ledger-with-Real-Time-Fraud-Triage-](https://github.com/praneel24eb-cyber/Financial-Transaction-Ledger-with-Real-Time-Fraud-Triage-)

---

## 📑 Table of Contents

- [Architectural Overview](#-architectural-overview)
- [System Architecture Diagram](#-system-architecture-diagram)
- [12-Module Project Implementation Checklist](#-12-module-project-implementation-checklist)
- [Key Engineering Pillars](#-key-engineering-pillars)
  - [1. ACID Double-Entry Bookkeeping & Reconciliation](#1-acid-double-entry-bookkeeping--reconciliation)
  - [2. Deadlock-Free Concurrency Control & Retry Logic](#2-deadlock-free-concurrency-control--retry-logic)
  - [3. Real-Time ML Fraud Triage & Fail-Safe Fallback](#3-real-time-ml-fraud-triage--fail-safe-fallback)
  - [4. Tamper-Evident SHA-256 Audit Log](#4-tamper-evident-sha-256-audit-log)
  - [5. Transactional Outbox & NoSQL Synchronization](#5-transactional-outbox--nosql-synchronization)
  - [6. Role-Based Access Control (RBAC)](#6-role-based-access-control-rbac)
- [Repository Structure](#-repository-structure)
- [Database Schema, Partitioning & Materialized Views](#-database-schema-partitioning--materialized-views)
- [Interactive UI Dashboard](#-interactive-ui-dashboard)
- [API Reference](#-api-reference)
- [Quickstart & Execution Guide](#-quickstart--execution-guide)
  - [Option A: Docker Compose (Recommended)](#option-a-docker-compose-recommended)
  - [Option B: Local Environment Setup](#option-b-local-environment-setup)
- [Verification & Benchmarks](#-verification--benchmarks)
  - [1. Pytest Test Suite](#1-pytest-test-suite)
  - [2. ML Fraud Model Evaluation (Precision, Recall, F1)](#2-ml-fraud-model-evaluation-precision-recall-f1)
  - [3. Concurrency & Deadlock Prevention Demo](#3-concurrency--deadlock-prevention-demo)
  - [4. Database Performance Reports](#4-database-performance-reports)
- [License](#-license)

---

## 🏛 Architectural Overview

This system addresses core distributed transaction and data-integrity challenges faced by modern fintech platforms:

1. **Relational Source of Truth (PostgreSQL 15+)**: All monetary movements obey fundamental double-entry principles (every debit has an equal credit). Zero negative balances, strict foreign keys, range partition pruning on ledger entries, and automated balance reconciliation.
2. **In-Memory Speed Layer (Redis 7+)**: Low-latency rolling velocity tracking (e.g., transaction count per 10-minute / 1-hour window) to feed real-time feature extractors in sub-millisecond time.
3. **NoSQL Document Store (MongoDB 6+)**: Semi-structured fraud evidence documents and historical risk analytics synchronized asynchronously via the Transactional Outbox.
4. **Predictive Safety (Scikit-Learn Isolation Forest)**: Real-time unsupervised anomaly scoring that categorizes transfers into `APPROVE`, `REVIEW`, or `ROLLBACK` with deterministic fallback protection.

---

## 📐 System Architecture Diagram

```mermaid
flowchart TD
    subgraph Client["Client Tier"]
        UI["Modern Glassmorphism UI<br/>(Dashboard, Transfer, Alerts, Audit, Benchmarks)"]
        API["REST API Clients<br/>(FastAPI with RBAC Headers)"]
    end

    subgraph Service["Application Core (FastAPI)"]
        AUTH["RBAC Gatekeeper<br/>(customer, analyst, admin)"]
        LEDGER["Double-Entry Ledger Engine<br/>(Ascending Lock Ordering & Retry Loop)"]
        FRAUD["ML Fraud Triage Engine<br/>(Isolation Forest v1.0 + Rule Fallback)"]
        AUDIT["Tamper-Evident Audit Service<br/>(SHA-256 Hash Chain Verifier)"]
    end

    subgraph PostgreSQL["PostgreSQL 15+ (Source of Truth)"]
        ACCOUNTS["ACCOUNT Table<br/>(SELECT ... FOR UPDATE)"]
        TXNS["TRANSACTION Table"]
        LEDGER_PART["LEDGER_ENTRY Table<br/>(Range-Partitioned by Month)"]
        OUTBOX["OUTBOX Table<br/>(Transactional Outbox)"]
        AUDIT_TBL["AUDIT_LOG Table<br/>(Append-Only, SHA-256 Chained)"]
        TRIGGER["Deferred Constraint Trigger<br/>SUM(debits) = SUM(credits)"]
        MVIEWS["Materialized Views<br/>mv_account_balances & mv_daily_summary"]
    end

    subgraph OutboxWorker["Outbox Dispatcher (Worker Daemon)"]
        WORKER["Outbox Poller<br/>(Exponential Backoff & Retries)"]
    end

    subgraph NoSQL["NoSQL Auxiliary Stores"]
        REDIS["Redis 7+<br/>(Rolling Velocity Counters)"]
        MONGO["MongoDB 6+<br/>(Fraud Evidence Documents)"]
    end

    UI --> API
    API --> AUTH
    AUTH --> LEDGER
    LEDGER --> FRAUD
    FRAUD -.->|Velocity Check| REDIS
    LEDGER -->|Atomic Transaction Block| ACCOUNTS
    LEDGER -->|Balanced Entries| LEDGER_PART
    LEDGER_PART --- TRIGGER
    LEDGER -->|Record Outbox Event| OUTBOX
    LEDGER -->|Cryptographic Hash| AUDIT_TBL
    LEDGER --- MVIEWS

    WORKER -->|Poll PENDING Events| OUTBOX
    WORKER -->|INCR Velocity with TTL| REDIS
    WORKER -->|Upsert Evidence Document| MONGO
```

---

## 📋 12-Module Project Implementation Checklist

This project is built according to the comprehensive task checklist in [`documentation/Fraud Ledger — Project Checklist.html`](documentation/Fraud%20Ledger%20%E2%80%94%20Project%20Checklist.html). All **52 tasks across all 12 modules** are **100% completed**:

| Module | Scope & Objectives | Tasks | Status |
|---|---|:---:|:---:|
| **Module 1: Requirements & Schema Design** | 2-page synopsis, Chen-style ER diagram, 7-step ER-to-relational mapping, PostgreSQL DDL with CHECK constraints & FKs, peer/guide review | 5 / 5 | ✅ Complete |
| **Module 2: Core Ledger Engine (PostgreSQL)** | Customer, Account, Device, Merchant, Transaction, Ledger_Entry tables; deferred zero-sum trigger; cached balance & reconciliation query; transfer unit tests | 5 / 5 | ✅ Complete |
| **Module 3: Concurrency Control** | `SELECT ... FOR UPDATE` in ascending `account_id` order; deadlock & serialization retry loop with backoff; deliberate deadlock demo; isolation level benchmarks | 4 / 4 | ✅ Complete |
| **Module 4: Fraud Triage Pipeline** | 5-D feature extraction; Isolation Forest training; FastAPI scoring service (0-100 risk score); 3-tier triage thresholds (<50, 50-80, >80); end-to-end result & alert generation | 5 / 5 | ✅ Complete |
| **Module 5: NoSQL Integration (Outbox Pattern)** | Transactional Outbox table; asynchronous draining worker; Redis velocity counters (`INCR` with TTL); MongoDB alert evidence documents; NoSQL write failure retry tests; Redis vs SQL window query benchmarks | 6 / 6 | ✅ Complete |
| **Module 6: Audit & Tamper-Evidence** | Automated triggers writing to `AUDIT_LOG`; SHA-256 hash chaining (`prev_hash` $\to$ `row_hash`); append-only privilege restriction (`REVOKE UPDATE, DELETE`); tamper-detection test | 4 / 4 | ✅ Complete |
| **Module 7: Analyst Review Workflow** | Analyst & Analyst_Review tables; review endpoint & UI (`CONFIRM_FRAUD`, `FALSE_POSITIVE`, `ESCALATE`); state machine linking decision back to `FRAUD_ALERT.status` | 3 / 3 | ✅ Complete |
| **Module 8: Performance Optimization & Benchmarking** | Composite B-Tree indexes; Materialized Views (`mv_account_balances`, `mv_daily_transaction_summary`); monthly range partitioning; `EXPLAIN ANALYZE` reports; pgbench benchmarks across isolation levels | 5 / 5 | ✅ Complete |
| **Module 9: API & Application Layer** | FastAPI REST endpoints (transfers, accounts, reconciliation, alerts, reviews, audit); Pydantic validation; RBAC role separation (`customer`, `analyst`, `admin`) | 3 / 3 | ✅ Complete |
| **Module 10: Interactive UI Dashboard** | Transaction history feed; analyst alert queue with review modal; system benchmark charts view; cryptographic audit chain inspector | 3 / 3 | ✅ Complete |
| **Module 11: Testing & Evaluation** | Concurrency correctness tests; concurrent multi-threaded load tests; ML metrics evaluation report (Precision, Recall, F1); benchmark documentation | 4 / 4 | ✅ Complete |
| **Module 12: Documentation & Submission** | Academic project synopsis; Chen ER diagram & relational document; final project report (`Final_Project_Report.md`); demo script & viva voce Q&A guide (`Demo_Script_and_Viva_QA.md`) | 4 / 4 | ✅ Complete |
| **Total** | **Comprehensive DBMS Academic Implementation** | **52 / 52** | **100% Done** |

---

## ⚡ Key Engineering Pillars

### 1. ACID Double-Entry Bookkeeping & Reconciliation
- Every transfer operation generates a balanced pair: exactly one `DEBIT` and one `CREDIT` entry in `LEDGER_ENTRY`.
- Enforced at the database level via a PostgreSQL **deferred constraint trigger**:
  $$\sum \text{debits} = \sum \text{credits}$$
- Balance checks prevent overdrafts (`CHECK (balance >= 0)`).
- **Automated Balance Reconciliation (`m2-4`)**: Cached `Account.balance` is verified against the historical sum of double-entry rows via `/api/v1/accounts/reconcile/all`, immediately flagging discrepancies.

### 2. Deadlock-Free Concurrency Control & Retry Logic
- High-frequency transfers between account pairs in reverse directions (e.g., Alice $\to$ Bob and Bob $\to$ Alice simultaneously) can trigger circular wait deadlocks.
- The system enforces **deterministic ascending lock ordering** (`account_id ASC`) using `SELECT ... FOR UPDATE`:
  ```sql
  -- Always acquire lock on the lower account ID first
  SELECT account_id, balance FROM ACCOUNT 
  WHERE account_id IN (acc_min, acc_max) 
  ORDER BY account_id ASC 
  FOR UPDATE;
  ```
- **Serialization & Deadlock Retry Loop (`m3-2`)**: The Ledger Service wraps transaction execution in an exponential backoff loop with randomized jitter, catching transient `40001` (Serialization Failure) and `40P01` (Deadlock) errors and resolving them transparently.

### 3. Real-Time ML Fraud Triage & Fail-Safe Fallback
- **Feature Pipeline**:
  - Transfer amount in INR.
  - 1-hour rolling velocity counter (cached in Redis).
  - 30-day historical mean deviation (calculated from PostgreSQL history).
  - Temporal signals (hour of day, night-time transfer flags).
  - New device / fingerprint mismatch indicator.
- **Decision Engine**:
  - `Risk Score < 50`: **`APPROVE`** $\to$ Transaction completed immediately.
  - `50 <= Risk Score <= 80`: **`REVIEW`** $\to$ Transfer allowed; `FRAUD_ALERT` generated for analyst triage.
  - `Risk Score > 80`: **`ROLLBACK`** $\to$ Transfer aborted, status `ROLLED_BACK`, source account marked `FROZEN`.
- **Fail-Safe Fallback**: If the ML model artifact is missing or prediction encounters latency, the system safely defaults to a deterministic rule-based fallback (`amount > ₹50,000` or `velocity > 5` $\to$ REVIEW).
- **Evaluation Performance (`m11-3`)**: 99.70% Accuracy, 93.98% Precision, 100.00% Recall, and 0.9690 F1-Score.

### 4. Tamper-Evident SHA-256 Audit Log
- All mutations to sensitive tables (`ACCOUNT`, `TRANSACTION`, `LEDGER_ENTRY`) emit append-only audit records via triggers.
- Each audit record is cryptographically linked to its predecessor via SHA-256 hash chaining:
  $$\text{row\_hash} = \text{SHA256}(\text{prev\_hash} \parallel \text{table} \parallel \text{operation} \parallel \text{old\_json} \parallel \text{new\_json})$$
- The application database role possesses **`INSERT`-only permissions** on `AUDIT_LOG` (`REVOKE UPDATE, DELETE`).
- An integrated verification algorithm scans the chain and pinpoints the exact row ID if historical data was mutated or deleted.

### 5. Transactional Outbox & NoSQL Synchronization
- Avoids fragile Two-Phase Commit (2PC) or distributed locking.
- Ledger transactions insert an `OUTBOX` record inside the same PostgreSQL transaction block.
- An asynchronous daemon worker polls `PENDING` outbox events and updates:
  - **Redis 7**: Atomic increments of velocity counters (`INCR`, `EXPIRE`).
  - **MongoDB 6**: Upserts immutable fraud evidence documents (`alert_id` unique key).
- Implements exponential backoff with a 5-attempt retry limit and full fault tolerance against simulated NoSQL failures (`m5-5`).

### 6. Role-Based Access Control (RBAC)
Endpoints enforce privilege tiers via the `X-User-Role` HTTP header:
- **`customer`**: Transfer execution, account lookup, transaction history.
- **`analyst`**: Access fraud review queues, investigate alert details, submit review determinations (`CONFIRM_FRAUD` / `FALSE_POSITIVE` / `ESCALATE`).
- **`admin`**: Trigger cryptographic audit chain verification, balance reconciliation, inspect benchmark reports, seed synthetic data.

---

## 📁 Repository Structure

```
Financial-Transaction-Ledger-with-Real-Time-Fraud-Triage-/
├── backend/
│   ├── app/
│   │   ├── api/                 # FastAPI API route controllers
│   │   │   ├── accounts.py      # Account balance, listing & reconciliation endpoints
│   │   │   ├── admin.py         # Administrative & benchmark report endpoints
│   │   │   ├── audit.py         # Audit log query and hash verification endpoints
│   │   │   ├── customers.py    # Customer KYC management
│   │   │   ├── fraud.py        # Fraud alerts and analyst review workflows
│   │   │   ├── security.py     # Role-based access control (RBAC) dependencies
│   │   │   └── transactions.py # Transfer execution and double-entry handlers
│   │   ├── database/            # Database DDL, triggers & initial data
│   │   │   ├── schema.sql       # PostgreSQL 15+ table schemas, partitions & materialized views
│   │   │   ├── triggers.sql     # Deferred balance triggers & audit hooks
│   │   │   └── seed.py          # Synthetic dataset seeder & model initiator
│   │   ├── fraud/               # ML feature extraction & Isolation Forest model
│   │   │   ├── features.py      # Real-time feature extraction pipeline
│   │   │   ├── infer.py         # Risk scoring & 3-tier triage inference
│   │   │   ├── train.py         # Isolation Forest model training script
│   │   │   └── isolation_forest.joblib # Serialized model binary
│   │   ├── models/              # Pydantic validation schemas
│   │   ├── repositories/        # Database, Redis & MongoDB client wrappers
│   │   │   ├── db.py            # PostgreSQL connection pool & transaction manager
│   │   │   ├── mongo_repo.py    # MongoDB fraud evidence repository
│   │   │   └── redis_repo.py    # Redis velocity counter repository
│   │   ├── services/            # Core business & ledger logic
│   │   │   ├── audit_service.py # SHA-256 hash chaining & verification
│   │   │   └── ledger_service.py# Double-entry execution, ascending locks & retry loop
│   │   ├── workers/             # Transactional outbox asynchronous processor
│   │   │   └── outbox_worker.py # Background poller & retry dispatcher
│   │   ├── config.py            # Application settings and environment variables
│   │   └── main.py              # Application entrypoint & Jinja2 UI mount
│   └── frontend/
│       ├── static/              # Dark glassmorphism stylesheet & assets
│       │   └── css/style.css    # Responsive theme styling
│       └── templates/           # Jinja2 server-rendered views
│           ├── alerts.html      # Analyst fraud review queue
│           ├── audit.html       # Cryptographic audit log inspector
│           ├── benchmarks.html  # Database benchmarks & EXPLAIN reports
│           ├── history.html     # Double-entry ledger audit history
│           ├── index.html       # System dashboard with live stats
│           └── transfer.html    # Funds transfer terminal with real-time triage
├── benchmarking/
│   ├── demo_concurrency.py      # Multi-threaded deadlock-prevention script
│   ├── evaluate_fraud_metrics.py# ML Precision, Recall, F1 evaluation script (m11-3)
│   ├── explain_reports/         # Comprehensive database performance analyses
│   │   ├── fraud_model_metrics.md # Isolation Forest validation metrics (Precision/Recall/F1)
│   │   ├── index_benchmarks.md  # B-Tree index scan cost reductions
│   │   ├── isolation_benchmarks.md # Read Committed vs Serializable concurrency
│   │   ├── partition_benchmarks.md # Monthly partition pruning verification
│   │   └── redis_vs_sql_latency.md # Redis cache vs SQL aggregate speedups
│   └── pgbench_scripts/         # pgbench load-testing transactions
│       ├── read_history.sql
│       └── transfer.sql
├── docker/
│   ├── docker-compose.yml       # 4-container production topology
│   └── Dockerfile               # Backend container build specification
├── documentation/               # Course documentation & deliverables
│   ├── dbmsfinal_synopsis.docx  # 2-page project synopsis
│   ├── ER_Diagram_Fraud_Ledger_v2.png # Chen-style Entity-Relationship diagram
│   ├── Financial_Ledger_ER_Diagram_and_Schema.modified.pdf # Relational mapping specification
│   ├── Fraud Ledger — Project Checklist.html # Interactive 52-task verification checklist (100%)
│   ├── Final_Project_Report.md  # Comprehensive academic project report (m12-3)
│   ├── Demo_Script_and_Viva_QA.md # Step-by-step demo script & viva questions (m12-4)
│   └── System_Requirements_Financial_Ledger_Fraud_Triage.docx # System requirements specification
├── tests/                       # Pytest verification suite
│   ├── conftest.py              # Test database fixtures & offline bypass
│   ├── test_audit.py            # Cryptographic hash chain tamper tests
│   ├── test_concurrency.py      # Concurrent row locking & race condition tests
│   ├── test_fraud.py            # Fraud engine & fail-safe fallback tests
│   ├── test_ledger.py           # Double-entry balancing & reconciliation tests
│   ├── test_outbox.py           # Outbox retry & NoSQL failure simulation tests (m5-5)
│   └── test_security.py         # RBAC role gating tests
├── requirements.txt             # Python dependencies
├── .gitignore                   # Ignored files (virtualenvs, databases, logs)
└── README.md                    # Project documentation
```

---

## 🗄 Database Schema, Partitioning & Materialized Views

The relational schema implements **12 normalized tables** and **2 materialized views** in PostgreSQL:

| Relation / View | Purpose | Integrity Constraint |
|---|---|---|
| `CUSTOMER` | Customer identity & KYC status | `UNIQUE(email)`, `CHECK (kyc_status)` |
| `DEVICE` | Fingerprint tracking for velocity & anomaly detection | FK to `CUSTOMER` |
| `MERCHANT` | Merchant directory & categories | ISO 2-letter country code |
| `ACCOUNT` | Monetary balances (cached) | `CHECK (balance >= 0)`, Row-lock target |
| `TRANSACTION` | Transfer header & execution lifecycle | `CHECK (status IN ('PENDING', 'COMMITTED', 'ROLLED_BACK'))` |
| `LEDGER_ENTRY` | **Range-partitioned** double-entry book | Partitioned by `created_at` (Monthly ranges) |
| `FRAUD_RESULT` | ML score (0-100), model version, triage action | Unique FK to `TRANSACTION` |
| `FRAUD_ALERT` | Actionable queue for high/medium severity alerts | Unique FK to `FRAUD_RESULT`, `CHECK (status)` |
| `ANALYST` | Fraud analyst directory & credentials | Primary key `analyst_id` |
| `ANALYST_REVIEW` | Audit trail of manual fraud reviews | `CHECK (decision IN ('CONFIRM_FRAUD', 'FALSE_POSITIVE', 'ESCALATE'))` |
| `OUTBOX` | Transactional outbox records | Status: `PENDING`, `SENT`, `FAILED` (with `OUTBOX_EVENT` view) |
| `AUDIT_LOG` | Tamper-evident cryptographic ledger | Append-only, SHA-256 hash-chained |
| `mv_account_balances` | Materialized view: Cached vs calculated ledger balance | `UNIQUE INDEX` on `account_id` |
| `mv_daily_transaction_summary` | Materialized view: Daily volume, avg amount & alert counts | B-Tree index on `summary_date` |

---

## 🖥 Interactive UI Dashboard

The system includes a pre-built glassmorphism web interface accessible via browser:

- **Dashboard (`/`)**: Real-time overview of total active accounts, system balance, open fraud alerts, and pending outbox events.
- **Transfer Terminal (`/ui/transfer`)**: Interactive funds transfer console with live feedback displaying transaction status, ML risk score, and triage decision.
- **Ledger History (`/ui/history`)**: Filterable transaction book with balanced debit/credit pairs.
- **Fraud Alert Desk (`/ui/alerts`)**: Fraud analyst console to inspect flagged transactions and resolve open alerts (`CONFIRM_FRAUD`, `FALSE_POSITIVE`, `ESCALATE`).
- **Audit Log Inspector (`/ui/audit`)**: Real-time hash chain viewer featuring an interactive **Verify Hash Chain** button that highlights tamper events.
- **Benchmark Reports (`/ui/benchmarks`)**: Database latency, indexing, and isolation reports rendered directly in the browser.

---

## 🔌 API Reference

### Core Endpoints

| Method | Endpoint | Allowed Roles | Description |
|---|---|---|---|
| `POST` | `/api/v1/transactions` | `customer`, `admin` | Executes double-entry funds transfer with real-time fraud triage |
| `GET` | `/api/v1/transactions/{txn_id}` | `customer`, `admin` | Returns details and ledger legs of a transaction |
| `GET` | `/api/v1/transactions/account/{account_id}` | `customer`, `admin` | Returns all transaction entries for an account |
| `GET` | `/api/v1/accounts/{account_id}` | `customer`, `admin` | Returns account balance, account type, and status |
| `GET` | `/api/v1/accounts` | `customer`, `admin` | Lists all customer accounts |
| `GET` | `/api/v1/accounts/reconcile/all` | `admin` | Reconciles cached balances against ledger entries across all accounts |
| `GET` | `/api/v1/accounts/{account_id}/reconcile` | `admin` | Performs balance reconciliation query for a single account |
| `GET` | `/api/v1/fraud/alerts` | `analyst`, `admin` | Lists open fraud triage alerts |
| `GET` | `/api/v1/fraud/analysts` | `analyst`, `admin` | Lists all registered fraud analysts |
| `POST` | `/api/v1/fraud/alerts/{alert_id}/review` | `analyst`, `admin` | Submits fraud analyst determination (`CONFIRM_FRAUD` / `FALSE_POSITIVE` / `ESCALATE`) |
| `GET` | `/api/v1/audit/verify/chain` | `admin` | Validates SHA-256 chain continuity and detects tampering |
| `GET` | `/api/v1/audit/{table_name}` | `admin` | Retrieves append-only audit trail records for a specific table |
| `GET` | `/api/v1/admin/benchmarks` | `admin` | Returns database benchmark reports and metrics |
| `GET` | `/api/v1/admin/outbox/status` | `admin` | Returns outbox worker queue metrics |
| `POST` | `/api/v1/admin/outbox/process` | `admin` | Manually triggers outbox event draining |
| `POST` | `/api/v1/admin/seed` | `admin` | Re-seeds synthetic transactions and accounts |

Interactive OpenAPI Swagger documentation is available at `http://localhost:8000/docs`.

---

## 🚀 Quickstart & Execution Guide

### Option A: Docker Compose (Recommended)

Spin up the entire stack (PostgreSQL 15, Redis 7, MongoDB 6, FastAPI backend) with one command:

```bash
docker-compose -f docker/docker-compose.yml up --build
```

- Web UI: **`http://localhost:8000`**
- Interactive Swagger API: **`http://localhost:8000/docs`**
- PostgreSQL: Port `5432` (db: `ledger_db`, user: `ledger_user`, pass: `ledger_password`)
- Redis: Port `6379`
- MongoDB: Port `27017`

### Option B: Local Environment Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/praneel24eb-cyber/Financial-Transaction-Ledger-with-Real-Time-Fraud-Triage-.git
   cd Financial-Transaction-Ledger-with-Real-Time-Fraud-Triage-
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables** (or create a `.env` file):
   ```env
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_DB=ledger_db
   POSTGRES_USER=ledger_user
   POSTGRES_PASSWORD=ledger_password
   REDIS_HOST=localhost
   REDIS_PORT=6379
   MONGO_URI=mongodb://localhost:27017
   MONGO_DB_NAME=fraud_triage_db
   ```

5. **Initialize PostgreSQL database & schema**:
   ```bash
   psql -U ledger_user -d ledger_db -f backend/app/database/schema.sql
   psql -U ledger_user -d ledger_db -f backend/app/database/triggers.sql
   ```

6. **Start the FastAPI application**:
   ```bash
   python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

---

## 🧪 Verification & Benchmarks

### 1. Pytest Test Suite
Run the automated test suite covering double-entry balancing, concurrency, cryptographic audit chaining, fraud triage, outbox fault tolerance, and RBAC:
```bash
python -m pytest -v tests/
```

### 2. ML Fraud Model Evaluation (Precision, Recall, F1)
Evaluate the Isolation Forest anomaly detector on a validation set:
```bash
python benchmarking/evaluate_fraud_metrics.py
```
**Results:**
- **Accuracy:** `99.70%`
- **Precision:** `93.98%`
- **Recall (Sensitivity):** `100.00%`
- **F1-Score:** `0.9690`
- **False Positive Rate:** `0.32%`
- **ROC-AUC:** `1.0000`

### 3. Concurrency & Deadlock Prevention Demo
Execute the multi-threaded race condition benchmark:
```bash
python benchmarking/demo_concurrency.py
```
This script launches concurrent threads transferring funds in opposite directions between the same account pair, confirming:
- **Zero deadlocks** due to deterministic ascending lock ordering (`account_id ASC`).
- **Zero lost updates** and precise preservation of total system balance.

### 4. Database Performance Reports
The `benchmarking/explain_reports/` directory contains full `EXPLAIN ANALYZE` reports:
- **`fraud_model_metrics.md`**: Validation results across precision, recall, and false positive rates.
- **`isolation_benchmarks.md`**: Empirical throughput and latency across `Read Committed`, `Repeatable Read`, and `Serializable`.
- **`index_benchmarks.md`**: Query execution cost reductions achieved with composite indexing.
- **`partition_benchmarks.md`**: Partition pruning verification across monthly ranges.
- **`redis_vs_sql_latency.md`**: Latency comparison between Redis in-memory velocity counters ($<1\text{ ms}$) and repeated SQL aggregations ($24\text{ ms}$).

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
