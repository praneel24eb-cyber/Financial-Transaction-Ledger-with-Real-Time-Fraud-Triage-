-- PostgreSQL 15+ Schema DDL for Financial Transaction Ledger with Real-Time Fraud Triage
-- Compliant with ER Diagram and System Requirements Documentation

-- Required extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. CUSTOMER
CREATE TABLE IF NOT EXISTS CUSTOMER (
    customer_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    kyc_status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (kyc_status IN ('PENDING', 'VERIFIED', 'REJECTED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. DEVICE
CREATE TABLE IF NOT EXISTS DEVICE (
    device_id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES CUSTOMER(customer_id) ON DELETE CASCADE,
    fingerprint VARCHAR(128) NOT NULL UNIQUE,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. MERCHANT
CREATE TABLE IF NOT EXISTS MERCHANT (
    merchant_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50),
    country VARCHAR(50) DEFAULT 'IN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. ACCOUNT
CREATE TABLE IF NOT EXISTS ACCOUNT (
    account_id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES CUSTOMER(customer_id) ON DELETE RESTRICT,
    account_type VARCHAR(20) NOT NULL CHECK (account_type IN ('SAVINGS', 'CURRENT', 'WALLET')),
    balance DECIMAL(14,2) NOT NULL DEFAULT 0.00 CHECK (balance >= 0),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'FROZEN', 'CLOSED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. TRANSACTION
CREATE TABLE IF NOT EXISTS TRANSACTION (
    txn_id BIGSERIAL PRIMARY KEY,
    device_id BIGINT REFERENCES DEVICE(device_id) ON DELETE SET NULL,
    merchant_id BIGINT REFERENCES MERCHANT(merchant_id) ON DELETE SET NULL,
    txn_type VARCHAR(20) NOT NULL DEFAULT 'TRANSFER' CHECK (txn_type IN ('TRANSFER', 'PAYMENT', 'WITHDRAWAL', 'DEPOSIT')),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'COMMITTED', 'ROLLED_BACK')),
    initiated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 6. LEDGER_ENTRY (Partitioned monthly by created_at)
CREATE TABLE IF NOT EXISTS LEDGER_ENTRY (
    entry_id BIGSERIAL,
    account_id BIGINT NOT NULL REFERENCES ACCOUNT(account_id) ON DELETE RESTRICT,
    txn_id BIGINT NOT NULL REFERENCES TRANSACTION(txn_id) ON DELETE CASCADE,
    direction VARCHAR(6) NOT NULL CHECK (direction IN ('DEBIT', 'CREDIT')),
    amount DECIMAL(14,2) NOT NULL CHECK (amount > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (entry_id, created_at)
) PARTITION BY RANGE (created_at);

-- Initial monthly partitions for LEDGER_ENTRY
CREATE TABLE IF NOT EXISTS ledger_entry_y2026m09 PARTITION OF LEDGER_ENTRY
    FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS ledger_entry_y2026m10 PARTITION OF LEDGER_ENTRY
    FOR VALUES FROM ('2026-10-01 00:00:00+00') TO ('2026-11-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS ledger_entry_y2026m11 PARTITION OF LEDGER_ENTRY
    FOR VALUES FROM ('2026-11-01 00:00:00+00') TO ('2026-12-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS ledger_entry_default PARTITION OF LEDGER_ENTRY DEFAULT;

-- 7. FRAUD_RESULT
CREATE TABLE IF NOT EXISTS FRAUD_RESULT (
    result_id BIGSERIAL PRIMARY KEY,
    txn_id BIGINT NOT NULL UNIQUE REFERENCES TRANSACTION(txn_id) ON DELETE CASCADE,
    risk_score INT NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    model_version VARCHAR(20) NOT NULL,
    decision VARCHAR(20) NOT NULL CHECK (decision IN ('APPROVE', 'REVIEW', 'ROLLBACK')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 8. FRAUD_ALERT
CREATE TABLE IF NOT EXISTS FRAUD_ALERT (
    alert_id BIGSERIAL PRIMARY KEY,
    result_id BIGINT NOT NULL UNIQUE REFERENCES FRAUD_RESULT(result_id) ON DELETE CASCADE,
    severity VARCHAR(10) CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH')),
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'REVIEWED', 'DISMISSED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 9. ANALYST
CREATE TABLE IF NOT EXISTS ANALYST (
    analyst_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    role VARCHAR(30)
);

-- 10. ANALYST_REVIEW
CREATE TABLE IF NOT EXISTS ANALYST_REVIEW (
    review_id BIGSERIAL PRIMARY KEY,
    alert_id BIGINT NOT NULL REFERENCES FRAUD_ALERT(alert_id) ON DELETE CASCADE,
    analyst_id BIGINT NOT NULL REFERENCES ANALYST(analyst_id) ON DELETE RESTRICT,
    decision VARCHAR(20) NOT NULL CHECK (decision IN ('CONFIRM_FRAUD', 'FALSE_POSITIVE', 'ESCALATE')),
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 11. OUTBOX (Transactional Outbox)
CREATE TABLE IF NOT EXISTS OUTBOX (
    outbox_id BIGSERIAL PRIMARY KEY,
    txn_id BIGINT NOT NULL REFERENCES TRANSACTION(txn_id) ON DELETE CASCADE,
    event_type VARCHAR(30) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'SENT', 'FAILED')),
    attempts SMALLINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Backward-compatibility view for OUTBOX_EVENT
CREATE OR REPLACE VIEW OUTBOX_EVENT AS
    SELECT outbox_id AS event_id, txn_id, event_type, payload, status, attempts, created_at
    FROM OUTBOX;

-- 12. AUDIT_LOG (Append-only tamper-evident hash chain)
CREATE TABLE IF NOT EXISTS AUDIT_LOG (
    audit_id BIGSERIAL PRIMARY KEY,
    table_name VARCHAR(50) NOT NULL,
    operation VARCHAR(10) NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    old_data JSONB,
    new_data JSONB,
    prev_hash CHAR(64),
    row_hash CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- INDEXES
CREATE INDEX IF NOT EXISTS idx_account_customer_id ON ACCOUNT(customer_id);
CREATE INDEX IF NOT EXISTS idx_device_customer_id ON DEVICE(customer_id);
CREATE INDEX IF NOT EXISTS idx_transaction_initiated ON TRANSACTION(initiated_at);
CREATE INDEX IF NOT EXISTS idx_ledger_account_created ON LEDGER_ENTRY(account_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ledger_txn_id ON LEDGER_ENTRY(txn_id);
CREATE INDEX IF NOT EXISTS idx_fraud_alert_result_id ON FRAUD_ALERT(result_id);
CREATE INDEX IF NOT EXISTS idx_fraud_alert_status ON FRAUD_ALERT(status);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON OUTBOX(status, attempts);

-- ===================================================================
-- MATERIALIZED VIEWS (Performance Optimization & Reporting - m8-2)
-- ===================================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_account_balances AS
SELECT 
    a.account_id,
    a.customer_id,
    a.account_type,
    a.status,
    a.balance AS cached_balance,
    COALESCE(SUM(CASE WHEN l.direction = 'CREDIT' THEN l.amount ELSE -l.amount END), 0.00) AS calculated_ledger_balance,
    COUNT(l.entry_id) AS total_ledger_entries,
    MAX(l.created_at) AS last_activity_at
FROM ACCOUNT a
LEFT JOIN LEDGER_ENTRY l ON a.account_id = l.account_id
GROUP BY a.account_id, a.customer_id, a.account_type, a.status, a.balance;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_account_balances_id ON mv_account_balances(account_id);

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_daily_transaction_summary AS
SELECT 
    DATE(t.initiated_at) AS summary_date,
    t.txn_type,
    t.status,
    COUNT(t.txn_id) AS total_transactions,
    COALESCE(SUM(l.amount), 0.00) AS total_volume,
    COALESCE(AVG(l.amount), 0.00) AS avg_amount,
    COUNT(fa.alert_id) AS total_alerts
FROM TRANSACTION t
LEFT JOIN LEDGER_ENTRY l ON t.txn_id = l.txn_id AND l.direction = 'DEBIT'
LEFT JOIN FRAUD_RESULT fr ON t.txn_id = fr.txn_id
LEFT JOIN FRAUD_ALERT fa ON fr.result_id = fa.result_id
GROUP BY DATE(t.initiated_at), t.txn_type, t.status;

CREATE INDEX IF NOT EXISTS idx_mv_daily_summary_date ON mv_daily_transaction_summary(summary_date);

-- ===================================================================
-- SECURITY / PERMISSIONS LAYER
-- Restricted application role with INSERT-ONLY privileges on AUDIT_LOG
-- ===================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'ledger_app_role') THEN
        CREATE ROLE ledger_app_role WITH LOGIN PASSWORD 'ledger_app_password';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE ledger_db TO ledger_app_role;
GRANT USAGE ON SCHEMA public TO ledger_app_role;

-- Operational table permissions
GRANT SELECT, INSERT, UPDATE ON ACCOUNT, TRANSACTION, LEDGER_ENTRY, FRAUD_RESULT, FRAUD_ALERT, ANALYST, ANALYST_REVIEW, CUSTOMER, DEVICE, MERCHANT, OUTBOX TO ledger_app_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ledger_app_role;
GRANT SELECT ON mv_account_balances, mv_daily_transaction_summary TO ledger_app_role;

-- Security Restriction: AUDIT_LOG is strictly INSERT and SELECT only (NO UPDATE / DELETE)
GRANT SELECT, INSERT ON AUDIT_LOG TO ledger_app_role;
REVOKE UPDATE, DELETE ON AUDIT_LOG FROM ledger_app_role;
