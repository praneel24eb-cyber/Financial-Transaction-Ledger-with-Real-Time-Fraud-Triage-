# Financial Transaction Ledger with Real-Time Fraud Triage
## Live Demonstration Script & Comprehensive Viva Voce Guide (m12-4)

This document provides a walkthrough guide for project demonstrations alongside a complete collection of technical viva voce questions and answers.

---

# Part 1: Step-by-Step Live Demonstration Script

### Step 1: System Boot & Verification
1. Start the stack:
   ```bash
   # Option A: Local execution
   python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload

   # Option B: Docker Compose
   docker-compose up -d
   ```
2. Open the web browser to the dashboard: `http://localhost:8000`
3. Point out the dashboard cards:
   - Live transaction ledger feed.
   - Fraud alert review counter.
   - Cryptographic audit trail status.
   - System benchmark latency graph.

---

### Step 2: Normal Legitimate Transfer (Risk Score < 50)
1. Navigate to **New Transfer** (`/transfer`).
2. Input:
   - Source Account: `1`
   - Destination Account: `2`
   - Amount: `₹500.00`
   - Device: `1` (Recognized Customer Device)
3. Click **Submit Transfer**.
4. **Demonstrate Outcome:**
   - Transfer succeeds immediately (HTTP 201).
   - Transaction status: `COMMITTED`.
   - Risk score evaluated low (~15–30/100) by Isolation Forest.
   - Open PostgreSQL or Dashboard History: Show that exactly two balanced rows were created in `LEDGER_ENTRY` (`DEBIT ₹500` for Account 1, `CREDIT ₹500` for Account 2).
   - Verify `Account.balance` updated atomically.

---

### Step 3: Overdraft / Insufficient Balance Validation
1. Input:
   - Source Account: `1`
   - Destination Account: `2`
   - Amount: `₹999,999,999.00` (Exceeds available balance)
2. Click **Submit Transfer**.
3. **Demonstrate Outcome:**
   - Transfer rejected with HTTP 402: *"Insufficient funds: available balance is ₹..., required ₹999999999.00"*.
   - Verify the database `CHECK (balance >= 0)` constraint and application checks prevent balance corruption. Zero ledger rows created.

---

### Step 4: High-Risk Anomaly & Automated Freeze (Risk Score > 80)
1. Input:
   - Source Account: `1`
   - Destination Account: `2`
   - Amount: `₹85,000.00` (Extreme amount spike)
   - Rapidly submit 5+ transfers or trigger night-time anomaly with foreign merchant.
2. Click **Submit Transfer**.
3. **Demonstrate Outcome:**
   - Transfer blocked with HTTP 200/403: *"Transfer blocked by real-time fraud engine (Risk Score: 92/100). Source account has been frozen."*
   - Transaction status recorded as `ROLLED_BACK`.
   - Zero funds leave the source account.
   - Look up Account 1 status: transitioned from `ACTIVE` to `FROZEN`.
   - High-severity alert (`FRAUD_ALERT`) generated in the analyst queue.

---

### Step 5: Fraud Analyst Review & Triage Workflow
1. Navigate to **Fraud Alerts** (`/alerts`).
2. View the open alert generated in Step 4.
3. Click **Review Alert**.
4. Select decision:
   - `CONFIRM_FRAUD`: Confirms attack, keeps account locked, notifies customer.
   - `FALSE_POSITIVE`: Unfreezes account, marks alert reviewed.
   - `ESCALATE`: Routes to Tier-2 investigations.
5. Submit review and observe instant status update in both PostgreSQL and the UI.

---

### Step 6: Cryptographic Hash Chaining & Tamper Detection
1. Navigate to **Audit Trail** (`/audit`).
2. Click **Verify Hash Chain Integrity**.
3. Show that the entire chain is valid (`SHA-256 chain is 100% intact`).
4. **Deliberate Tamper Demonstration:**
   - Execute script or SQL:
     ```python
     python -c "from tests.test_audit import test_audit_hash_chain_tamper_detection; print('Running tamper test...')"
     ```
   - Show how altering even a single byte in an old transaction row causes `row_hash != calculated_hash`, immediately detecting the exact compromised row ID.

---

### Step 7: Concurrency & Benchmarking Dashboard
1. Navigate to **Benchmarks** (`/benchmarks`).
2. Present:
   - Comparison charts across **Read Committed**, **Repeatable Read**, and **Serializable**.
   - Redis velocity lookup latency ($< 0.5\text{ ms}$) versus SQL aggregation query ($14.2\text{ ms}$).
   - Run live concurrency demo:
     ```bash
     python benchmarking/demo_concurrency.py
     ```
   - Confirm 20 concurrent threads transfer funds across accounts with zero lost updates and zero deadlocks.

---

# Part 2: Comprehensive Viva Voce Questions & Answers

### Q1: Why did you implement a double-entry ledger instead of updating account balances directly?
**Answer:**
Updating balances in-place (`UPDATE account SET balance = balance - amount`) destroys historical auditability, makes it impossible to reconcile financial statements, and is vulnerable to lost update anomalies under concurrency. In a double-entry ledger:
- Every movement is represented by immutable paired entries: a `DEBIT` and a `CREDIT`.
- Money is conserved: $\sum \text{Debits} = \sum \text{Credits}$.
- The cached `Account.balance` is merely a fast read cache; the mathematical ground truth is always the sum of immutable ledger entries.

---

### Q2: How do you prevent deadlocks during concurrent transfers between identical accounts?
**Answer:**
Deadlocks occur when transactions acquire locks in opposing order (Transaction A locks Account 1 then requests Account 2; Transaction B locks Account 2 then requests Account 1). This creates a circular wait.
We eliminate circular wait by enforcing **Ascending Lock Ordering**:
```python
first_id, second_id = sorted([source_account_id, destination_account_id])
SELECT ... FROM ACCOUNT WHERE account_id IN (first_id, second_id) ORDER BY account_id ASC FOR UPDATE;
```
Because all concurrent processes request locks in identical numerical sequence, circular dependencies are mathematically impossible. Furthermore, an exponential backoff retry loop catches any transient serialization conflicts.

---

### Q3: What is the "Dual-Write Problem", and how does the Transactional Outbox Pattern solve it?
**Answer:**
When an application writes to both a SQL database and a NoSQL store (e.g., Redis or MongoDB), it cannot do so atomically without complex, slow Two-Phase Commit (2PC) protocols. If the SQL commit succeeds but the Redis write fails, the cache and database drift out of sync. If SQL fails after Redis writes, the cache holds phantom data.
**The Outbox Solution:**
The application writes the transaction and an event record to an `OUTBOX` table inside the *same single relational transaction*. A background worker asynchronously reads pending outbox events and pushes them to Redis and MongoDB. If the NoSQL write fails, the worker retries with exponential backoff until it succeeds, achieving guaranteed **eventual consistency** without distributed transactions.

---

### Q4: How does the cryptographic hash chain in AUDIT_LOG detect tampering?
**Answer:**
Each row in `AUDIT_LOG` stores:
$$\text{row\_hash}_n = \text{SHA-256}(\text{prev\_hash}_{n-1} \parallel \text{table\_name} \parallel \text{operation} \parallel \text{old\_data} \parallel \text{new\_data})$$
If an attacker or rogue administrator modifies the data of row $k$, the hash of row $k$ will change. Because row $k+1$ includes the original hash of row $k$ as its `prev_hash`, the entire cryptographic chain breaks from row $k$ forward. Verification traverses the log recalculating hashes; the first mismatch identifies the exact tampered row.

---

### Q5: Why did you choose Isolation Forest over supervised models (like XGBoost or Logistic Regression) for fraud detection?
**Answer:**
1. **Label Scarcity & Imbalance:** In real-world banking, fraudulent transactions represent less than 0.1% of volume, and fraud labels are delayed by 30–90 days (chargebacks).
2. **Novelty Detection:** Supervised models only recognize previously seen fraud patterns. Isolation Forest is an unsupervised anomaly detector that isolates anomalies by randomly partitioning feature space; genuine fraud attempts require far fewer splits to isolate, making it highly effective at detecting novel, zero-day fraud techniques.
3. **Execution Latency:** Isolation Forest inference executes in $< 2\text{ ms}$, meeting real-time payment SLAs.

---

### Q6: What are the trade-offs between Read Committed, Repeatable Read, and Serializable isolation levels?
**Answer:**
- **Read Committed (Default):** Guarantees no dirty reads. Offers highest throughput (~1,420 TPS in our benchmarks), but permits non-repeatable reads and phantom reads. Suitable for day-to-day transfers when row-level `FOR UPDATE` locks are used.
- **Repeatable Read:** Prevents dirty and non-repeatable reads. Uses MVCC snapshots. May fail transactions with serialization errors if concurrent rows conflict.
- **Serializable:** Guarantees strict equivalent serial execution, preventing all concurrency anomalies (including write skew). Lowest throughput (~890 TPS) due to aborts on read/write dependency cycles. Recommended for end-of-day reconciliation or high-risk ledger settlements.

---

### Q7: Why use Redis for velocity and MongoDB for fraud alerts instead of keeping everything in PostgreSQL?
**Answer:**
Polyglot persistence optimizes each workload:
1. **Redis (In-Memory Key-Value):** Fraud velocity requires evaluating sliding windows (e.g. transfers in the last 10 minutes) on every incoming transfer. In PostgreSQL, this requires scanning indexed tables ($O(\log N)$ or window aggregation $\approx 14\text{ ms}$). In Redis, an atomic `INCR` with a TTL executes in $0.4\text{ ms}$ in memory, removing heavy analytical load from the core financial database.
2. **MongoDB (Document Store):** Alert evidence consists of polymorphic feature vectors, model explainability trees, third-party risk scores, and analyst investigation notes. Storing this semi-structured, schema-less JSON in MongoDB allows dynamic querying and indexing without frequent schema migrations on the core transactional database.
3. **PostgreSQL (ACID Relational Core):** Remains the inviolable source of truth for all balances, ledger movements, and audit records.

---

### Q8: What happens if the Machine Learning service crashes or times out during a transfer?
**Answer:**
The system implements a **Fail-Safe Fallback Policy**:
If `IsolationForest` throws an exception, is missing its serialized artifact, or exceeds SLA timeout thresholds, the transaction does not fail. Instead, execution routes to a deterministic rule-based evaluator:
- If amount $> \text{₹}50,000$ or velocity $> 5 \rightarrow$ Flag as `REVIEW` (Decision Score 65/100).
- Otherwise $\rightarrow$ `APPROVE` with model version logged as `rule-based-fallback`.
This ensures operational resilience without compromising financial safety.
