# Index Design and Query Rewrites

Use this when proposing an index or rewriting a slow query. Every recommendation should end with a before-and-after plan; this file explains what to try, and `explain-guide.md` explains how to confirm it worked. Rolling the DDL out safely (online builds, locks, ordering) belongs to `data-api:db-migration-safety`.

## Contents

1. How a B-tree answers a query
2. Composite column order
3. Leftmost prefix and skip scan
4. Covering indexes
5. Partial indexes (PostgreSQL)
6. Expression indexes
7. When an index won't help
8. Sargable rewrites
9. Text search: prefix, infix, case-insensitive
10. Keyset pagination
11. Large IN lists and ID sets
12. Counting large tables
13. CTEs and subqueries
14. What indexes cost, and finding the useless ones

---

## 1. How a B-tree answers a query

A B-tree stores keys in sorted order. A query can use it to:

1. **Seek** to the first matching key using equality on leading columns, plus at most one range on the next column.
2. **Scan forward or backward** from there, in key order, which can satisfy `ORDER BY` and let `LIMIT` stop early.
3. **Filter** remaining index columns without visiting the table.
4. **Fetch** table rows for the columns the index doesn't hold. This step is skipped entirely in an index-only or covering scan.

Everything below follows from those four steps.

## 2. Composite column order

Order the key as: **equality columns, then the one column used for a range or for ordering, then optional columns that only filter or cover.**

| Query | Index | Why |
|---|---|---|
| `WHERE account_id = ? AND status = ? ORDER BY created_at DESC LIMIT 50` | `(account_id, status, created_at)` | Two equalities pin a contiguous slice already sorted by `created_at`; LIMIT stops after 50 entries. |
| `WHERE account_id = ? AND created_at >= ? ORDER BY created_at` | `(account_id, created_at)` | Equality, then one range that also supplies the order. |
| `WHERE account_id = ? AND created_at >= ? AND amount > ?` | `(account_id, created_at, amount)` | Only the first range (`created_at`) narrows the seek. `amount` is checked inside the index, which still avoids table visits for rows that fail. |

**When the range and the sort are on different columns, you must choose.** For `WHERE account_id = ? AND created_at >= ? ORDER BY amount DESC LIMIT 10`:

- `(account_id, created_at)` reads every row in the range, then sorts. That's good when the range is narrow.
- `(account_id, amount)` walks in `amount` order, filters on `created_at`, and stops at 10 matches. That's good when most rows qualify, and terrible when few do, because it may walk the whole account (see the worked example in `explain-guide.md`).

Test both with the worst-case parameters.

**"Most selective column first" is a myth for equality columns.** When every key column is compared with `=`, their order barely affects that lookup. Choose the order that lets the most other queries reuse the leading prefix.

**Sort direction.** A B-tree can be scanned backward, so `(a, b)` serves both `ORDER BY a, b` and `ORDER BY a DESC, b DESC`. Mixed directions such as `ORDER BY a ASC, b DESC` need an index declared with matching directions: `(a ASC, b DESC)`. MySQL 8.0+ honors `DESC` in index definitions.

## 3. Leftmost prefix and skip scan

An index on `(a, b, c)` reliably serves predicates on `a`, on `a, b`, and on `a, b, c`. A filter on `b` alone, or on `c` alone, generally cannot seek.

- **PostgreSQL 18** adds B-tree skip scan. It can use `(a, b)` for a predicate on `b` by probing once per distinct value of `a`. This helps when `a` has few distinct values (a status, a region) and does nothing useful when `a` has millions. In EXPLAIN ANALYZE, a large `Index Searches` count on the node is the sign it's skipping.
- **MySQL 8.0.13+** has a skip-scan range method under narrow conditions: a single-table query, no `GROUP BY` or `DISTINCT`, only index columns referenced, and a range condition on the column after the skipped ones. `Extra` shows `Using index for skip scan`.

Treat skip scan as a bonus that may rescue an existing index, not as a design strategy. If a query is hot, give it an index that leads with its own equality columns.

## 4. Covering indexes

If the index contains every column the query reads, the table is never visited.

```sql
-- PostgreSQL 11+: INCLUDE columns are stored in the leaf entries, not in the search key
CREATE INDEX orders_customer_created_incl
  ON orders (customer_id, created_at DESC) INCLUDE (total, status);
```

- `INCLUDE` columns can't be used for seeking or ordering. They only avoid the table fetch.
- PostgreSQL index-only scans still check the visibility map. On a frequently updated table that isn't vacuumed often, `Heap Fetches` climbs and the benefit shrinks.
- MySQL has no `INCLUDE`. Append the columns to the key instead. Every InnoDB secondary index already carries the primary key columns, so `(customer_id, created_at)` covers `SELECT id, created_at ... WHERE customer_id = ?` when `id` is the primary key. `Extra: Using index` confirms coverage.
- Don't cover wide text or JSON columns. The index grows, fewer entries fit in cache, and every write gets more expensive.

## 5. Partial indexes (PostgreSQL)

Index only the rows the hot query targets:

```sql
CREATE INDEX jobs_queued_run_at_idx ON jobs (run_at) WHERE status = 'queued';

-- The query must contain a predicate that implies the index predicate:
SELECT id FROM jobs WHERE status = 'queued' AND run_at <= now() ORDER BY run_at LIMIT 10;
```

Common uses:

- A small active subset of a large table: queued jobs, unread notifications, open tickets.
- Soft deletes: `... WHERE deleted_at IS NULL`.
- Conditional uniqueness: `CREATE UNIQUE INDEX one_open_subscription ON subscriptions (user_id) WHERE ended_at IS NULL;`.

Gotcha: with a bound parameter (`status = $1`), a generic cached plan cannot prove the parameter equals `'queued'`, so it won't use the partial index. Write the constant into the SQL when the query is meant to use a partial index.

MySQL does not support partial indexes.

## 6. Expression indexes

When the query must apply a function to the column, index that exact expression:

```sql
-- PostgreSQL
CREATE INDEX users_email_lower_idx ON users (lower(email));
-- MySQL 8.0.13+ (functional key part: note the double parentheses)
CREATE INDEX users_email_lower_idx ON users ((lower(email)));

SELECT id FROM users WHERE lower(email) = lower($1);   -- matches the indexed expression
```

- The query must use the same expression. `lower(email)` and `upper(email)` are different expressions.
- PostgreSQL requires the expression to be immutable. An index on `created_at::date` for a `timestamptz` column is rejected because the cast depends on the session time zone. Filter with a range on the bare column instead (section 8).
- In PostgreSQL, an expression index also gets its own planner statistics after `ANALYZE`, which can repair a bad estimate on that expression.
- Often the better fix is to store the normalized value (a lowercased email column, or a `citext` column) so every query benefits without remembering the expression.

## 7. When an index won't help

- **The predicate matches a large fraction of the table.** Random index fetches lose to one sequential read, so the planner is right to scan. Don't fight it; reduce the rows needed instead.
- **Low-cardinality columns** (booleans, a status with three values) are poor standalone indexes. A partial index on the rare value, or the column as a non-leading part of a composite, works better.
- **Physical order matters.** In PostgreSQL, `pg_stats.correlation` near ±1 means rows are stored roughly in index order, which makes range scans cheap. For huge append-only tables queried by time range, a BRIN index is tiny and effective.
- **Negative predicates** (`<>`, `NOT IN`, `NOT LIKE`) rarely benefit from an index. Rephrase as a positive set, or use a partial index on what the query does want.
- **Tiny tables.** A few pages are cheaper to scan than to navigate.

## 8. Sargable rewrites

A predicate is *sargable* when the bare indexed column is compared with a value computed once. Move work to the constant side.

| Non-sargable | Sargable rewrite |
|---|---|
| `created_at::date = '2025-03-01'` / MySQL `DATE(created_at) = '2025-03-01'` | `created_at >= '2025-03-01' AND created_at < '2025-03-02'` |
| `EXTRACT(YEAR FROM created_at) = 2025` / MySQL `YEAR(created_at) = 2025` | `created_at >= '2025-01-01' AND created_at < '2026-01-01'` |
| `created_at + interval '30 days' > now()` | `created_at > now() - interval '30 days'` |
| `amount * 1.1 > 100` | `amount > 100 / 1.1` |
| `COALESCE(deleted_at, 'infinity') > now()` | `deleted_at IS NULL OR deleted_at > now()` |
| `substring(sku, 1, 3) = 'ABC'` / `LEFT(sku, 3) = 'ABC'` | `sku LIKE 'ABC%'` (see section 9 for PostgreSQL collations) |
| `id::text = $1` | `id = $1::bigint` |
| `lower(email) = $1` with no matching index | Expression index (section 6) or a normalized column |
| `a = $1 OR b = $2` | Separate indexes on `a` and `b` (PostgreSQL can BitmapOr them), or split into two indexed branches that cannot return the same row twice (below the table) |
| `($1 IS NULL OR status = $1) AND ($2 IS NULL OR region = $2)` | Build the `WHERE` from only the supplied filters, still with bound parameters, so each shape gets its own plan |

**Splitting an OR without changing results.** A row with `a = $1` and `b = $2` matches both branches, so a plain `UNION ALL` returns it twice and inflates every count or sum built on top. Exclude from the second branch what the first already returned:

```sql
SELECT id, a, b, amount FROM t WHERE a = $1
UNION ALL
SELECT id, a, b, amount FROM t WHERE b = $2 AND (a = $1) IS NOT TRUE;
```

`(a = $1) IS NOT TRUE` is true when `a` differs from `$1`, when `a` is NULL, and when `$1` is NULL, which is exactly the set of rows the first branch did not return. (`a IS DISTINCT FROM $1` misses rows where both are NULL, so it is only correct when `$1` is never NULL.) The same predicate works in MySQL 8.0+. Each branch can seek its own index; the exclusion is just a filter on the second branch's rows.

- Plain `UNION` is equivalent only when the select list includes a unique key. Otherwise it also removes rows that are legitimately identical.
- Put any `ORDER BY` and `LIMIT` around the whole union.
- Prove the rewrite with the `EXCEPT ALL` diff from correctness-traps.md, section 22, on seed rows that match both branches and rows with NULL in `a`.

PostgreSQL 18 rewrites `col = 1 OR col = 2 OR ...` on the **same** column into `col = ANY(...)` automatically. ORs across **different** columns still need the treatment above.

## 9. Text search: prefix, infix, case-insensitive

| Need | PostgreSQL | MySQL |
|---|---|---|
| Prefix: `LIKE 'abc%'` | A plain B-tree works only with the `C` collation. Otherwise create it with `text_pattern_ops` / `varchar_pattern_ops`: `CREATE INDEX ... ON products (sku text_pattern_ops);`. That index does not serve `<`/`>`/`ORDER BY`, so keep a normal index if you need those. | A B-tree works for a constant prefix. |
| Infix: `LIKE '%abc%'`, `ILIKE` | `pg_trgm` extension with a GIN trigram index: `CREATE INDEX ... ON products USING gin (name gin_trgm_ops);`. Effective for search terms of 3+ characters. | A B-tree cannot help. Use a `FULLTEXT` index with `MATCH ... AGAINST`, or an external search engine. |
| Word search, ranking, stemming | Full-text search: `to_tsvector` / `to_tsquery` with a GIN index | `FULLTEXT` index |
| Case-insensitive equality | Expression index on `lower(col)`, `citext`, or a nondeterministic ICU collation | Default `_ci` collations already compare case-insensitively |

## 10. Keyset pagination

`OFFSET n` makes the database produce and discard `n` rows on every page, so cost grows with page depth. Rows inserted or deleted between requests also shift page boundaries, causing duplicates and skips. Keyset (seek) pagination remembers where the last page ended:

```sql
-- PostgreSQL: row-value comparison; sort key must end in a unique column
SELECT id, created_at, total
FROM orders
WHERE customer_id = $1
  AND (created_at, id) < ($2, $3)          -- values from the last row of the previous page
ORDER BY created_at DESC, id DESC
LIMIT 20;

-- Supporting index (also serves the first page, which omits the row comparison)
CREATE INDEX orders_customer_created_id_idx ON orders (customer_id, created_at DESC, id DESC);
```

MySQL's optimizer often fails to use an index fully for row-constructor comparisons, so write the expanded form and confirm with EXPLAIN:

```sql
WHERE customer_id = ?
  AND (created_at < ? OR (created_at = ? AND id < ?))
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Rules:

- The ordering must be total. End it with a unique column, or rows with tied timestamps get skipped or repeated.
- All sort columns should go the same direction for the row-comparison form. Mixed directions need the expanded form and a matching index.
- Nullable sort columns break the comparison, since NULLs never satisfy `<`. Use NOT NULL columns, or sort on a `COALESCE`d expression in both the index and the query.
- Keep the cursor at full precision. Round-tripping a microsecond timestamp through a millisecond type, such as a JavaScript `Date`, silently skips or repeats rows. Encode the cursor opaquely (for example, base64 of the raw values), and never let clients build it.
- Keyset can't jump to page 37. If the product needs numbered pages, cap the depth, or combine keyset with an approximate total.
- For "previous page," flip the comparison and the sort, then reverse the rows in the application.

## 11. Large IN lists and ID sets

Expanding thousands of IDs into `IN ($1, $2, ..., $5000)` costs parsing and planning on every call, yields a different statement text per list length (defeating statement caches and statistics grouping), and eventually hits the protocol's bind-parameter limit (65,535 in both PostgreSQL and MySQL).

**PostgreSQL: bind one array.**

```sql
SELECT * FROM orders WHERE id = ANY($1::bigint[]);

-- Join form: carries per-ID extras and preserves the caller's order
SELECT o.*
FROM unnest($1::bigint[]) WITH ORDINALITY AS ids(id, ord)
JOIN orders o ON o.id = ids.id
ORDER BY ids.ord;

-- Several parallel arrays become rows
SELECT * FROM unnest($1::bigint[], $2::text[]) AS t(id, code);
```

Most PostgreSQL drivers bind a native list or array to an array parameter; check the driver's documentation for the exact call. Through an ORM, use its array type or a raw parameterized query.

**MySQL** has no array parameters:

- Send the IDs in fixed-size chunks, a few hundred to a few thousand per statement. Keep the chunk size constant so statement shapes repeat.
- For very large sets, load a temporary table, then join to it.
- Or unpack a single JSON parameter (8.0.4+):
  ```sql
  SELECT o.* FROM JSON_TABLE(?, '$[*]' COLUMNS (id BIGINT PATH '$')) AS ids
  JOIN orders o ON o.id = ids.id;
  ```
- Very large literal `IN` lists can exceed `range_optimizer_max_mem_size`, at which point MySQL abandons the range plan for a scan.

**At scale, the caller should send the criteria.** If the IDs came from a query the client ran earlier ("all orders for customers in region X"), pass the criteria and resolve the set server-side with a join or subquery. Beyond tens of thousands of IDs, move the work to a background job that processes the set in bounded batches.

## 12. Counting large tables

`SELECT count(*) FROM big_table WHERE ...` visits every qualifying row. In PostgreSQL that holds even with an index, since the index cannot prove each row is visible to the current transaction; an index-only scan helps only when the visibility map is current.

Choose by what the caller actually needs:

| Need | Approach |
|---|---|
| "Is there at least one?" | `SELECT EXISTS (SELECT 1 FROM t WHERE ...)`. It stops at the first match. |
| Whole-table size for a dashboard | PostgreSQL: `SELECT reltuples::bigint FROM pg_class WHERE oid = 'public.orders'::regclass;` (−1 means not yet analyzed, on PG 14+). MySQL: `information_schema.TABLES.TABLE_ROWS`, a rough InnoDB estimate. |
| Filtered estimate | The planner's row estimate from `EXPLAIN (FORMAT JSON)`, the top node's "Plan Rows". It's approximate, so label it as approximate. |
| "1,000+" style UI totals | Capped count: `SELECT count(*) FROM (SELECT 1 FROM t WHERE ... LIMIT 1001) s;` |
| Exact, frequently read | Maintained counter (a trigger or application update) or a periodically refreshed summary. A single counter row becomes a write hotspot; spread it across several rows and sum them, or refresh asynchronously. |

Pagination UIs often don't need a total at all. "Next page exists" can be answered by fetching `LIMIT n + 1`.

## 13. CTEs and subqueries

**PostgreSQL CTEs.**

- Before 12, every CTE is materialized: computed once in full, with no filters pushed in from the outer query.
- From 12, a non-recursive, side-effect-free CTE referenced once is inlined like a subquery. One referenced two or more times is materialized.
- Override deliberately:

  ```sql
  -- Allow the outer filter to reach the base table even though the CTE is referenced twice
  WITH recent AS NOT MATERIALIZED (SELECT * FROM events WHERE created_at > now() - interval '1 day')
  SELECT ... FROM recent r1 JOIN recent r2 ON ... WHERE r1.user_id = $1;

  -- Referenced once, so the default would inline it
  WITH scored AS MATERIALIZED (SELECT id, expensive_score(payload) AS s FROM docs)
  SELECT id, s FROM scored WHERE s > 0.8;
  ```

  Inlined, `s` is replaced by `expensive_score(payload)` in both the `WHERE` and the select list, so the function runs twice for every row that passes the filter. `MATERIALIZED` computes it once per row. This applies to functions declared `IMMUTABLE` or `STABLE`. A `VOLATILE` function (the default for a new function) already prevents inlining. A CTE referenced two or more times is materialized by default, so `MATERIALIZED` there changes nothing.
- The other legitimate use of `MATERIALIZED` is as an optimization fence: when the planner badly misestimates the inlined subquery and picks a poor join order, materializing it fixes its row count. Prefer fixing the statistics (explain-guide.md, section 7), and say in a comment why the fence is there.
- Data-modifying CTEs (`WITH x AS (DELETE ... RETURNING ...)`) always execute exactly once, to completion, regardless of how much of their output is read.

**MySQL CTEs and derived tables (8.0+).** The optimizer either merges them into the outer query or materializes them; from 8.0.22 it can push outer conditions into a materialized derived table. Check `EXPLAIN` for a `<derived N>` table with a full scan.

**Recursive CTEs.** Make termination explicit with a depth column and `WHERE depth < N`. PostgreSQL 14+ has `CYCLE` and `SEARCH` clauses for graph walks. MySQL stops at `cte_max_recursion_depth` (default 1000) with an error.

**Subqueries.**

- `IN (subquery)` and `EXISTS` usually become semi-joins, which is efficient.
- `NOT EXISTS` becomes an anti-join. `NOT IN (subquery)` does not, except from PostgreSQL 19 when both sides are provably non-NULL; see correctness-traps.md, section 1.
- A scalar subquery in the `SELECT` list that references the outer row runs per row unless the planner can decorrelate it. Rewrite it as a join, or as `LATERAL` when it needs `ORDER BY ... LIMIT 1`.

## 14. What indexes cost, and finding the useless ones

Each index:

- Adds work to every `INSERT`, and to every `UPDATE` that changes an indexed column. In PostgreSQL, updating a column that has a B-tree index also prevents a heap-only-tuple (HOT) update, so the row's other indexes must be updated too.
- Uses disk and cache, competing with the data that hot queries need.
- Slows vacuum, backups, and restores.

Before adding an index, look for one that already serves the query or could be widened: `(a)` is redundant next to `(a, b)`, unless `(a)` is unique or much smaller and hot.

Find candidates for removal:

```sql
-- PostgreSQL: never-scanned, non-unique indexes since statistics were last reset
SELECT s.schemaname, s.relname AS table_name, s.indexrelname AS index_name,
       s.idx_scan, pg_size_pretty(pg_relation_size(s.indexrelid)) AS index_size
FROM pg_stat_user_indexes s
JOIN pg_index i ON i.indexrelid = s.indexrelid
WHERE s.idx_scan = 0 AND NOT i.indisunique
ORDER BY pg_relation_size(s.indexrelid) DESC;
```

```sql
-- MySQL (sys schema)
SELECT * FROM sys.schema_unused_indexes;
SELECT * FROM sys.schema_redundant_indexes;
```

Before dropping anything, check that the statistics cover a full business cycle (month-end and year-end jobs). Check every replica too, since usage counters are per server and an index unused on the primary may serve replica reads. Don't drop indexes that back constraints. Drop through the migration process.
