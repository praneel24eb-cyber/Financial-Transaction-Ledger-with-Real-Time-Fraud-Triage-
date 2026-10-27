-- pgbench script modeling read transaction history
\set acc random(1, 10)

SELECT l.entry_id, l.txn_id, l.account_id, l.direction, l.amount, l.created_at, t.status
FROM LEDGER_ENTRY l
JOIN TRANSACTION t ON l.txn_id = t.txn_id
WHERE l.account_id = :acc
ORDER BY l.entry_id DESC
LIMIT 20;
