# Reading Execution Plans

How to capture a plan safely, read it, and turn what you see into a fix. PostgreSQL first, then MySQL.

## Contents

1. Capturing a plan safely (PostgreSQL)
2. Anatomy of a plan line
3. Plan arithmetic: inclusive times, loops, parallel workers
4. Node reference
5. Buffers: how much data the query touched
6. Symptom-to-fix table
7. When estimates are wrong
8. Plan caching: "fast in psql, slow in the app"
9. Diagnostic-only planner switches
10. Worked example
11. MySQL plans
12. Finding the queries worth reviewing

---

## 1. Capturing a plan safely (PostgreSQL)

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS) SELECT ...;
```

| Option | What it adds | Notes |
|---|---|---|
| `ANALYZE` | Executes the query and reports actual rows, times, and loops | Side effects happen. Run writes only on a local or restored copy, inside `BEGIN; ... ROLLBACK;`. See the production rule below for what the rollback does not undo. |
| `BUFFERS` | Pages hit in cache, read, dirtied, and written, plus temp I/O | Included automatically with `ANALYZE` from PostgreSQL 18. Listing it is harmless and needed on older versions. |
| `SETTINGS` | Planner-relevant settings that differ from defaults (PG 12+) | Reveals a leftover `enable_*` override or an unusual `work_mem`. |
| `WAL` | WAL records and bytes generated (PG 13+, needs `ANALYZE`) | Useful for bulk writes. |
| `VERBOSE` | Output column lists, schema-qualified names, per-worker detail | Noisy. Use it when you need to see which columns flow up. |
| `GENERIC_PLAN` | Plans a statement containing `$1`-style placeholders without values (PG 16+) | Cannot be combined with `ANALYZE`. Shows what a cached generic plan would look like. |
| `SERIALIZE` | Time and buffers to convert output rows for the client (PG 17+, needs `ANALYZE`) | Normal `EXPLAIN ANALYZE` skips this work, so wide or out-of-line columns can look cheaper than they are. |
| `MEMORY` | Planner memory use (PG 17+) | Rarely needed. |
| `TIMING OFF` | Keeps row counts but drops per-node timing | Lowers overhead on machines with slow clocks. |
| `FORMAT JSON` | Machine-readable output | For plan visualizers. Text format is easiest to read in review. |

Rules for capturing:

- Use the parameter values that hurt: the largest customer or account, the widest date range, the most common status.
- Run twice and keep the second run, unless cold-cache behavior is the actual question. Then say which run you report.
- Record `Planning Time` and `Execution Time`. `Execution Time` excludes network transfer and, unless `SERIALIZE` is used, output conversion.
- `EXPLAIN ANALYZE` adds timing overhead to every node, so absolute times run slightly high. Compare runs captured the same way.
- **Production.** Plain `EXPLAIN` and `EXPLAIN (GENERIC_PLAN)` do not execute, so they are safe anywhere. Take `ANALYZE` measurements of reads on a replica or a restored copy, and of writes only on a local or restored copy. `BEGIN ... ROLLBACK` undoes the row changes but not the run itself:
  - every row the statement touches stays locked until the rollback, so live writers queue behind it;
  - WAL is still generated and replicas replay it, and the dead rows left behind are bloat for vacuum;
  - sequence values stay consumed;
  - triggers run, and anything they did outside the database (calls through `dblink` or a foreign table, a request to another service) is not undone;
  - deferred constraint triggers fire only at commit, so they never run and their cost is missing from the plan.

  If a production run is unavoidable and the owner approves it, put `SET LOCAL statement_timeout = '...'` and `SET LOCAL lock_timeout = '...'` at the start of the transaction so it gives up instead of blocking traffic.

## 2. Anatomy of a plan line

```
Index Scan using orders_customer_id_idx on orders o  (cost=0.43..8.45 rows=3 width=40) (actual time=0.020..0.031 rows=2 loops=1)
  Index Cond: (customer_id = 42)
  Filter: (status = 'paid'::text)
  Rows Removed by Filter: 1
  Buffers: shared hit=4
```

| Field | Meaning |
|---|---|
| `cost=0.43..8.45` | Planner's estimate in arbitrary units: startup cost .. total cost. Not milliseconds. Compare costs only between alternative plans for the same query. |
| `rows=3` (first parentheses) | Estimated rows this node returns, per execution. |
| `width=40` | Estimated average row width in bytes. |
| `actual time=0.020..0.031` | Milliseconds to the first row .. to the last row, **averaged per loop**. |
| `rows=2` (second parentheses) | Actual rows returned, averaged per loop. Shown with decimals from PostgreSQL 18. |
| `loops=1` | How many times this node ran. |
| `Index Cond` | Predicate used to navigate the index. This is the part the index makes cheap. |
| `Filter` | Predicate checked after fetching each row. Rows that fail are wasted work. |
| `Rows Removed by Filter` | Rows fetched and then discarded. Compare with `rows`. |

Read the tree from the innermost, most indented nodes outward. Each node's children are indented beneath it, and a node's time includes its children's time.

## 3. Plan arithmetic: inclusive times, loops, parallel workers

- **Inclusive time.** A parent's `actual time` includes its children. To find a node's own time, take its total (time × loops) and subtract each child's total (time × loops). Parallel plans are the exception; see below.
- **Loops.** Under a Nested Loop, the inner node runs once per outer row. `actual time=0.050..0.050 rows=1 loops=200000` means 200,000 × 0.05 ms = 10 s in total, and 200,000 rows. Always multiply before calling a node cheap.
- **Parallel plans.** Under `Gather` / `Gather Merge`, `loops` counts the leader plus the workers, and `rows` and `actual time` are per-process averages.
  - Multiply **rows** by `loops` to get total rows.
  - Do **not** multiply time. The processes run at the same time, so the per-loop time is already roughly the elapsed time, and time × loops is total worker time, not latency. A `Parallel Seq Scan` showing `actual time=..500 loops=3` under a `Gather` that took 510 ms spent about 500 ms of wall-clock time, not 1,500 ms. Subtracting 1,500 from 510 gives a negative self time, which is the sign you multiplied.
  - When finding the `Gather`'s own time, subtract the parallel child's per-loop time. Between nodes inside the parallel section, which share the same `loops`, compare per-loop times.
  - `VERBOSE` prints each worker's time and rows, which shows whether the work was evenly split.
  - Check `Workers Planned` against `Workers Launched`. Fewer launched means the server ran out of parallel workers, which is a capacity problem rather than a query problem.
- **LIMIT stops children early.** Under a `Limit`, a child's actual rows can be far below its estimate because the parent stopped asking for rows. That is expected and is not a misestimate. Look at `Rows Removed by Filter` and buffers instead.
- **`(never executed)`** marks a node that never ran, such as the inner side of a join whose outer side returned nothing. Zero time there is not evidence that it's fast.

## 4. Node reference

### Scans

| Node | What it does | Watch for |
|---|---|---|
| Seq Scan | Reads the whole table | Fine for small tables or low selectivity. A problem when `Rows Removed by Filter` is far larger than `rows`. |
| Index Scan | Walks the index, then fetches each matching row from the table | Cheap per row but random I/O. Expensive when it returns a large fraction of the table. |
| Index Only Scan | Answers from the index alone | `Heap Fetches` well above 0 means the visibility map is stale and it is falling back to table reads. Vacuum fixes it. |
| Bitmap Index Scan + Bitmap Heap Scan | Collects matching row locations, then reads the table in physical order | `Heap Blocks: lossy=N` means the bitmap exceeded `work_mem`, which shows up as `Rows Removed by Index Recheck`. BitmapAnd and BitmapOr combine several indexes. |
| CTE Scan | Reads a materialized CTE | A filter applied above it was not pushed into the CTE. See index-design.md, CTE section. |
| Function Scan | Reads a set-returning function | Estimated at a fixed default unless the function declares `ROWS`. |

### Joins

| Node | Best when | Watch for |
|---|---|---|
| Nested Loop | Outer side small, inner side has an index on the join key | Outer side estimated small but actually large, which causes an inner `loops` explosion. |
| Hash Join | Large, unsorted inputs joined by equality | `Batches` above 1 on the Hash node means it spilled to disk. Peak memory is shown. |
| Merge Join | Both inputs already sorted on the join key (often via indexes) | An explicit Sort feeding it may be the real cost. |
| Memoize (PG 14+) | Caches inner-side results for repeated keys in a Nested Loop | `Hits` versus `Misses`. Many evictions mean the cache is too small to help. |
| Hash/Merge Anti Join, Semi Join | `NOT EXISTS` / `EXISTS` planned as joins | Good sign. Through PostgreSQL 18, `NOT IN (subquery)` cannot use these and appears as a SubPlan. From 19 it can, but only when both sides are provably non-NULL. |

### Other nodes

| Node | Watch for |
|---|---|
| Sort | `Sort Method: quicksort Memory:` is in memory. `top-N heapsort` means a LIMIT is being used well. `external merge Disk:` is a spill. |
| Incremental Sort (PG 13+) | Input already sorted on a prefix (`Presorted Key`). Usually good. |
| HashAggregate | From PG 13 it can spill; look for `Batches` and `Disk Usage`. |
| GroupAggregate | Needs sorted input; check for an expensive Sort beneath it. |
| WindowAgg, Material | From PG 18, memory and disk usage are reported. Disk use means a spill. |
| SubPlan / InitPlan | A SubPlan with `loops` equal to the outer row count is a correlated subquery running per row. An InitPlan runs once. |
| Append / Merge Append | Partitions or `UNION ALL` branches. `Subplans Removed: N` means partitions were pruned at run time. Check that pruning happened. |
| Gather / Gather Merge | Parallel query. See section 3. |
| LockRows | `FOR UPDATE` / `FOR SHARE` row locking. |
| ModifyTable (Insert/Update/Delete/Merge) | Trigger times appear after the plan; see the next note. |

For data-modifying statements, `EXPLAIN ANALYZE` lists triggers after the plan, including foreign-key checks (`Trigger for constraint ...: time=... calls=...`). A large time on a `DELETE` usually means a referencing table has no index on its foreign-key column.

## 5. Buffers: how much data the query touched

```
Buffers: shared hit=1180 read=95811, temp read=5120 written=5120
I/O Timings: shared read=640.2
```

- `shared hit`: pages found in PostgreSQL's buffer cache.
- `shared read`: pages requested from the OS, which may come from the OS cache or from disk.
- `dirtied` / `written`: pages this query modified, or wrote out to make room.
- `temp read/written`: spill files from sorts, hashes, and materialization.
- `local`: temporary tables.
- `I/O Timings` appear only when `track_io_timing` is on.

Pages default to 8 kB, so `read=95811` is about 750 MB brought in from outside PostgreSQL's cache.

**Hits are accesses, not distinct pages.** Every buffer count is non-distinct: touching the same page twice counts twice. An inner index probed 1,000,000 times under a Nested Loop (or a Memoize that keeps missing) reports millions of `shared hit` on a few hundred pages. Convert only `read` and temp counts to bytes. Treat a large `hit` as a sign of repeated work and compare it with `loops`; the fix there is fewer loops, not a different access path.

Hit plus read, measured against rows returned, is still the most stable way to compare two plans for the same query, because it does not change with cache warmth the way time does. A parent's buffer counts include its children's. From PostgreSQL 13, planning buffers are reported separately under `Planning:`.

## 6. Symptom-to-fix table

| Symptom in the plan | Likely cause | What to try |
|---|---|---|
| Estimated rows off from actual by 10× or more (and not explained by a Limit) | Stale statistics, correlated columns, skewed values, or a predicate on an expression | Section 7 |
| Nested Loop whose inner side has very large `loops` | Outer side underestimated; missing index on the inner join key | Fix the estimate first, then index the join key |
| Seq Scan with `Rows Removed by Filter` far above `rows` | No usable index, or the predicate is non-sargable | Matching index, or rewrite the predicate (index-design.md) |
| Index Scan with large `Rows Removed by Filter` | The index covers only part of the predicate | Composite index whose columns match the filter |
| Index Scan walking an ORDER BY index under a LIMIT, discarding many rows | Planner hoped matches were evenly spread; they weren't | Composite index (filter columns, then sort columns). See section 10. |
| `Sort Method: external merge Disk:` | Sorting more data than `work_mem` | Index that delivers the order, fewer rows or columns before the sort, or `SET LOCAL work_mem` for that one transaction |
| Hash `Batches` above 1, or HashAggregate `Disk Usage` | Hash table larger than its memory budget | Same as above. Hash nodes may use `work_mem × hash_mem_multiplier`. |
| `Heap Blocks: lossy` with Index Recheck removals | Bitmap larger than `work_mem` | Raise `work_mem` locally, or use a more selective index |
| Index Only Scan with high `Heap Fetches` | Visibility map out of date | Vacuum the table; review autovacuum settings for it |
| SubPlan with `loops` equal to the outer row count | Correlated subquery, or `NOT IN (subquery)` | Rewrite as a join, `LATERAL`, or `NOT EXISTS` |
| Planning Time far above Execution Time | Many joins, many partitions, huge literal IN lists | Bind arrays instead of literal lists; prepared statements; check partition pruning |
| Large `JIT:` timing on a short query | JIT triggered by an inflated cost estimate | JIT is off by default from PostgreSQL 19, so check whether someone turned `jit` on. On 18 and earlier, fix the estimate, or raise `jit_above_cost` (or turn `jit` off) for that workload |
| `Trigger for constraint ...` dominating a DELETE | Unindexed foreign-key column on a referencing table | Index the referencing column |
| CTE Scan with a filter above it | Materialized CTE blocking push-down | `NOT MATERIALIZED`, or inline the CTE |
| `Workers Launched` below `Workers Planned` | Parallel worker pool exhausted | Capacity issue, not the query |

## 7. When estimates are wrong

The planner picks join order, join methods, and scans from row estimates. When an estimate is badly off, fix the estimate before rewriting the query, because the rewrite may only work until the data shifts.

1. **Refresh statistics.** `ANALYZE table_name;`. Bulk loads and large deletes can leave statistics stale until autovacuum catches up.
2. **Increase detail for skewed columns.** `ALTER TABLE orders ALTER COLUMN status SET STATISTICS 1000;` then `ANALYZE orders;`. The default target is 100, from `default_statistics_target`.
3. **Teach it about correlated columns.** The planner assumes predicates are independent, so `city = 'Paris' AND country = 'FR'` gets underestimated.
   ```sql
   CREATE STATISTICS addresses_city_country (dependencies, ndistinct, mcv)
     ON city, country FROM addresses;
   ANALYZE addresses;
   ```
   `mcv` needs PostgreSQL 12+; statistics on expressions need 14+.
4. **Give expressions statistics.** A predicate like `lower(email) = $1` has no column statistics. An expression index on `lower(email)` gets its own after `ANALYZE`.
5. **Set-returning functions.** Declare a realistic row count with `ALTER FUNCTION fn(args) ROWS 50;`.
6. **Check the data model.** Some estimates cannot be fixed: a filter on a JSON key, or a value computed per row. Consider promoting the value to a real column.

Inspect what the planner believes:

```sql
SELECT attname, null_frac, n_distinct, most_common_vals, most_common_freqs, correlation
FROM pg_stats
WHERE schemaname = 'public' AND tablename = 'orders';
```

## 8. Plan caching: "fast in psql, slow in the app"

Applications usually send parameterized, prepared statements; a psql session usually has literal values. In PostgreSQL, a prepared statement's first five executions use custom plans built for the actual values. After that, the server may switch to a single generic plan if its estimated cost is not much worse. A generic plan cannot use the specific value's statistics, and cannot use a partial index whose predicate depends on the parameter.

- Reproduce the app's shape: `PREPARE q(bigint) AS SELECT ... WHERE customer_id = $1;` then run `EXPLAIN (ANALYZE) EXECUTE q(42);` six or more times. Or use `EXPLAIN (GENERIC_PLAN)` on PG 16+.
- `plan_cache_mode` (PG 12+) can be set to `force_custom_plan` for a session or role when skew makes generic plans bad. Prefer fixing the query or the index, and document the setting if you use it.
- Connection poolers in transaction mode and driver settings also affect whether statements are prepared server-side. Check the driver's documentation rather than assuming.

## 9. Diagnostic-only planner switches

To see the plan the planner rejected, and what it would cost, disable a node type in your own session:

```sql
BEGIN;
SET LOCAL enable_seqscan = off;    -- also enable_nestloop, enable_hashjoin, enable_sort, ...
EXPLAIN (ANALYZE, BUFFERS) SELECT ...;
ROLLBACK;
```

If the alternative is much faster, the planner's estimates or cost settings are wrong for this case; go back to section 7. Don't ship these settings as the fix. They apply to every query in their scope and age badly as the data changes. PostgreSQL 18 marks disabled nodes in `EXPLAIN ANALYZE` output.

## 10. Worked example

Query: the 20 most recent orders for one customer.

```sql
SELECT id, total, created_at FROM orders
WHERE customer_id = 4711
ORDER BY created_at DESC
LIMIT 20;
```

Before (indexes exist on `customer_id` and on `created_at` separately):

```
Limit  (cost=0.43..820.43 rows=20 width=24) (actual time=812.380..812.391 rows=20 loops=1)
  Buffers: shared hit=1180 read=95811
  ->  Index Scan Backward using orders_created_at_idx on orders  (cost=0.43..410000.43 rows=10000 width=24) (actual time=812.378..812.388 rows=20 loops=1)
        Filter: (customer_id = 4711)
        Rows Removed by Filter: 1843210
        Buffers: shared hit=1180 read=95811
Planning Time: 0.210 ms
Execution Time: 812.420 ms
```

Reading it:

- The planner expected 10,000 matching rows spread evenly through time, so walking the `created_at` index newest-first should find 20 matches almost immediately. That is why the Limit's cost is tiny.
- In reality this customer's orders are old. The scan discarded 1.84 million rows and read about 750 MB (95,811 pages) to find 20.
- Actual rows (20) below the estimate (10,000) is **not** the signal here, since the Limit stopped the scan. The signals are `Rows Removed by Filter` and `Buffers`.

Fix: one composite index that serves both the filter and the order.

```sql
CREATE INDEX orders_customer_id_created_at_idx ON orders (customer_id, created_at DESC);
```

After:

```
Limit  (cost=0.56..80.12 rows=20 width=24) (actual time=0.031..0.052 rows=20 loops=1)
  Buffers: shared hit=24
  ->  Index Scan using orders_customer_id_created_at_idx on orders  (cost=0.56..39780.56 rows=10000 width=24) (actual time=0.030..0.049 rows=20 loops=1)
        Index Cond: (customer_id = 4711)
        Buffers: shared hit=24
Planning Time: 0.250 ms
Execution Time: 0.071 ms
```

The predicate moved from `Filter` into `Index Cond`, nothing is removed, and the buffers dropped from about 97,000 to 24. PostgreSQL 18 also prints `Index Searches: 1` under the scan. An ascending `(customer_id, created_at)` index would work as well, scanned backward; `DESC` matters only for mixed-direction sorts. The old single-column `customer_id` index is now redundant, because the new index's leading column serves the same lookups. Flag it for removal.

## 11. MySQL plans

### Traditional `EXPLAIN` columns

```sql
EXPLAIN FORMAT=TRADITIONAL SELECT ...;
SHOW WARNINGS;   -- immediately after EXPLAIN: shows the query as the optimizer rewrote it
```

From MySQL 9.5, `explain_format` defaults to `TREE`, so a bare `EXPLAIN` prints the tree shown in the next subsection. Ask for `FORMAT=TRADITIONAL` to get this column table. `SHOW WARNINGS` also reports when an index was skipped because of a type or collation conversion.

| Column | Meaning |
|---|---|
| `type` | Access method, roughly best to worst: `system`, `const`, `eq_ref`, `ref`, `fulltext`, `ref_or_null`, `index_merge`, `unique_subquery`, `index_subquery`, `range`, `index` (full index scan), `ALL` (full table scan) |
| `possible_keys` / `key` | Candidate indexes / the one chosen. `key` NULL with `type=ALL` on a large table is the classic finding. |
| `key_len` | Bytes of the index key used. Shows how many columns of a composite index are actually used. |
| `ref` | What the index is compared to: a constant or a column from an earlier table. |
| `rows` | Estimated rows examined for this table, per lookup. |
| `filtered` | Estimated percentage of those rows that survive the conditions. `rows × filtered / 100` is what flows to the next table. |
| `Extra` | `Using index` means covering (no table access). `Using index condition` means index condition pushdown. `Using where` means filtering after the read. `Using temporary` means an internal temp table (often GROUP BY or DISTINCT). `Using filesort` means a sort not served by an index. `Using join buffer (hash join)` means a hash join (8.0.18+). `Using index for skip scan` means a skip scan (8.0.13+). |

Tables are listed in join order. Each row is an inner loop of the one above it, so multiply the `rows` estimates down the list to gauge the work.

### Tree format and `EXPLAIN ANALYZE`

```sql
EXPLAIN FORMAT=TREE SELECT ...;          -- 8.0.16+, estimates only
EXPLAIN ANALYZE SELECT ...;              -- 8.0.18+, executes, TREE output
EXPLAIN ANALYZE FORMAT=JSON SELECT ...;  -- 8.3+, executes; needs explain_json_format_version = 2 (the default from 9.5)
```

From 8.3 up to 9.4 (which includes 8.4 LTS), run `SET explain_json_format_version = 2;` first, or the JSON form is rejected. Version 2 JSON follows the same structure as the tree and adds `actual_*` fields, which suits plan visualizers.

```
-> Nested loop inner join  (cost=1250.40 rows=980) (actual time=0.210..48.300 rows=1012 loops=1)
    -> Filter: (o.created_at >= TIMESTAMP'2025-01-01 00:00:00')  (cost=410.20 rows=980) (actual time=0.150..12.100 rows=1012 loops=1)
        -> Index range scan on o using idx_created_at  (cost=410.20 rows=980) (actual time=0.148..11.700 rows=1012 loops=1)
    -> Single-row index lookup on c using PRIMARY (id=o.customer_id)  (cost=0.25 rows=1) (actual time=0.030..0.033 rows=1 loops=1012)
```

The semantics match PostgreSQL's: `actual time` is first row..all rows in milliseconds, averaged per loop; `rows` is averaged per loop; multiply by `loops`. `EXPLAIN ANALYZE` executes the statement. It supports `SELECT`, multi-table `UPDATE` and `DELETE`, and `TABLE`. Run anything that writes only on a local or restored copy, inside a transaction you roll back; the PostgreSQL caveats in section 1 (locks held for the run, replication traffic, trigger side effects) apply here too.

### Fixing MySQL estimates

- `ANALYZE TABLE orders;` refreshes index statistics.
- `ANALYZE TABLE orders UPDATE HISTOGRAM ON status WITH 64 BUCKETS;` (8.0+) gives the optimizer value distributions for non-indexed columns used in filters.
- To see why the optimizer chose a plan:
  ```sql
  SET optimizer_trace = 'enabled=on';
  SELECT ...;
  SELECT TRACE FROM information_schema.OPTIMIZER_TRACE;
  SET optimizer_trace = 'enabled=off';
  ```
- Index hints (`FORCE INDEX`, `USE INDEX`) and optimizer hints are diagnostic first. As permanent fixes they break silently when indexes are renamed or the data changes.

## 12. Finding the queries worth reviewing

Rank by total time (calls × mean), not by the slowest single run.

PostgreSQL, with the `pg_stat_statements` extension enabled (column names as of PG 13+):

```sql
SELECT calls,
       round(total_exec_time) AS total_ms,
       round(mean_exec_time::numeric, 2) AS mean_ms,
       rows,
       shared_blks_hit, shared_blks_read,
       left(query, 120) AS query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

- `auto_explain` logs plans of slow statements automatically. Key settings: `auto_explain.log_min_duration`, `auto_explain.log_analyze` (adds overhead to every statement), `auto_explain.log_buffers`, and `auto_explain.sample_rate`. Load it per session with `LOAD 'auto_explain';` or via `session_preload_libraries` / `shared_preload_libraries`.
- `log_min_duration_statement` logs statements slower than a threshold.

MySQL:

```sql
SELECT * FROM sys.statement_analysis LIMIT 20;   -- digests sorted by total latency
```

- Compare `rows_examined` with `rows_sent`. A large ratio means the query reads far more than it returns.
- The slow query log (`slow_query_log`, `long_query_time`, optionally `log_queries_not_using_indexes`) captures individual slow statements.

Statistics are per server: a query that runs only on a read replica does not appear in the primary's `pg_stat_statements` or `sys` views. Check each node that serves traffic.
