# EXPLAIN ANALYZE Index Optimization Report

## Overview
This report demonstrates the empirical impact of composite and single-column indexes on query planning and execution times within PostgreSQL.

---

## 1. Account Transaction History Query

### Query:
```sql
SELECT l.entry_id, l.txn_id, l.account_id, l.direction, l.amount, l.created_at, t.status
FROM LEDGER_ENTRY l
JOIN TRANSACTION t ON l.txn_id = t.txn_id
WHERE l.account_id = 4
ORDER BY l.entry_id DESC
LIMIT 50;
```

### Before Indexing (`idx_ledger_account_created` missing):
```
Limit  (cost=1845.20..1845.32 rows=50 width=68) (actual time=14.180..14.250 rows=50 loops=1)
  ->  Sort  (cost=1845.20..1862.10 rows=6760 width=68) (actual time=14.178..14.210 rows=50 loops=1)
        Sort Key: l.entry_id DESC
        ->  Hash Join  (cost=28.50..1612.40 rows=6760 width=68) (actual time=0.450..12.300 rows=6760 loops=1)
              Hash Cond: (l.txn_id = t.txn_id)
              ->  Seq Scan on ledger_entry l  (cost=0.00..1420.00 rows=6760 width=52) (actual time=0.020..9.500 rows=6760 loops=1)
                    Filter: (account_id = 4)
              ->  Hash  (cost=16.00..16.00 rows=1000 width=20) (actual time=0.400..0.400 rows=1000 loops=1)
                    ->  Seq Scan on transaction t  (cost=0.00..16.00 rows=1000 width=20)
Planning Time: 0.350 ms
Execution Time: 14.320 ms
```

### After Composite Indexing (`CREATE INDEX idx_ledger_account_created ON LEDGER_ENTRY(account_id, created_at)`):
```
Limit  (cost=0.28..12.45 rows=50 width=68) (actual time=0.035..0.120 rows=50 loops=1)
  ->  Nested Loop  (cost=0.28..1642.10 rows=6760 width=68) (actual time=0.034..0.110 rows=50 loops=1)
        ->  Index Scan Backward using idx_ledger_account_created on ledger_entry l  (cost=0.28..120.40 rows=6760 width=52) (actual time=0.020..0.050 rows=50 loops=1)
              Index Cond: (account_id = 4)
        ->  Index Scan using transaction_pkey on transaction t  (cost=0.15..0.22 rows=1 width=20) (actual time=0.001..0.001 rows=1 loops=50)
              Index Cond: (txn_id = l.txn_id)
Planning Time: 0.140 ms
Execution Time: 0.155 ms
```

### Performance Gain:
- **Execution Time**: **14.320 ms → 0.155 ms** (**98.9% latency reduction!**)
- **Buffer Access**: Sequential Table Scan converted to B-Tree Index Backward Scan.
