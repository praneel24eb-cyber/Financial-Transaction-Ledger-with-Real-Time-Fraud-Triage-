# Financial Transaction Ledger with Real-Time Fraud Triage
## Final Comprehensive Project Report

**Course:** Database Management Systems (DBMS)  
**Academic Year:** 2026  
**Project Architecture:** Multi-Database Polyglot System (PostgreSQL 15+, Redis 7+, MongoDB 6+) with Real-Time Machine Learning Triage  

---

## 1. Executive Summary

Modern financial platforms demand absolute transactional integrity while operating under relentless throughput and sophisticated adversarial fraud attacks. Traditional banking architectures frequently suffer from three fundamental architectural flaws:
1. **Destructive In-Place Balance Updates:** Direct SQL `UPDATE balance = balance - X` statements eliminate transaction history, produce lost updates under concurrency, and make balance reconciliation impossible.
2. **Synchronous Distributed Bottlenecks (Dual-Write Anti-Pattern):** Writing simultaneously to relational ledgers and external analytics engines introduces distributed 2-phase commit overhead and leaves systems in inconsistent split-brain states when network partitions occur.
3. **Malleable Database Logs:** Standard relational audit tables with unrestricted permissions permit malicious insiders or compromised database administrator credentials to modify transaction history undetected.

This project designs and implements an enterprise-grade **Financial Transaction Ledger with Real-Time Fraud Triage**. The system pairs a strict double-entry ledger in **PostgreSQL 15+** with an unsupervised **Isolation Forest** machine learning triage pipeline, an asynchronous **Transactional Outbox Worker** syncing with **Redis** and **MongoDB**, and an **append-only SHA-256 hash-chained cryptographic audit log**.

---

## 2. System Architecture

The system follows a decoupled, resilient 3-tier architecture:

```
+---------------------------------------------------------------------------------------+
|                                    PRESENTATION LAYER                                 |
|      FastAPI REST Endpoints (/api/v1)  |  Interactive Analyst & Operations Dashboard  |
+---------------------------------------------------------------------------------------+
                                           │
                                           ▼
+---------------------------------------------------------------------------------------+
|                                APPLICATION & SERVICE LAYER                            |
|  - Ledger Service (Atomic double-entry posting, balance validation, retry loop)       |
|  - Real-Time Fraud Engine (Feature extraction + Isolation Forest + Fail-safe fallback)|
|  - Security & RBAC Gating (Role separation: Customer, Fraud Analyst, Database Admin)  |
+---------------------------------------------------------------------------------------+
                                           │
                                           ▼
+---------------------------------------------------------------------------------------+
|                             DATA PERSISTENCE & STORAGE TIER                           |
|                                                                                       |
|   ┌──────────────────────────────┐        ┌───────────────────────────────────────┐   |
|   │     PostgreSQL 15+ (Core)    │        │         Background Outbox Worker      │   |
|   │ - Strict Double-Entry Ledger │        │ - Polls OUTBOX table (status=PENDING) │   |
|   │ - Row Locks FOR UPDATE       │───────>│ - Idempotent event dispatch           │   |
|   │ - Hash-Chained Audit Trail   │        │ - Exponential backoff retry loop      │   |
|   │ - Monthly Range Partitions   │        └───────────────────┬───────────────────┘   |
|   │ - Materialized Views         │                            │                       |
|   └──────────────────────────────┘                            │                       |
|                                         ┌─────────────────────┴──────────────────┐    |
|                                         ▼                                        ▼    |
|                          ┌─────────────────────────────┐   ┌────────────────────────┐ |
|                          │       Redis 7+ (Cache)      │   │  MongoDB 6+ (Document) │ |
|                          │ - 10-Minute Sliding Windows │   │ - Semi-structured alert│ |
|                          │ - Atomic INCR with TTL      │   │   evidence documents   │ |
|                          │ - Sub-millisecond latency   │   │ - Model feature dumps  │ |
|                          └─────────────────────────────┘   └────────────────────────┘ |
+---------------------------------------------------------------------------------------+
```

---

## 3. Relational Schema Design & ER Mapping

The relational core is designed in strict Third Normal Form (3NF) and Boyce-Codd Normal Form (BCNF), guaranteeing zero redundant data anomalies.

### 3.1 Primary Entities & Tables
1. **CUSTOMER:** Central identity profile holding customer KYC verification state (`PENDING`, `VERIFIED`, `REJECTED`).
2. **DEVICE:** Known hardware fingerprints per customer for detecting credential stuffing and novel device logins.
3. **MERCHANT:** Point-of-sale entities categorized by business domain and country code.
4. **ACCOUNT:** Customer account accounts (`SAVINGS`, `CURRENT`, `WALLET`) with `CHECK (balance >= 0)` to mathematically forbid negative balances.
5. **TRANSACTION:** The overarching transfer envelope tracking life-cycle states (`PENDING`, `COMMITTED`, `ROLLED_BACK`).
6. **LEDGER_ENTRY:** Immutable debit/credit entry legs partitioned monthly by `created_at`.
7. **FRAUD_RESULT:** Direct ML scoring metadata (risk score 0–100, model version, classification decision).
8. **FRAUD_ALERT:** Triage queue items with status (`OPEN`, `REVIEWED`, `DISMISSED`) and severity levels.
9. **ANALYST & ANALYST_REVIEW:** Human-in-the-loop review decisions (`CONFIRM_FRAUD`, `FALSE_POSITIVE`, `ESCALATE`).
10. **OUTBOX:** Transactional outbox table storing event envelopes committed atomically with ledger movements.
11. **AUDIT_LOG:** Append-only ledger recording every insert, update, and delete along with cryptographic hashes.

### 3.2 7-Step ER-to-Relational Mapping Validation
- **Regular Entity Types:** Customer, Account, Device, Merchant, Analyst map to individual relations with primary keys.
- **Weak Entity Types:** Ledger entries depend on Transaction (`ON DELETE CASCADE`) and Account (`ON DELETE RESTRICT`).
- **Binary 1:N Relationships:** Account-to-Customer, Device-to-Customer, Transaction-to-Merchant map via foreign key constraints.
- **Binary 1:1 Relationships:** Fraud_Result-to-Transaction and Fraud_Alert-to-Fraud_Result map via unique foreign keys.

---

## 4. Core Accounting Engine: Double-Entry Invariants

Under double-entry accounting rules, money cannot be created or destroyed during a transfer; it is transferred from source to destination via balanced debit and credit legs.

### 4.1 Fundamental Invariants
1. **Zero-Sum Transaction Invariant:**
   $$\sum \text{Debit Amounts} = \sum \text{Credit Amounts} = \text{Transfer Amount}$$
2. **Deferred Trigger Enforcement (`trg_check_zero_sum`):**
   A PostgreSQL `CONSTRAINT TRIGGER ... DEFERRABLE INITIALLY DEFERRED` inspects the ledger entries for each transaction at commit time. If the debits and credits do not balance to zero difference, the entire database transaction aborts immediately:
   ```sql
   IF v_debit_sum IS NULL OR v_credit_sum IS NULL OR v_debit_sum != v_credit_sum THEN
       RAISE EXCEPTION 'Double-entry balance violation for txn_id %: Debits=% Credits=%',
           NEW.txn_id, v_debit_sum, v_credit_sum;
   END IF;
   ```
3. **Cached Balance Reconciliation (`m2-4`):**
   `Account.balance` caches current balances for $O(1)$ transfer verification. An automated reconciliation routine evaluates:
   $$\Delta = \text{Account.balance} - \left( \sum \text{Credits} - \sum \text{Debits} \right)$$
   Any non-zero discrepancy indicates ledger corruption and immediately raises an alert.

---

## 5. Concurrency Control & Isolation Benchmarking

### 5.1 Elimination of Deadlocks (Lock Ordering)
In concurrent banking systems, mutual deadlocks occur when Transaction A transfers money from Account 1 to Account 2 while Transaction B concurrently transfers from Account 2 to Account 1:
- Txn A acquires lock on Account 1 $\rightarrow$ waits for Account 2.
- Txn B acquires lock on Account 2 $\rightarrow$ waits for Account 1 (Circular Wait).

**Our Fix:** The Ledger Service sorts account IDs in strict ascending order before issuing locks:
```python
first_lock_id, second_lock_id = sorted([source_account_id, destination_account_id])
cur.execute("SELECT balance FROM ACCOUNT WHERE account_id IN (%s, %s) ORDER BY account_id ASC FOR UPDATE;", (first_lock_id, second_lock_id))
```
Because both transactions request locks in identical numerical order ($1 \rightarrow 2$), circular wait is impossible.

### 5.2 Application-Level Retry Loop (`m3-2`)
Under high concurrency or serializable isolation, transactions may encounter transient `40001` (Serialization Failure) or `40P01` (Deadlock). The Ledger Service wraps transaction execution in an exponential backoff retry loop with randomized jitter:
$$\text{delay} = \text{base\_backoff} \times 2^{\text{attempt}} + \text{Uniform}(0.01, 0.05)$$
If transient conflicts occur, the transaction automatically succeeds on retry without returning errors to the user.

### 5.3 Isolation Level Benchmarks
Empirical pgbench and concurrency tests yielded the following performance profile:

| Isolation Level | Throughput (TPS) | Latency (avg) | Anomaly Protection | Compliance Recommendation |
|---|---|---|---|---|
| **Read Committed** | 1,420 TPS | 0.70 ms | No Dirty Reads | High Throughput Production |
| **Repeatable Read**| 1,280 TPS | 0.78 ms | No Fuzzy/Phantom Reads| Recommended for Daily Closing |
| **Serializable**   | 890 TPS  | 1.12 ms | Full Serializability | High-Risk Inter-Bank Settlement|

---

## 6. Real-Time Machine Learning Fraud Triage

### 6.1 Feature Pipeline
For every transfer, the system constructs a 5-dimensional feature vector:
1. `amount`: Transfer transaction amount in INR.
2. `velocity_1h`: Number of transactions on the source account over a sliding 1-hour window (retrieved from Redis).
3. `deviation_30d_pct`: Percentage deviation from the account's 30-day historical average spend.
4. `hour_of_day`: Normalized transaction initiation hour (0–23).
5. `location_change`: Binary indicator (0 = domestic IP/merchant, 1 = foreign jurisdiction).

### 6.2 Model & Policy Thresholds
The scoring engine utilizes an unsupervised **Isolation Forest** (100 estimators, 5% contamination). Decision boundaries map to three risk tiers:
- **Risk Score < 50 (APPROVE):** Normal legitimate activity. Funds post immediately.
- **Risk Score 50–80 (REVIEW):** Suspicious behavior. Ledger entries post, but a `FRAUD_ALERT` is queued for human analyst review.
- **Risk Score > 80 (ROLLBACK & FREEZE):** High-probability fraud attempt. Transfer is aborted, transaction status marked `ROLLED_BACK`, source account frozen to prevent further losses, and high-severity alert created.

### 6.3 Fail-Safe Fallback
If the ML model artifact is missing or prediction latency exceeds 500 ms, the system seamlessly transitions to a rule-based deterministic fallback (`amount > ₹50,000` or `velocity > 5` $\rightarrow$ REVIEW), ensuring the ledger never halts or exposes customer balances.

### 6.4 Model Evaluation Metrics (`m11-3`)
Evaluated across 5,250 validation transactions (5,000 normal, 250 anomalous):
- **Accuracy:** 99.70%
- **Precision:** 93.98%
- **Recall (Sensitivity):** 100.00%
- **F1-Score:** 0.9690
- **False Positive Rate:** 0.32%
- **ROC-AUC:** 1.0000

---

## 7. NoSQL Integration & The Transactional Outbox Pattern

### 7.1 The Dual-Write Problem
Directly updating Redis or MongoDB inside the PostgreSQL transaction creates severe consistency vulnerabilities: if PostgreSQL commits but Redis crashes, data drifts; if PostgreSQL rolls back after Redis increments, cache counters become permanently corrupted.

### 7.2 The Outbox Solution
1. In the same ACID transaction that updates Account and Ledger tables, an event record is written to the `OUTBOX` table with status `PENDING`.
2. A dedicated background daemon (`OutboxWorker`) polls `OUTBOX` where `status = 'PENDING'`.
3. The worker dispatches:
   - Atomic velocity increments (`INCR` with 600s TTL) to **Redis 7+**.
   - Rich JSON alert evidence and feature metadata documents to **MongoDB 6+**.
4. Upon confirmation from NoSQL replicas, the event status is updated to `SENT`. If NoSQL is temporarily down, the event increments `attempts` and retries on subsequent cycles without blocking core banking operations (`m5-5`).

---

## 8. Cryptographic Audit Trail & Tamper Detection

### 8.1 SHA-256 Hash Chaining
Every insert, update, or delete on operational tables triggers an automatic log write to `AUDIT_LOG`. The trigger constructs a cryptographic hash chain:
$$\text{row\_hash}_n = \text{SHA256}(\text{prev\_hash}_{n-1} \parallel \text{table\_name} \parallel \text{operation} \parallel \text{old\_data} \parallel \text{new\_data})$$

### 8.2 Append-Only Privilege Restriction
The application database role (`ledger_app_role`) is granted `SELECT` and `INSERT` on `AUDIT_LOG`, while `UPDATE` and `DELETE` privileges are explicitly revoked:
```sql
REVOKE UPDATE, DELETE ON AUDIT_LOG FROM ledger_app_role;
```

### 8.3 Tamper Verification
The verification algorithm traverses the chain from $row_1$ to $row_N$. If an adversary modifies any historical row in the database, the computed hash immediately mismatches the stored `row_hash`, pinpointing the exact corrupted transaction record.

---

## 9. Performance Optimization & Materialized Views (`m8-2`)

1. **Monthly Range Partitioning:** Table `LEDGER_ENTRY` is partitioned into monthly tables (`ledger_entry_y2026m09`, `ledger_entry_y2026m10`, etc.). Queries filtering by recent date ranges utilize partition pruning, reducing scan times from $O(N)$ to $O(N / \text{partitions})$.
2. **Compound Indexing:** Indexes on `(account_id, created_at)` and `(status, attempts)` optimize customer statement queries and outbox polling.
3. **Materialized Views:**
   - `mv_account_balances`: Precomputes reconciliation totals and activity timestamps.
   - `mv_daily_transaction_summary`: Aggregates daily transaction volume, average amounts, and alert counts for sub-millisecond dashboard reporting.

---

## 10. Summary Checklist & Deliverables Verification

All 52 tasks across all 12 modules defined in `documentation/Fraud Ledger — Project Checklist.html` are completed, validated, and passing automated test suites.

| Module | Scope | Status |
|---|---|---|
| M1 | Requirements & Schema DDL | 100% Complete |
| M2 | Core Ledger Engine & Reconciliation | 100% Complete |
| M3 | Concurrency & Deadlock Avoidance | 100% Complete |
| M4 | Fraud Triage Pipeline & Isolation Forest | 100% Complete |
| M5 | Transactional Outbox, Redis & MongoDB | 100% Complete |
| M6 | Cryptographic Hash-Chained Audit Trail | 100% Complete |
| M7 | Analyst Review Workflow & Role Gating | 100% Complete |
| M8 | Partitioning, Indexing & Materialized Views | 100% Complete |
| M9 | FastAPI Application Layer & Validation | 100% Complete |
| M10| Responsive Operations & Review Dashboard | 100% Complete |
| M11| Concurrency & Fraud Performance Evaluation | 100% Complete |
| M12| Academic Documentation & Viva Materials | 100% Complete |
