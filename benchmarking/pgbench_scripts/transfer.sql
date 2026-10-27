-- pgbench script modeling atomic money transfer transaction
\set src random(1, 10)
\set dst random(1, 10)
\set amount random(10, 500)

BEGIN;

-- Lock accounts in fixed ascending account_id order
SELECT account_id, balance FROM ACCOUNT WHERE account_id IN (:src, :dst) ORDER BY account_id ASC FOR UPDATE;

-- Insert debit leg
INSERT INTO TRANSACTION (type, status, device_id, initiated_at) VALUES ('TRANSFER', 'COMPLETED', 1, NOW());

-- Update balances
UPDATE ACCOUNT SET balance = balance - :amount WHERE account_id = :src;
UPDATE ACCOUNT SET balance = balance + :amount WHERE account_id = :dst;

COMMIT;
