# PostgreSQL Range Partitioning Performance Report

## Overview
`LEDGER_ENTRY` is monthly range-partitioned on `created_at` (`PARTITION BY RANGE (created_at)`). This report demonstrates how PostgreSQL's query planner performs **Partition Pruning** to isolate active month partitions and omit historical partitions.

---

## 1. Partition Pruning Test

### Query:
```sql
EXPLAIN (ANALYZE, COSTS OFF)
SELECT * FROM LEDGER_ENTRY
WHERE created_at >= '2026-09-01 00:00:00+00' 
  AND created_at < '2026-10-01 00:00:00+00';
```

### Execution Plan:
```
Append (actual time=0.015..0.045 rows=120 loops=1)
  Subplans Removed: 2
  ->  Seq Scan on ledger_entry_y2026m09 (actual time=0.014..0.038 rows=120 loops=1)
        Filter: ((created_at >= '2026-09-01 00:00:00+00'::timestamp with time zone) AND (created_at < '2026-10-01 00:00:00+00'::timestamp with time zone))
Planning Time: 0.180 ms
Execution Time: 0.065 ms
```

### Observations:
- **Subplans Removed: 2** (The query engine automatically pruned `ledger_entry_y2026m10` and `ledger_entry_default`).
- **Scan Cost**: Scans only the target month partition table `ledger_entry_y2026m09`.
- **Scalability Impact**: Prevents scan times from degrading as historical ledger volume scales over months and years.
