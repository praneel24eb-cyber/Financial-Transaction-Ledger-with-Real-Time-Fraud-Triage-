# LedgerGuard — Live Project Demo & Viva Defense Guide

This document provides a comprehensive, start-to-finish walkthrough to present and defend the **LedgerGuard (Financial Transaction Ledger with Real-Time Fraud Triage)** project during an in-person live demo, lab evaluation, or viva examination.

---

## 🏛️ 1. Technical Architecture & System Pitch

When introducing the project, open with this crisp, technical definition:

> *"LedgerGuard is an enterprise financial transaction engine built with **PostgreSQL 15+** as an immutable, strictly consistent double-entry ACID ledger. It integrates real-time **Isolation Forest Machine Learning fraud triage**, a **Transactional Outbox Pattern** for asynchronous synchronization across **Redis 7** and **MongoDB 6**, and an append-only **SHA-256 cryptographic audit chain** to guarantee tamper evidence."*

### Why Polyglot Persistence? (SQL vs. NoSQL)
| Database Engine | Category | Role in LedgerGuard | Why this specific DBMS? |
| :--- | :--- | :--- | :--- |
| **PostgreSQL 15+** | Relational (SQL) | Primary Source of Truth: Accounts, Transactions, Double-entry Ledger, Audit Chain | **Strict ACID Guarantees**, pessimistic row locks (`SELECT ... FOR UPDATE`), deferred constraint triggers, table range-partitioning. |
| **Redis 7** | Key-Value In-Memory Cache | Real-time sliding-window transaction velocity counters (`INCR`, `EXPIRE`) | **Sub-millisecond latency** (~0.4ms) for hot-path anomaly detection without bottlenecking SQL disk I/O. |
| **MongoDB 6** | Document Store (NoSQL) | Fraud Evidence Documents, Raw Outbox Payloads, ML Telemetry | **Schema-flexible storage** for arbitrary ML decision trees, JSON explanation vectors, and audit documents that shouldn't bloat normalized SQL tables. |

---

## 🚀 2. Complete End-to-End User Testing Scenario

Here is one **continuous, live narrative journey** you can perform directly in front of the evaluators.

```
[Start: Dashboard] ➔ [Scenario A: Legitimate Transfer] ➔ [Scenario B: Suspicious Transfer] ➔ [Scenario C: High-Risk Attack Blocked] ➔ [Inspect Ledger] ➔ [Analyst Triage] ➔ [Tamper Test] ➔ [Benchmarks]
```

---

### Step 1: Open the Application & Check Baseline State
1. **Action:** Navigate to **`http://localhost:8000/`** (🏠 Dashboard).
2. **What to show the evaluator:**
   * **Total Accounts:** 15 accounts seeded.
   * **Total System Deposits:** ~₹868,000+ total balance.
   * **Live Transaction Feed:** Point out the top glowing ticker bar continuously displaying recent transactions.
   * **Account List:** Show **Account #1** (Balance: ~₹52,189) and **Account #2** (Balance: ~₹63,164). Note their current balances before performing any transfers.

---

### Step 2: Scenario A — Execute a Legitimate User Transfer (Low Risk < 50)
1. **Action:** Click **💸 Transfer** on the top navigation bar (`/ui/transfer`).
2. **User Inputs to enter:**
   * **From Account:** Select `Account #1`
   * **To Account:** Select `Account #2`
   * **Amount (₹):** Enter `1500.00`
   * **Device ID:** Enter `1` (Customer's known, regular smartphone)
   * **Isolation Level:** Leave as `READ COMMITTED`
3. **Click:** **"Run Fraud Triage & Transfer"**.
4. **Immediate Output Observed:**
   * A vibrant green **✅ Transfer Approved** card appears.
   * **Source New Balance:** Exactly ₹1,500 deducted.
   * **Destination New Balance:** Exactly ₹1,500 credited.
   * **Transaction ID:** Note the generated ID (e.g. `#41`).
5. **What to Explain to the Evaluator:**
   * *"The transaction executed atomically in PostgreSQL. Isolation Forest scored this under 50 because the device is familiar, volume is normal, and velocity is low. Both account balances updated simultaneously."*

---

### Step 3: Scenario B — Execute a Suspicious Transfer (Medium Risk 50–80)
1. **Action:** Click the amber button: **🟡 Simulate Review** on the Transfer page.
   * It automatically pre-fills: Amount = `4500.00` (elevated 200% above 30-day average), Device ID = `1` (not in the DEVICE table — treated as unknown device by ML).
2. **Click:** **"Run Fraud Triage & Transfer"** (the button auto-submits).
3. **Immediate Output Observed:**
   * An amber card appears with a subtle badge: **`Under Review`**.
   * Status: *"Transaction Submitted — Your transaction is being processed."*
4. **What to Explain to the Evaluator:**
   * *"Notice that the customer is NOT told about fraud or ML scores. Customers are never alerted to internal risk thresholds. However, behind the scenes, PostgreSQL flagged the transaction as REVIEW, and the Outbox worker queued it for human review."*
   * *"Device ID 42 doesn't exist in the DEVICE table — the backend detects this and passes NULL as device_id to avoid FK violations, while still setting device_changed=1.0 in the ML feature vector. The Isolation Forest scores this as 50–80 due to the elevated amount + unknown device combination."*

---

### Step 4: Scenario C — Trigger an Attack Simulation (High Risk > 80)
1. **Action:** Click the red button: **🎯 Simulate High Risk**.
   * It automatically pre-fills: Amount = `75000.00` (far above 30-day average) and Device ID = `999` (flagged malicious device).
2. **Click:** **"Run Fraud Triage & Transfer"**.
3. **Immediate Output Observed:**
   * A red warning card appears: **`Transaction Could Not Be Completed`**.
   * Detail message: *"We couldn't complete this transaction. Please contact support."*
4. **What to Explain to the Evaluator:**
   * *"Isolation Forest detected this as an extreme statistical outlier (Score > 80). The backend issued an immediate PostgreSQL `ROLLBACK`. Not a single rupee moved, no partial state exists, and the customer receives a neutral, deliberate message that avoids leaking fraud parameters to attackers."*

---

### Step 5: Verify the Double-Entry Ledger (`/ui/history`)
1. **Action:** Click **📒 Ledger** on the navigation bar (`/ui/history`).
2. **What to do:**
   * Look at the top rows.
   * **Show the paired entries:** Find Transaction `#41` (from Scenario A).
   * Notice row 1: `Account #1` | `↓ DEBIT` | `-₹1500.00`.
   * Notice row 2: `Account #2` | `↑ CREDIT` | `+₹1500.00`.
   * **Click on the row:** It expands to show transaction metadata, timestamps, and explains the double-entry invariant.
   * Filter the table using the **Filter Account** dropdown to show only `Account #1`.
3. **What to Explain (DBMS Concept):**
   * *"In enterprise banking, balances are never arbitrarily modified. We enforce double-entry bookkeeping using PostgreSQL's deferred constraint trigger (`check_ledger_balance`). If `SUM(debits) != SUM(credits)` when the transaction commits, PostgreSQL raises an exception and aborts."*

---

### Step 6: Step into the Fraud Analyst Dashboard (`/ui/alerts`)
1. **Action:** Click **🚨 Fraud Alerts** on the navigation bar (`/ui/alerts`).
2. **What to do:**
   * Point out the open alerts queue. Locate the alert from **Scenario B**.
   * Notice the circular **Risk Score badge** (e.g., `68/100`) and Severity (`MEDIUM` or `HIGH`).
   * Click **Review** on the alert row.
3. **Show the Analyst Side-Panel:**
   * Show the **ML Evidence** section: It displays the explanation string, feature vector, and rule hits synced asynchronously to **MongoDB**.
   * **Enter Review Action:**
     * Analyst ID: `1`
     * Review Decision: Select `CONFIRM_FRAUD` or `FALSE_POSITIVE`.
     * Analyst Notes: Type *"Verified with customer via 2FA phone confirmation."*
   * Click **Submit Decision**.
4. **Immediate Output Observed:**
   * The alert row visually marks as `REVIEWED`, updates its badge, and closes the ticket.
5. **What to Explain (Polyglot / NoSQL Concept):**
   * *"Relational SQL is used for core money movement, while MongoDB stores rich, polymorphic ML evidence trees. The Transactional Outbox Pattern guaranteed that PostgreSQL committed the transfer first, and MongoDB received the evidence document asynchronously with zero message loss."*

---

### Step 7: Prove Tamper-Evidence via the Cryptographic Audit Chain (`/ui/audit`)
1. **Action:** Click **🔒 Audit Chain** on the navigation bar (`/ui/audit`).
2. **What to do:**
   * Show the table of append-only audit entries containing `Prev Hash` and `Row Hash`.
   * **Step A:** Click **🔒 Verify Chain Integrity**.
     * **Result:** A green confirmation banner: **✔ Audit Chain 100% Valid**.
     * Explain: *"The backend just computed a full SHA-256 hash recalculation from row #1 to the latest row. Every row's hash matches."*
   * **Step B (The Attack Test):** Click **🧪 Corrupt a Row (Demo)**.
     * The top row's checkmark flips to **❌ TAMPERED**.
     * A red alert appears: **❌ TAMPERING DETECTED**.
   * **Step C:** Click **🧪 Corrupt a Row (Demo)** again to restore it back to **✅**.
3. **What to Explain (DBMS & Security Concept):**
   * *"Every mutation on `ACCOUNT`, `TRANSACTION`, and `LEDGER_ENTRY` fires an append-only trigger that chains hashes:*
     $$\text{Row\_Hash} = \text{SHA-256}(\text{Prev\_Hash} \mathbin{\Vert} \text{Table} \mathbin{\Vert} \text{Op} \mathbin{\Vert} \text{Old\_Data} \mathbin{\Vert} \text{New\_Data})$$
   * *If an employee with root database access tampers with an account balance directly in SQL (`UPDATE account SET balance = 9999999`), the subsequent hash chain breaks immediately, alerting auditors."*

---

### Step 8: Conclude with Performance & Benchmarks (`/ui/benchmarks`)
1. **Action:** Click **⚡ Benchmarks** on the navigation bar (`/ui/benchmarks`).
2. **What to show on screen:**
   * **Chart.js Bar Chart:** Visualizes Throughput (TPS) across the three isolation levels:
     * **Read Committed:** ~1,850 TPS
     * **Repeatable Read:** ~1,200 TPS
     * **Serializable:** ~620 TPS
   * **Simulate Load Button:** Click **🔁 Simulate Concurrent Load** to trigger active concurrent outbox processing live.
   * **EXPLAIN ANALYZE comparison table:**
     * **Sequential Scan (Before Index):** 14.2 ms execution time.
     * **Index Scan (After Index `idx_ledger_account_time`):** 0.8 ms execution time (**17.75× speedup**).
     * **Redis vs SQL Aggregate:** 0.4 ms in Redis vs 3.1 ms in PostgreSQL.
3. **What to Explain (DBMS Engineering):**
   * *"By combining `READ COMMITTED` with ascending primary-key row locks (`account_id ASC`), our ledger achieves the strict correctness of Serializable isolation while retaining the high throughput of Read Committed."*

---

## 🎯 3. Panel-by-Panel Summary Table (Quick Cheat Sheet)

| Panel / URL | What You Click / Enter | What the System Does | Key Theory / Concept to Speak |
| :--- | :--- | :--- | :--- |
| **🏠 Dashboard** (`/`) | Inspect cards and live ticker | Polls `/api/v1/transactions` every 8s | Single Source of Truth; Outbox queue depth. |
| **💸 Transfer** (`/ui/transfer`) | Select Acc #1 ➔ Acc #2, enter ₹1,500, click *Run Transfer* | Atomically locks accounts in ASC order, fits features into Isolation Forest, commits balanced ledger entries | Deadlock avoidance (`min, max`), Isolation Forest score < 50, ACID atomicity. |
| **💸 High Risk** (`/ui/transfer`) | Click *Simulate High Risk* (₹75,000, Device 999) | Isolation Forest detects outlier score > 80; SQL `ROLLBACK` executes | Safe decline UX (no fraud leakage); explicit SQL abort. |
| **📒 Ledger** (`/ui/history`) | Click row to expand; filter by account | Displays monthly-partitioned ledger rows | Deferred constraint trigger (`check_ledger_balance`); partition pruning. |
| **🚨 Alerts** (`/ui/alerts`) | Click *Review*, pick decision, submit notes | Joins SQL alert with Mongo evidence document; updates ticket state | Polyglot persistence; async decoupling via Transactional Outbox. |
| **🔒 Audit Chain** (`/ui/audit`) | Click *Verify Chain*, then click *Corrupt a Row* | Traverses SHA-256 chain from `audit_id=1`; detects bit-flip modification | Merkle-style cryptographic chaining; tamper detection. |
| **⚡ Benchmarks** (`/ui/benchmarks`) | View Chart.js chart; inspect EXPLAIN ANALYZE cards | Displays empirical pgbench results & index timing | Index optimization (17.75× speedup); Redis ~0.4ms caching vs SQL ~3.1ms. |

---

## 💡 4. Top 5 Questions Evaluators Will Ask & Model Answers

### Q1: "Why did you implement a double-entry ledger instead of updating the account balance column directly?"
> **Answer:** *"In banking, updating a balance directly (`UPDATE account SET balance = balance - 100`) destroys audit traceability and makes reconciliation impossible if a crash occurs. Double-entry bookkeeping guarantees that every debit has an equal and opposite credit. It preserves an immutable journal of every single movement of funds, enforced by our deferred constraint trigger."*

### Q2: "How does the system prevent deadlocks when two users transfer to each other simultaneously?"
> **Answer:** *"We enforce a strict ascending primary key lock ordering policy in `ledger_service.py`:
> ```python
> first_id = min(source_account_id, destination_account_id)
> second_id = max(source_account_id, destination_account_id)
> ```
> Both concurrent transactions are forced to acquire locks in the exact same sequence (`min` then `max`). This breaks Coffman's circular wait condition and mathematically prevents deadlocks."*

### Q3: "Why did you choose Isolation Forest over supervised models like Logistic Regression or Neural Networks?"
> **Answer:** *"Supervised models require large amounts of labeled fraud data, which is heavily imbalanced in banking (< 0.1% of transactions). Isolation Forest is an unsupervised anomaly detection algorithm that isolates anomalies using random partitioning trees. Because anomalous transactions have unusual feature values, they require significantly fewer tree splits to isolate, making it both fast and effective without labeled training sets."*

### Q4: "Why use both Redis and PostgreSQL for velocity counting?"
> **Answer:** *"Calculating real-time velocity in SQL requires running `COUNT(*) WHERE initiated_at >= NOW() - INTERVAL '1 hour'`, which scans disk and locks index pages under high concurrency. Redis handles sliding-window rate limiting in-memory using atomic `INCR` and `EXPIRE` commands in ~0.4 milliseconds, protecting the primary database from read exhaustion."*

### Q5: "What happens if MongoDB or Redis crashes during a transaction?"
> **Answer:** *"The core transaction will still succeed! PostgreSQL is the single source of truth. We implemented graceful fallbacks: if Redis is unavailable, the application falls back to an in-memory dictionary. If MongoDB is offline, evidence is safely preserved in the PostgreSQL `OUTBOX` table until the daemon can reconnect and replay it."*
