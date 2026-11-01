-- pgbench script modeling atomic money transfer transaction
\set src random(1, 10)
\set dst random(1, 10)
\set amount random(10, 500)

BEGIN;

-- Lock accounts in fixed ascending account_id order (FR-10)
SELECT account_id, balance FROM ACCOUNT WHERE account_id IN (:src, :dst) ORDER BY account_id ASC FOR UPDATE;

-- Insert transaction header
INSERT INTO TRANSACTION (txn_type, status, device_id, initiated_at) 
VALUES ('TRANSFER', 'COMMITTED', 1, NOW());

-- Insert balanced double-entry legs for the transaction
INSERT INTO LEDGER_ENTRY (txn_id, account_id, direction, amount, created_at)
VALUES (lastval(), :src, 'DEBIT', :amount, NOW());

INSERT INTO LEDGER_ENTRY (txn_id, account_id, direction, amount, created_at)
VALUES (lastval(), :dst, 'CREDIT', :amount, NOW());

-- Update balances
UPDATE ACCOUNT SET balance = balance - :amount WHERE account_id = :src;
UPDATE ACCOUNT SET balance = balance + :amount WHERE account_id = :dst;

COMMIT;

