# PostgreSQL migration reference

This file covers lock levels, rewrites and safe forms for each operation, based on the PostgreSQL 18 documentation. PostgreSQL 19, due for release in late October 2026, is noted where it changes things. The version table lists the releases where behavior changed. Run `SELECT version();` first, because some of these recipes don't exist on older majors.

## Contents

1. Lock modes that matter
2. The lock queue and timeouts
3. Operation cheat sheet
4. Recipes: NOT NULL, CHECK, FOREIGN KEY, UNIQUE/PRIMARY KEY, indexes, type changes, partitions
5. Transactions and non-transactional statements
6. Idempotency snippets
7. Measuring and monitoring
8. Replication, poolers, prepared statements
9. Version feature table

## 1. Lock modes that matter

| Lock | What it blocks | Typical holders |
|---|---|---|
| `ACCESS EXCLUSIVE` | Everything, plain `SELECT` included | most `ALTER TABLE` forms, `DROP`, `TRUNCATE`, `VACUUM FULL`, `CLUSTER` |
| `SHARE ROW EXCLUSIVE` | writes (and other DDL) | `ADD FOREIGN KEY` (on both tables), `CREATE TRIGGER` |
| `SHARE` | writes (`INSERT`/`UPDATE`/`DELETE`) | `CREATE INDEX` (non-concurrent) |
| `SHARE UPDATE EXCLUSIVE` | other DDL, `VACUUM`; reads and writes go through | `CREATE INDEX CONCURRENTLY`, `VALIDATE CONSTRAINT`, `ANALYZE`, `ATTACH PARTITION` (on the parent) |

Unless the docs say otherwise for a subcommand, `ALTER TABLE` takes `ACCESS EXCLUSIVE`. When a single `ALTER TABLE` carries several subcommands, it takes the strongest lock any of them needs.

## 2. The lock queue and timeouts

PostgreSQL grants locks in request order. Here is how a "fast" `ALTER` takes a table down:

1. A report query or an idle-in-transaction session has held `ACCESS SHARE` on `orders` for 10 minutes.
2. `ALTER TABLE orders ADD COLUMN ...` asks for `ACCESS EXCLUSIVE` and waits.
3. Every new `SELECT`/`INSERT` on `orders` queues behind the waiting `ALTER`. The table is effectively down until step 1 finishes.

The defense is to fail fast and retry:

```sql
SET lock_timeout = '3s';         -- give up acquiring a lock after 3s
SET statement_timeout = '60s';   -- cap total runtime
ALTER TABLE orders ADD COLUMN fulfilled_at timestamptz;
RESET lock_timeout;              -- a plain SET lasts for the whole session
RESET statement_timeout;
```

- **Scope the settings.** Inside an explicit transaction, use `SET LOCAL`, which ends with the transaction. Outside one, `SET LOCAL` only draws a warning and does nothing, so use plain `SET` and `RESET` afterwards. A plain `SET` otherwise stays in force for every later statement the tool runs on that connection, including a later concurrent build.
- **Concurrent operations are the exception.** `CREATE INDEX CONCURRENTLY`, `REINDEX CONCURRENTLY`, `DROP INDEX CONCURRENTLY` and `DETACH PARTITION ... CONCURRENTLY` wait for other transactions to finish, and `lock_timeout` applies to those waits. A seconds-scale value cancels them partway, and they leave a broken object behind (section 4.5). Run them with `SET lock_timeout = 0` (or minutes) and cap them with `statement_timeout` instead. Ordinary traffic isn't affected while they wait, because the `SHARE UPDATE EXCLUSIVE` lock they hold or request doesn't conflict with reads or writes. It does hold off other DDL and vacuum on that table. `VALIDATE CONSTRAINT` can take the relaxed setting for the same reason.
- Retry the whole migration a few times, with jittered backoff, when it fails with SQLSTATE `55P03` (lock_not_available). Most migration tools won't do this for you, so wrap the command. The retry has to cope with leftovers: a canceled concurrent build needs the drop-and-rebuild pattern in section 6, not a bare `IF NOT EXISTS`.
- `idle_in_transaction_session_timeout` (server or role setting) limits how long forgotten transactions can block DDL. PostgreSQL 17+ also has `transaction_timeout`.

## 3. Operation cheat sheet

| Operation | Lock | Rewrite / full scan? | Safe approach |
|---|---|---|---|
| `CREATE INDEX` | `SHARE` | builds while blocking writes | `CREATE INDEX CONCURRENTLY` (section 4.5) |
| `DROP INDEX` | `ACCESS EXCLUSIVE` | no | `DROP INDEX CONCURRENTLY`. It can't drop an index that backs a constraint |
| `REINDEX` | `SHARE` on the table plus `ACCESS EXCLUSIVE` on the index. Planning a query locks every index of its table, so this blocks almost every read and write on the table, not only queries that use the index | rebuild | `REINDEX INDEX CONCURRENTLY` (12+) |
| `ADD COLUMN`, nullable, no default | `ACCESS EXCLUSIVE`, brief | no | lock timeout only |
| `ADD COLUMN ... DEFAULT` non-volatile (constant, `now()`) | `ACCESS EXCLUSIVE`, brief | no (11+); existing rows read the stored default | fine. Note `now()` is evaluated once, so all existing rows get the migration's timestamp |
| `ADD COLUMN` with volatile default (`clock_timestamp()`, `gen_random_uuid()`, `random()`), `serial`, identity, stored generated column, or a domain with constraints | `ACCESS EXCLUSIVE` | full rewrite of table and indexes | add the column nullable with no default, then `ALTER COLUMN ... SET DEFAULT` (applies to new rows only), then backfill in batches |
| `ADD COLUMN ... GENERATED ALWAYS AS (...)` virtual (18+, and the default kind in 18) | `ACCESS EXCLUSIVE`, brief | never rewrites | fine on 18+. On 12-17, generated columns must be `STORED` and trigger a rewrite |
| `ALTER COLUMN SET DEFAULT` / `DROP DEFAULT` | `ACCESS EXCLUSIVE`, brief | no; affects future inserts only | fine |
| `ALTER COLUMN SET NOT NULL` | `ACCESS EXCLUSIVE` | full scan, unless a valid constraint proves it | section 4.1 |
| `ALTER COLUMN DROP NOT NULL` | `ACCESS EXCLUSIVE`, brief | no | fine |
| `ADD CONSTRAINT ... CHECK` | `ACCESS EXCLUSIVE` | full scan | `NOT VALID`, then `VALIDATE CONSTRAINT` (section 4.2) |
| `ADD CONSTRAINT ... FOREIGN KEY` | `SHARE ROW EXCLUSIVE` on both tables | full scan of referencing table | `NOT VALID`, then `VALIDATE` (section 4.3) |
| `ADD UNIQUE` / `ADD PRIMARY KEY` | `ACCESS EXCLUSIVE` | index build under the lock | `CREATE UNIQUE INDEX CONCURRENTLY`, then `ADD CONSTRAINT ... USING INDEX` (section 4.4) |
| `ALTER COLUMN TYPE` | `ACCESS EXCLUSIVE` | rewrite plus index rebuild, unless binary-coercible | section 4.6 |
| `RENAME COLUMN` / `RENAME TO` | `ACCESS EXCLUSIVE`, brief | no | metadata-only, but breaks running code. Use expand/contract (`recipes.md`) |
| `DROP COLUMN` | `ACCESS EXCLUSIVE`, brief | no; space is reclaimed only as rows get rewritten | stop all use first (`recipes.md`). Dependent views block it unless you use `CASCADE`, and `CASCADE` drops them |
| `DROP TABLE`, `TRUNCATE` | `ACCESS EXCLUSIVE` | n/a | data-loss review |
| `CREATE TRIGGER` | `SHARE ROW EXCLUSIVE` | no | lock timeout |
| `ALTER TYPE ... ADD VALUE` (enum) | brief | no | the new value can't be used in the same transaction. Enum values can't be dropped (there is no `DROP VALUE`) |
| `VACUUM FULL`, `CLUSTER` (and plain `REPACK` on 19+) | `ACCESS EXCLUSIVE` | full rewrite | avoid online. On 19+, use `REPACK (CONCURRENTLY)` and read its caveats (section 9). On older versions, use the `pg_repack` extension if it's installed |
| `ATTACH PARTITION` | `SHARE UPDATE EXCLUSIVE` on parent, `ACCESS EXCLUSIVE` on the partition (and the default partition) | scans the partition unless a valid `CHECK` matching the bound exists | add a matching `CHECK ... NOT VALID`, `VALIDATE` it, then attach |
| `DETACH PARTITION` | `ACCESS EXCLUSIVE` on parent | no | `DETACH PARTITION ... CONCURRENTLY` (14+). It can't run in a transaction block and isn't allowed when the table has a default partition. If it's interrupted, the partition is left pending detach; finish with `ALTER TABLE ... DETACH PARTITION ... FINALIZE` |

## 4. Recipes

Run each numbered step as its own migration unless stated otherwise. Give steps that take a strong lock a short lock timeout. The concurrent and `VALIDATE` steps get the relaxed setting from section 2.

### 4.1 SET NOT NULL without a long exclusive lock

PostgreSQL 18+ (named not-null constraints can be `NOT VALID`):

```sql
ALTER TABLE users ADD CONSTRAINT users_email_not_null NOT NULL email NOT VALID;  -- brief lock; new writes checked
-- backfill/repair any NULLs (batched), then:
ALTER TABLE users VALIDATE CONSTRAINT users_email_not_null;                      -- scan under SHARE UPDATE EXCLUSIVE
```

PostgreSQL 12-17 (a validated CHECK lets `SET NOT NULL` skip its scan):

```sql
ALTER TABLE users ADD CONSTRAINT users_email_nn CHECK (email IS NOT NULL) NOT VALID;
ALTER TABLE users VALIDATE CONSTRAINT users_email_nn;      -- scan, but reads/writes continue
ALTER TABLE users ALTER COLUMN email SET NOT NULL;         -- brief: proven by the valid CHECK, no scan
ALTER TABLE users DROP CONSTRAINT users_email_nn;          -- now redundant
```

As soon as the `NOT VALID` constraint exists, any write that leaves the column null fails. Deploy the code that always writes the column before this step, not after.

### 4.2 CHECK constraint

```sql
ALTER TABLE orders ADD CONSTRAINT orders_total_nonneg CHECK (total_cents >= 0) NOT VALID;
-- repair violating rows, then:
ALTER TABLE orders VALIDATE CONSTRAINT orders_total_nonneg;
```

### 4.3 Foreign key

```sql
-- 1. index the referencing column first (own non-transactional migration);
--    parent-side DELETE/UPDATE otherwise seq-scans the child
CREATE INDEX CONCURRENTLY IF NOT EXISTS orders_customer_id_idx ON orders (customer_id);
-- 2. find orphans and decide what to do with them
SELECT count(*) FROM orders o LEFT JOIN customers c ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL AND c.id IS NULL;
-- 3. add without validating (brief SHARE ROW EXCLUSIVE on both tables)
ALTER TABLE orders ADD CONSTRAINT orders_customer_id_fkey
  FOREIGN KEY (customer_id) REFERENCES customers (id) NOT VALID;
-- 4. validate (SHARE UPDATE EXCLUSIVE on orders, ROW SHARE on customers)
ALTER TABLE orders VALIDATE CONSTRAINT orders_customer_id_fkey;
```

PostgreSQL 18 also accepts `NOT VALID` foreign keys on partitioned tables. It also adds `NOT ENFORCED` constraints, which are metadata only, never checked, and not a safety step.

### 4.4 UNIQUE constraint or new PRIMARY KEY

```sql
-- check for duplicates first; the build fails (leaving an INVALID index) if any exist
SELECT email, count(*) FROM users GROUP BY email HAVING count(*) > 1;

CREATE UNIQUE INDEX CONCURRENTLY users_email_key ON users (email);      -- own non-transactional migration
ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE USING INDEX users_email_key;  -- brief
```

For `PRIMARY KEY USING INDEX`, if the columns aren't already `NOT NULL`, PostgreSQL runs `SET NOT NULL` itself, with a full scan under `ACCESS EXCLUSIVE`. Do 4.1 first. The index must be a plain b-tree index with default sort order, not partial and not on expressions.

### 4.5 Indexes

- `CREATE INDEX CONCURRENTLY` can't run inside a transaction block. It makes two table scans. After the second, it waits for every transaction in the database whose snapshot is older, whatever table that transaction touches. So a long transaction anywhere makes it hang, even though it doesn't block traffic. Look for them first with the old-snapshot query in section 7.
- Those waits count against `lock_timeout`. Run the build with the relaxed timeout from section 2, or a short value cancels it.
- If it fails (a deadlock, a uniqueness violation, a cancel or timeout), it leaves an **INVALID** index behind. The planner ignores that index, but once it's past its first phase (`indisready` is true) every write still pays to maintain it. Drop it with `DROP INDEX CONCURRENTLY` and build again (section 6 has a re-runnable pattern). `REINDEX INDEX CONCURRENTLY` also rebuilds it, but not when the failure was duplicate data. Then it just fails the same way again.
- **A failed UNIQUE build can keep enforcing uniqueness.** The PostgreSQL docs say that if the build fails during its second scan, the invalid index goes on enforcing its uniqueness constraint. Production writes that create duplicates, old code's included, then get unique violations from an index no query uses. Drop it promptly, repair the duplicates, then rebuild.
- On a partitioned table, `CONCURRENTLY` isn't supported on the parent. Do this instead:

```sql
CREATE INDEX IF NOT EXISTS events_created_at_idx ON ONLY events (created_at);    -- parent only; starts INVALID
CREATE INDEX CONCURRENTLY events_2026_10_created_at_idx ON events_2026_10 (created_at);  -- per partition
ALTER INDEX events_created_at_idx ATTACH PARTITION events_2026_10_created_at_idx;
-- repeat per partition; the parent index becomes valid once every partition has one attached
```

- Watch progress in `pg_stat_progress_create_index` (12+).

### 4.6 Changing a column type

No rewrite is needed when the old type is binary-coercible to the new one and `USING` doesn't change the values. Examples:

- `varchar(n)` to `varchar(m)` with m > n, or to unconstrained `varchar`/`text`.
- `varchar` to `text` and back. Indexes aren't rebuilt either, as long as the collation doesn't change.
- `numeric(p,s)` to a larger precision with the same scale, or to unconstrained `numeric`.
- `timestamp` to `timestamptz` and back, on 12+, **only when the session `TimeZone` is `UTC`**. Run `SET TimeZone = 'UTC';` first, and only if the stored values really are UTC. Indexes on the column may still be rebuilt.

Expect a full rewrite plus index rebuild under `ACCESS EXCLUSIVE` for everything else. That includes `int` to `bigint`, `text` to `integer`, `timestamp` to `date`, any value-changing `USING`, and adding or shrinking a length limit. To cap a length without changing the type, use `CHECK (char_length(col) <= n) NOT VALID`, then `VALIDATE`. For real type changes on large tables, use the new-column recipe in `recipes.md`.

To confirm on a copy, compare `SELECT pg_relation_filenode('t');` before and after. A new filenode means the table was rewritten.

### 4.7 Renaming without breaking readers (short-lived shim)

A plain `RENAME` is instant, but every running instance of old code breaks at once. Expand/contract with dual writes is the default (`recipes.md`). For a table rename, one short-lived alternative is: `ALTER TABLE old_name RENAME TO new_name; CREATE VIEW old_name AS SELECT * FROM new_name;`. Run both in one transaction with a lock timeout. Simple single-table views are auto-updatable, so old code keeps working until it's gone. Then drop the view. A `SELECT *` view captures the column list at creation time. Some ORMs introspect differently for views, so test them.

## 5. Transactions and non-transactional statements

- DDL is transactional, so a failed migration rolls back cleanly. The flip side is that every lock is held until `COMMIT`. Keep each transaction to one lock-heavy statement, and never put a backfill after DDL in the same transaction.
- These can't run in a transaction block: `CREATE INDEX CONCURRENTLY`, `DROP INDEX CONCURRENTLY`, `REINDEX CONCURRENTLY`, `DETACH PARTITION ... CONCURRENTLY`, `VACUUM`, `CREATE DATABASE`. Put each in its own migration with the tool's transaction wrapper turned off.
- **Multi-statement trap:** when a client sends several statements as one simple-query string, which is how many tools run a `.sql` file, PostgreSQL runs them as a single implicit transaction. A `CONCURRENTLY` statement in that file then fails with "cannot run inside a transaction block". Keep it alone in its file.
- `ALTER TYPE ... ADD VALUE` can run inside a transaction (12+), but the new value can't be used until that transaction commits. Don't add the value and backfill it in the same migration.

## 6. Idempotency snippets

Native guards include `CREATE TABLE IF NOT EXISTS`, `CREATE [UNIQUE] INDEX [CONCURRENTLY] IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, `DROP COLUMN IF EXISTS`, `DROP INDEX [CONCURRENTLY] IF EXISTS`, `DROP CONSTRAINT IF EXISTS`, `ALTER TYPE ... ADD VALUE IF NOT EXISTS`. There's no `ADD CONSTRAINT IF NOT EXISTS` and no `CREATE TYPE IF NOT EXISTS`, so guard those with a catalog check:

```sql
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'orders_customer_id_fkey' AND conrelid = 'public.orders'::regclass
  ) THEN
    ALTER TABLE public.orders ADD CONSTRAINT orders_customer_id_fkey
      FOREIGN KEY (customer_id) REFERENCES public.customers (id) NOT VALID;
  END IF;
END $$;
```

`IF NOT EXISTS` on an index matches by name only, so it silently skips over the INVALID leftover of a failed concurrent build, and the tool records the migration as done. A re-runnable concurrent build has to check validity:

```sql
-- 1. Is there a leftover from an earlier attempt? (outside any transaction)
SELECT indisvalid, indisready FROM pg_index
WHERE indexrelid = to_regclass('public.orders_customer_id_idx');
-- 2. Only if a row came back with indisvalid = false:
DROP INDEX CONCURRENTLY IF EXISTS public.orders_customer_id_idx;
-- 3. Build, as its own non-transactional step, with lock_timeout relaxed (section 2)
CREATE INDEX CONCURRENTLY IF NOT EXISTS orders_customer_id_idx ON public.orders (customer_id);
-- 4. Verify, and fail the migration unless this returns true
SELECT indisvalid FROM pg_index WHERE indexrelid = 'public.orders_customer_id_idx'::regclass;
```

Put the branch in step 2 in the migration's host language, or use psql's `\gexec`. A `DO` block always runs inside a transaction, so it can't contain `CONCURRENTLY`.

To find every invalid leftover:

```sql
SELECT indexrelid::regclass AS index_name, indrelid::regclass AS table_name,
       indisready,   -- true: still maintained on every write
       indisunique   -- true and ready: may still be rejecting duplicates (section 4.5)
FROM pg_index WHERE NOT indisvalid;
```

`VALIDATE CONSTRAINT` is safe to re-run, because it does nothing when the constraint is already valid.

## 7. Measuring and monitoring

```sql
-- size and approximate rows
SELECT pg_size_pretty(pg_total_relation_size('public.orders')) AS total_size,
       (SELECT reltuples::bigint FROM pg_class WHERE oid = 'public.orders'::regclass) AS approx_rows;

-- who is blocking whom, and long transactions (run before and during a migration)
SELECT pid, pg_blocking_pids(pid) AS blocked_by, state, wait_event_type, wait_event,
       now() - xact_start AS xact_age, left(query, 80) AS query
FROM pg_stat_activity
WHERE datname = current_database()
  AND (cardinality(pg_blocking_pids(pid)) > 0 OR xact_start < now() - interval '1 minute')
ORDER BY xact_start;

-- what a concurrent index build will wait for: old transactions or snapshots
-- anywhere in this database, whatever table they touch
SELECT pid, now() - xact_start AS xact_age, state, backend_xmin, left(query, 80) AS query
FROM pg_stat_activity
WHERE datname = current_database() AND pid <> pg_backend_pid()
  AND backend_xmin IS NOT NULL AND xact_start < now() - interval '5 minutes'
ORDER BY xact_start;

-- is a table still used? sample twice, some hours apart, and compare
SELECT relname, seq_scan, idx_scan, n_tup_ins, n_tup_upd, n_tup_del
FROM pg_stat_user_tables WHERE relname = 'orders_legacy';

-- streaming replica lag
SELECT application_name, replay_lag FROM pg_stat_replication;
```

- Stop a runaway statement with `SELECT pg_cancel_backend(PID);`. If that doesn't work, use `pg_terminate_backend(PID)`.
- On a staging copy, turn on `log_lock_waits` and set a low `deadlock_timeout`, so lock waits during the rehearsal show up in the log.
- A rewrite or a large backfill produces WAL roughly the size of the data it touches. Check disk space and archive or replication throughput before you start.

## 8. Replication, poolers, prepared statements

- **Physical (streaming) replicas** replay everything, rewrites included. Long rewrites and large backfills show up as replay lag.
- **Strong locks replay on hot standbys too.** An `ACCESS EXCLUSIVE` lock taken on the primary is replayed on each standby. If standby queries are reading the table, replay waits for them for up to `max_standby_streaming_delay` (30 s by default) and then cancels them. While it waits, WAL replay stalls for the whole standby, and new standby queries on the table can queue behind the lock. The primary's `lock_timeout` gives no protection there. Check `pg_stat_activity` on each standby before strong-lock DDL, and watch replay lag during it.
- **A replica has the new schema only after it replays the migration.** Before you release code that reads the new shape from replicas, confirm it's there. Either check the catalog on each replica (`information_schema.columns`), or record `pg_current_wal_lsn()` on the primary right after the migration commits and wait until `pg_last_wal_replay_lsn()` on each replica has reached it.
- **Logical replication doesn't replicate DDL.** A subscriber table can have extra columns, but it can't be missing a column the publisher sends. So add columns on subscribers first, and drop them on the publisher first. Apply the schema change on both sides as separate, coordinated steps.
- **Transaction-mode poolers** (such as PgBouncer in transaction mode) don't keep session `SET`s or session advisory locks between transactions. Run migrations on a direct connection.
- **Prepared statements and `SELECT *`:** after a column is added or dropped, a cached plan for `SELECT *` on that table can fail with `cached plan must not change result type`. List columns explicitly, or make sure the driver re-prepares.

## 9. Version feature table

| Version | Change relevant to migrations |
|---|---|
| 10 | Sequences have a data type (`CREATE SEQUENCE ... AS`). A `serial` column's sequence is `AS integer`, so widening the column doesn't widen the sequence (`ALTER SEQUENCE ... AS bigint`). Identity columns |
| 11 | `ADD COLUMN` with a non-volatile default no longer rewrites. Procedures can `COMMIT` (useful for in-database batch loops) |
| 12 | `SET NOT NULL` skips the scan when a valid `CHECK` proves it. `REINDEX CONCURRENTLY`. `ALTER TYPE ... ADD VALUE` allowed inside transactions. `timestamp`/`timestamptz` change without rewrite when the session is in UTC. `ATTACH PARTITION` takes only `SHARE UPDATE EXCLUSIVE` on the parent. `pg_stat_progress_create_index` |
| 14 | `DETACH PARTITION ... CONCURRENTLY` |
| 17 | `transaction_timeout` |
| 18 | Not-null constraints are named catalog constraints and can be added `NOT VALID`, then validated. Virtual generated columns (the default kind; adding one never rewrites). `NOT VALID` foreign keys on partitioned tables. `NOT ENFORCED` for `CHECK` and foreign keys |
| 19 (release due late October 2026; check the final release notes) | `REPACK` replaces `VACUUM FULL` and `CLUSTER`. `REPACK (CONCURRENTLY)` rewrites a table online: `SHARE UPDATE EXCLUSIVE` while it copies, then `ACCESS EXCLUSIVE` only for the brief file swap. It needs a primary key or an index-based replica identity, and it can't run on unlogged or partitioned tables (do each partition) or inside a transaction block. It is **not MVCC-safe**: a transaction holding an older snapshot, such as a running `pg_dump`, sees the table as empty after the swap. So don't overlap it with dumps or long reads of that table |
