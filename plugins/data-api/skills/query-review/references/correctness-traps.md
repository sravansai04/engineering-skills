# Correctness Traps: Counterexamples and Fixes

Each section gives the failing pattern, a minimal demonstration, and the rewrite. Use the demonstrations in review comments, since a three-row counterexample settles an argument faster than an explanation does. Examples are PostgreSQL unless marked; MySQL differences are noted inline.

## Contents

1. NOT IN with a nullable subquery
2. Comparisons with NULL
3. Negative filters silently drop NULL rows
4. Aggregates and NULL
5. LEFT JOIN turned into an inner join
6. Join fan-out inflating aggregates
7. DISTINCT as a symptom
8. Joins on keys that are not actually unique
9. UNION versus UNION ALL
10. Ungrouped columns
11. Latest row per group
12. Non-deterministic ordering
13. NULLs in sort order
14. Window frame defaults
15. Integer division and division by zero
16. Floating point for money
17. Date-range boundaries
18. Time zones and DST
19. What "now" means
20. Implicit casts
21. Case sensitivity and collation
22. Proving a rewrite returns the same rows

---

## 1. NOT IN with a nullable subquery

`x NOT IN (a, b, NULL)` expands to `x <> a AND x <> b AND x <> NULL`. The last term is unknown, so the whole predicate is never true.

```sql
SELECT 3 NOT IN (1, 2, NULL);   -- NULL, not true; a WHERE clause treats it as false
```

So this returns zero rows as soon as one `blocked_accounts.customer_id` is NULL:

```sql
SELECT * FROM customers
WHERE id NOT IN (SELECT customer_id FROM blocked_accounts);
```

Fix: use `NOT EXISTS`. It has the intended semantics, and PostgreSQL plans it as an anti-join. `NOT IN (subquery)` cannot become an anti-join because of these NULL rules, so it runs as a hashed or per-row SubPlan that degrades badly when the subquery result is large.

```sql
SELECT * FROM customers c
WHERE NOT EXISTS (SELECT 1 FROM blocked_accounts b WHERE b.customer_id = c.id);
```

`NOT IN` with a literal list of non-NULL constants is fine.

Version note: from PostgreSQL 19 the planner converts `NOT IN (subquery)` to an anti-join when it can prove neither side yields NULL, for example when both columns are declared `NOT NULL`. That removes the performance penalty for those columns only. The NULL semantics are unchanged, so still prefer `NOT EXISTS` for nullable columns, for older servers, and for portability.

## 2. Comparisons with NULL

`col = NULL` and `col <> NULL` evaluate to NULL for every row.

| Intent | PostgreSQL | MySQL |
|---|---|---|
| is missing | `col IS NULL` | `col IS NULL` |
| equal, treating NULL = NULL as true | `a IS NOT DISTINCT FROM b` | `a <=> b` |
| different, treating NULL as a value | `a IS DISTINCT FROM b` | `NOT (a <=> b)` |

This matters most in change-detection queries such as `WHERE new.email <> old.email`, which misses changes to or from NULL.

## 3. Negative filters silently drop NULL rows

```sql
-- status values: 'active', 'closed', NULL
SELECT count(*) FROM accounts WHERE status <> 'closed';   -- excludes NULL-status rows too
```

If NULL rows belong in the result, say so: `WHERE status IS DISTINCT FROM 'closed'` or `WHERE status <> 'closed' OR status IS NULL`. The same applies to `NOT IN ('a', 'b')`, `NOT LIKE`, and `NOT (col > 5)`.

## 4. Aggregates and NULL

| Expression | Over rows (10, NULL, 20) | Over zero rows |
|---|---|---|
| `COUNT(*)` | 3 | 0 |
| `COUNT(col)` | 2 | 0 |
| `SUM(col)` | 30 | NULL |
| `AVG(col)` | 15 (NULL skipped in numerator and denominator) | NULL |
| `MAX(col)` | 20 | NULL |

- Wrap a `SUM` that feeds arithmetic or display in `COALESCE(SUM(x), 0)`.
- If NULL means zero for the business, `AVG(COALESCE(col, 0))` gives 10 here, not 15. Decide which one is right; don't let the default decide.
- `COUNT(DISTINCT col)` also ignores NULLs.

## 5. LEFT JOIN turned into an inner join

```sql
SELECT c.id, o.id
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE o.status = 'paid';     -- unmatched customers have o.status NULL, so they are filtered out
```

To keep every customer and match only paid orders, move the predicate into the join:

```sql
LEFT JOIN orders o ON o.customer_id = c.id AND o.status = 'paid'
```

To find customers with **no** paid order, use `NOT EXISTS`, or `WHERE o.id IS NULL` with the predicate in `ON`. In general, a `WHERE` test on a right-table column keeps the unmatched rows only if it is true when that column is NULL, which is why `o.id IS NULL` (on a non-nullable key) works and `o.status = 'paid'` does not.

## 6. Join fan-out inflating aggregates

One order with three items (10, 20, 30) and two payments (30, 30):

```sql
SELECT o.id, SUM(oi.price) AS item_total, SUM(p.amount) AS paid, COUNT(p.id) AS payment_count
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
JOIN payments p     ON p.order_id = o.id
GROUP BY o.id;
-- item_total = 120 (should be 60), paid = 180 (should be 60), payment_count = 6 (should be 2)
```

The join produces 3 × 2 = 6 rows. Every independent one-to-many child multiplies the others.

**Fix A: aggregate each child first, then join on the parent key.** This works well when most parents are in scope, since each child table is aggregated once and hash-joined.

```sql
SELECT o.id, COALESCE(i.item_total, 0) AS item_total, COALESCE(p.paid, 0) AS paid
FROM orders o
LEFT JOIN (SELECT order_id, SUM(price) AS item_total
           FROM order_items GROUP BY order_id) i ON i.order_id = o.id
LEFT JOIN (SELECT order_id, SUM(amount) AS paid
           FROM payments GROUP BY order_id) p ON p.order_id = o.id;
```

**Fix B: LATERAL per parent.** This works well when few parents are in scope and the child's `order_id` is indexed. It is available in PostgreSQL and in MySQL 8.0.14+.

```sql
SELECT o.id, i.item_total, p.paid
FROM orders o
CROSS JOIN LATERAL (SELECT COALESCE(SUM(price), 0) AS item_total
                    FROM order_items WHERE order_id = o.id) i
CROSS JOIN LATERAL (SELECT COALESCE(SUM(amount), 0) AS paid
                    FROM payments WHERE order_id = o.id) p
WHERE o.created_at >= '2025-01-01' AND o.created_at < '2025-04-01';
```

An aggregate subquery without `GROUP BY` always returns exactly one row, so `CROSS JOIN LATERAL` cannot drop parents here.

**Fix C: EXISTS when the child is only a filter.** For "orders that have at least one refunded payment," a join produces duplicates and `EXISTS` does not.

Fan-out also hides in ORMs: filtering across a to-many relation (Django `filter(items__sku=...)`, a JPA join in a criteria query) can duplicate the parent rows.

## 7. DISTINCT as a symptom

`SELECT DISTINCT` added after the fact usually means a join fans out (section 6) or matches on a non-unique key (section 8). Problems with leaving it in place:

- It removes duplicate output rows but not the inflation inside `SUM`/`COUNT` computed before it.
- `SUM(DISTINCT amount)` drops two genuinely different payments that happen to be equal.
- It forces a sort or hash over the full result.
- It hides the defect from anyone reading the code later.

`DISTINCT` is legitimate when the question is genuinely "the set of distinct values," such as listing the countries that have customers. Prefer `EXISTS` for "parents that have a matching child."

## 8. Joins on keys that are not actually unique

A join on `email`, `external_id`, or `(customer_id, effective_date)` is only one-to-one if a unique constraint enforces it. Check the schema. If there is no constraint:

- Add one, which belongs to `data-api:db-migration-safety` work, or
- Make the join pick one row deliberately (`DISTINCT ON`, `ROW_NUMBER() = 1`, or `LATERAL ... LIMIT 1` with a defined order), or
- Accept and document the fan-out.

Effective-dated tables are a common source. A join with `ON e.date BETWEEN r.start AND r.end` fans out when ranges overlap or touch on a shared endpoint. Use half-open ranges, and in PostgreSQL an exclusion constraint, to prevent overlaps.

## 9. UNION versus UNION ALL

`UNION` removes duplicate rows across and within its branches. If two branches can legitimately produce identical rows (two equal payments), `UNION` drops one. If the branches cannot overlap, `UNION ALL` gives the same result and skips the deduplication sort or hash. Pick based on meaning, then enjoy the speed.

## 10. Ungrouped columns

```sql
SELECT customer_id, status, MAX(created_at)
FROM orders GROUP BY customer_id;
```

- PostgreSQL raises an error, unless `status` is functionally dependent on the grouped columns, which in practice means they include the table's primary key.
- MySQL with `ONLY_FULL_GROUP_BY` in `sql_mode` (the default since 5.7.5) also errors. With it disabled, MySQL returns `status` from an arbitrary row of each group. Do not "fix" the error by removing that mode. MySQL's `ANY_VALUE(status)` makes the arbitrariness explicit, which is acceptable only when every row in the group has the same value.

## 11. Latest row per group

`MAX(created_at)` alongside other columns does not return the other columns of the max row. Correct patterns:

```sql
-- PostgreSQL: DISTINCT ON keeps the first row per key in ORDER BY order
SELECT DISTINCT ON (customer_id) customer_id, id, status, created_at
FROM orders
ORDER BY customer_id, created_at DESC, id DESC;

-- Portable (PostgreSQL, MySQL 8.0+): window function
SELECT customer_id, id, status, created_at
FROM (
  SELECT o.customer_id, o.id, o.status, o.created_at,
         ROW_NUMBER() OVER (PARTITION BY o.customer_id
                            ORDER BY o.created_at DESC, o.id DESC) AS rn
  FROM orders o
) ranked
WHERE rn = 1;

-- Per parent with an index on orders (customer_id, created_at DESC):
-- one short index probe per customer, good when there are few parents and many rows each
SELECT c.id, last_order.*
FROM customers c
LEFT JOIN LATERAL (
  SELECT o.id, o.status, o.created_at
  FROM orders o
  WHERE o.customer_id = c.id
  ORDER BY o.created_at DESC, o.id DESC
  LIMIT 1
) last_order ON true;
```

Include a unique tiebreaker (`id`) in the ordering, or two rows with the same timestamp will be chosen arbitrarily. Use `RANK()` instead of `ROW_NUMBER()` if ties should all be returned.

## 12. Non-deterministic ordering

SQL guarantees no row order without `ORDER BY`, and only a partial order when the sort key has ties. Symptoms: a "first" row that changes between runs, and pagination that repeats or skips rows. It often appears only after a plan change (a parallel scan, a new index), so it passes tests and fails in production.

- Every `LIMIT`/`OFFSET`/keyset query needs an `ORDER BY` ending in a unique column: `ORDER BY created_at DESC, id DESC`.
- Ordering in a subquery or view is not guaranteed to survive the outer query. Order at the outermost level.

## 13. NULLs in sort order

The engines disagree on where NULL sorts, so the same top-N query returns different rows:

| Engine | `ORDER BY x` (ascending) | `ORDER BY x DESC` |
|---|---|---|
| PostgreSQL | NULLs last (NULL sorts above every value) | NULLs first |
| MySQL | NULLs first (NULL sorts below every value) | NULLs last |

```sql
-- scores: 90, 70, NULL
SELECT score FROM players ORDER BY score DESC LIMIT 2;
-- PostgreSQL: NULL, 90      MySQL: 90, 70
```

Fixes:

- **PostgreSQL:** say what you mean, `ORDER BY score DESC NULLS LAST`. For an index to deliver that order without a Sort node, declare it the same way: `CREATE INDEX ON players (score DESC NULLS LAST);`. A plain `(score)` index scanned backward yields `DESC NULLS FIRST`, which does not match.
- **MySQL** has no `NULLS FIRST/LAST` clause. Sort on the null test first: `ORDER BY score IS NULL, score` puts NULLs last in ascending order. This expression usually stops an index from providing the order, so check `EXPLAIN` for `Using filesort` on large tables.
- **Portable:** `ORDER BY CASE WHEN score IS NULL THEN 1 ELSE 0 END, score DESC` behaves the same on both engines.
- Keyset cursors over a nullable sort column break on top of this (index-design.md, section 10).

## 14. Window frame defaults

When `OVER (...)` contains an `ORDER BY` but no frame clause, the frame is `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. In `RANGE` mode the frame ends at the current row's last *peer* (rows with an equal sort key), not at the current row. Two consequences:

```sql
-- amounts by day: (1 Jan, 10), (2 Jan, 20), (2 Jan, 5), (3 Jan, 30)
SELECT day, amount,
       SUM(amount)        OVER (ORDER BY day) AS running,
       LAST_VALUE(amount) OVER (ORDER BY day) AS last_amt
FROM sales;
-- running:  10, 35, 35, 65   both 2 Jan rows include each other, so neither shows its own subtotal
-- last_amt: 10, then 20 or 5 for both 2 Jan rows, 30   never the partition's last value except on the final day
```

- A running total that must step row by row needs `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` and a unique tiebreaker in the window order (`ORDER BY day, id`). Without the tiebreaker, the order among tied rows, and so the running values, can change between runs.
- `LAST_VALUE` (and `NTH_VALUE`) over the whole partition needs `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`. Often clearer: `FIRST_VALUE(amount) OVER (ORDER BY day DESC, id DESC)`.
- The rules are the same in PostgreSQL and MySQL 8.0+.

## 15. Integer division and division by zero

```sql
-- PostgreSQL: count() returns bigint, so this is integer division and yields 0
SELECT count(*) FILTER (WHERE status = 'shipped') / count(*) AS shipped_ratio FROM orders;

-- Fix: force numeric and guard the divisor
SELECT 100.0 * count(*) FILTER (WHERE status = 'shipped') / NULLIF(count(*), 0) AS shipped_pct
FROM orders;
```

- PostgreSQL raises an error on division by zero. MySQL returns NULL with a warning in a `SELECT`; in strict mode, data-changing statements can error instead. `NULLIF(divisor, 0)` makes the result NULL on both engines, which is usually what a report wants.
- MySQL's `/` returns a decimal (`5 / 2 = 2.5000`), and `DIV` truncates. `FILTER` is not available in MySQL; use `SUM(status = 'shipped')` or `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`.
- Watch the operation order: `count_a / count_b * 100` truncates before multiplying. Put the decimal operand first.

## 16. Floating point for money

```sql
SELECT 0.1::float8 + 0.2::float8 = 0.3::float8;   -- false
SELECT 0.1 + 0.2 = 0.3;                           -- true: unadorned literals are numeric
```

Store and compute currency in `numeric(p, s)` / `DECIMAL(p, s)`, or as integer minor units. Round once, at a defined step, with a defined rule. Never sum already-rounded line amounts and expect the total to equal the rounded sum of unrounded amounts.

## 17. Date-range boundaries

```sql
-- created_at is a timestamp: BETWEEN stops at 2025-01-31 00:00:00, so most of the 31st is lost
WHERE created_at BETWEEN '2025-01-01' AND '2025-01-31'

-- Half-open range: correct for any precision and directly usable by an index
WHERE created_at >= '2025-01-01' AND created_at < '2025-02-01'
```

Patching it with `'2025-01-31 23:59:59'` misses fractional seconds. For `date` columns `BETWEEN` is inclusive and correct, but half-open ranges work for both types, so use them everywhere. Adjacent periods built from half-open ranges never overlap or leave gaps.

## 18. Time zones and DST

**PostgreSQL types.** `timestamptz` stores an absolute instant and displays it in the session's `TimeZone`. `timestamp` stores wall-clock time with no zone. Converting between them, including comparing one with the other, uses the session `TimeZone`, so the same query can return different rows for different connections.

```sql
SET TimeZone = 'UTC';
SELECT ('2025-03-01 02:30:00+00'::timestamptz)::date;   -- 2025-03-01
SET TimeZone = 'America/New_York';
SELECT ('2025-03-01 02:30:00+00'::timestamptz)::date;   -- 2025-02-28
```

**`AT TIME ZONE` runs in opposite directions depending on its input type.** On `timestamptz` it returns the local wall-clock time in that zone. On `timestamp` it assumes the stored value already is local time in that zone and returns an instant. Check the column type before writing a conversion:

| Column type | Expression that gives New York wall-clock time |
|---|---|
| `timestamptz` | `created_at AT TIME ZONE 'America/New_York'` |
| `timestamp` holding UTC | `(created_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/New_York'` |

Many applications store UTC in plain `timestamp` columns. Applying the one-step form to them reads each UTC value as New York time and shifts it the wrong way: a stored `2025-03-01 03:30` (UTC) becomes the instant `08:30 UTC`, not `2025-02-28 22:30` New York time, and a following `::date` then renders that in the session zone. Rows near midnight land in the wrong day without any error.

Bucket by an explicit business zone instead of the session's:

```sql
-- timestamptz column
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS local_day, count(*)
FROM orders GROUP BY 1;

-- timestamp column holding UTC
SELECT ((created_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/New_York')::date AS local_day, count(*)
FROM orders GROUP BY 1;

-- PostgreSQL 12+, timestamptz input: three-argument date_trunc returns the local day start as timestamptz
SELECT date_trunc('day', created_at, 'America/New_York') AS local_day_start, count(*)
FROM orders GROUP BY 1;
```

To filter by a local day and keep the predicate sargable, convert the bounds, not the column, and produce bounds of the column's own type:

```sql
-- timestamptz column: the bounds are instants
WHERE created_at >= TIMESTAMP '2025-03-01 00:00' AT TIME ZONE 'America/New_York'
  AND created_at <  TIMESTAMP '2025-03-02 00:00' AT TIME ZONE 'America/New_York'

-- timestamp column holding UTC: turn the local midnight into an instant, then into UTC wall-clock time
WHERE created_at >= (TIMESTAMP '2025-03-01 00:00' AT TIME ZONE 'America/New_York') AT TIME ZONE 'UTC'
  AND created_at <  (TIMESTAMP '2025-03-02 00:00' AT TIME ZONE 'America/New_York') AT TIME ZONE 'UTC'
```

A bare literal bound such as `created_at >= '2025-03-01'` on a `timestamptz` column is read in the session `TimeZone`, so a report run from a UTC session and one run from a local session cut the day at different instants. Comparing a `timestamptz` bound with a `timestamp` column also converts through the session `TimeZone`. Write the business zone into the bound.

**DST.** A local day is not always 24 hours. With the session in `America/New_York`, adding `interval '1 day'` to a `timestamptz` keeps the wall-clock time across the March and November transitions, while `interval '24 hours'` does not. Pick the one the business rule means, and test with timestamps on both sides of a transition.

**MySQL.** `TIMESTAMP` columns are converted from the session `time_zone` to UTC on write and back on read. `DATETIME` is stored as written, with no conversion. `CONVERT_TZ()` with named zones such as `'America/New_York'` returns NULL unless the server's time zone tables are loaded.

**Application side.** Make sure the driver, the ORM, and the database agree on the zone. A common bug is an application that sends naive local times into a UTC-assuming column.

## 19. What "now" means

| Function | PostgreSQL meaning |
|---|---|
| `now()`, `CURRENT_TIMESTAMP`, `transaction_timestamp()` | start of the current transaction |
| `statement_timestamp()` | start of the current statement |
| `clock_timestamp()` | actual time, changes during a statement |

In a long transaction, `now()` stays frozen, so `WHERE expires_at < now()` in a loop never sees time move. In MySQL, `NOW()` is the statement start time and `SYSDATE()` is the time of evaluation.

## 20. Implicit casts

**MySQL: comparing a string column to a number** converts every row's string to a number. It cannot use the index, and it matches surprising values:

```sql
-- phone is VARCHAR and indexed
SELECT * FROM users WHERE phone = 5551234;     -- full scan; '5551234abc' also matches
SELECT * FROM users WHERE phone = '5551234';   -- index lookup
```

**MySQL: join columns with different character sets or collations** force a conversion on one side, which can stop that side's index from being used. Look for it when `EXPLAIN` shows a full scan on a join that "should" be indexed.

**PostgreSQL: parameter type wider than the column.** A driver binding a decimal value against an `integer` column produces `(id)::numeric = $1`. The cast is on the column, so the index on `id` is skipped:

```sql
EXPLAIN SELECT * FROM orders WHERE id = 42::numeric;
-- Seq Scan on orders  Filter: ((id)::numeric = '42'::numeric)
```

Bind with the column's own type, or cast the parameter (`$1::integer`), never the column.

**Text-typed identifiers.** `WHERE id::text = $1` in PostgreSQL, or a UUID stored as text in one table and as a native type in another, creates the same problem. Cast the parameter to the column type.

## 21. Case sensitivity and collation

- MySQL's default collations, such as `utf8mb4_0900_ai_ci` in 8.0, are case- and accent-insensitive: `'Café' = 'cafe'` is true, and a unique index rejects both values.
- PostgreSQL comparisons are case-sensitive by default. Options for case-insensitive matching: an expression index on `lower(col)` with queries that use `lower(col)`, the `citext` extension, or a nondeterministic ICU collation.
- Porting a query or a uniqueness rule between engines without checking collation changes results.
- `ORDER BY` on text follows the collation, and different OS or ICU library versions can sort differently. Don't depend on text order across environments for anything that must be stable, such as keyset cursors on a text column.

## 22. Proving a rewrite returns the same rows

Run both directions; each must return zero rows. `EXCEPT ALL` respects duplicate counts and treats NULLs as equal. It is supported in PostgreSQL and in MySQL 8.0.31+.

```sql
(SELECT ... original query ...)
EXCEPT ALL
(SELECT ... rewritten query ...);

(SELECT ... rewritten query ...)
EXCEPT ALL
(SELECT ... original query ...);
```

- Round floating or high-precision numeric outputs to the precision the consumer uses before comparing.
- Remove `ORDER BY`/`LIMIT` from both before comparing sets, then check ordering separately if it matters.
- An empty diff only proves equality on the data you ran it against. Seed the edge cases first: NULLs in every nullable column, duplicate values, parents with zero children and with several, rows exactly on range boundaries (midnight, month end, both sides of a DST change), and very large and very small values.
- When the query feeds application code, also run the tests that cover it. Equivalent SQL can still change column types or names the caller depends on.
