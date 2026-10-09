# Concurrency and Safety

Queries that are correct in a single-user test can corrupt data, deadlock, or stall the database when many copies run at once. This file covers parameterization, transactions and isolation, races, locking, queues, long transactions, and bulk writes. PostgreSQL first, MySQL (InnoDB) noted.

## Contents

1. Parameterization
2. Transaction boundaries
3. Isolation levels
4. Lost updates and check-then-act races
5. Lock ordering and deadlocks
6. Work queues with SKIP LOCKED
7. Long transactions and timeouts
8. Bulk writes in batches
9. Replicas and read-your-writes
10. Error codes worth handling

---

## 1. Parameterization

**Values are always bound parameters.** Concatenation, f-strings, template literals, `format`, and `sprintf` are injection vectors no matter how the value was "sanitized." This includes values read back from your own database (second-order injection) and values inside ORM raw-SQL helpers. See orm-patterns.md, section 8, for the safe and unsafe form in each stack.

**Identifiers and keywords cannot be bound.** Sort columns, sort direction, and table names must come from a fixed allowlist, never from user text:

```python
SORTABLE = {"created": "created_at", "total": "total", "customer": "customer_name"}
column = SORTABLE.get(params.get("sort"), "created_at")       # unknown input falls back to a default
direction = "DESC" if params.get("dir") == "desc" else "ASC"

sql = (f"SELECT id, total, created_at FROM orders WHERE account_id = %s "
       f"ORDER BY {column} {direction}, id {direction} LIMIT %s")   # only allowlisted text is interpolated
cursor.execute(sql, (account_id, page_size))                     # every value is still bound
```

**`LIKE` needs its own escaping.** The value is bound safely, but `%` and `_` inside it are still wildcards: a search for `100%` matches everything starting with `100`. Escape them, and declare the escape character explicitly. A character other than backslash avoids differences in string-literal handling between engines:

```python
def like_escape(term: str) -> str:
    return term.replace("!", "!!").replace("%", "!%").replace("_", "!_")

cursor.execute("SELECT id FROM products WHERE name LIKE %s ESCAPE '!'", (like_escape(term) + "%",))
```

**Dynamic SQL inside the database** follows the same rule. In PL/pgSQL, quote identifiers with `format('%I', ...)` and pass values with `USING`:

```sql
EXECUTE format('SELECT count(*) FROM %I WHERE status = $1', table_name)
  INTO n USING wanted_status;
```

In MySQL stored programs, use `PREPARE stmt FROM @sql; EXECUTE stmt USING @value;` with `?` placeholders.

**Defense in depth.** Have the application connect as a role that can't run DDL or read unrelated schemas. That limits the blast radius when a mistake slips through. For injection outside SQL, and for authorization review, use `review-suite:secure-code-review`.

## 2. Transaction boundaries

- **Statements that must succeed or fail together go in one transaction:** a debit and a credit, an order and its line items, a status change and its audit row. In autocommit mode, each statement commits on its own, and a crash between them leaves half the change.
- **Keep transactions short and database-only.** Read, compute, write, commit. HTTP calls, message publishing, file uploads, and email belong before or after the transaction, never inside it (section 7).
- **"Write to the database and publish an event" needs an outbox** when both must happen. Insert the event row in the same transaction as the business change, then publish it from a separate process after commit. Publishing inside the transaction can announce a change that later rolls back. Publishing after commit without an outbox can lose the event on a crash.
- **Retries repeat everything.** When a transaction is retried after a serialization failure or deadlock, the whole unit re-runs, reads included. Side effects outside the database must not be inside the retried block.

## 3. Isolation levels

| Level | PostgreSQL | MySQL InnoDB |
|---|---|---|
| READ UNCOMMITTED | Behaves as READ COMMITTED | Dirty reads possible; avoid |
| READ COMMITTED | **Default.** Each statement sees a fresh snapshot. An `UPDATE` that waits on a concurrently updated row re-checks its `WHERE` against the new version. | Each consistent read takes a fresh snapshot. Mostly record locks only, so less gap locking and fewer deadlocks than REPEATABLE READ. |
| REPEATABLE READ | One snapshot for the whole transaction, and no phantoms. Updating a row that another transaction changed since the snapshot fails with `40001`. | **Default.** Plain `SELECT`s read one snapshot, but locking reads, `UPDATE`, and `DELETE` act on the latest committed rows and take next-key (gap) locks on ranges they scan. No error on concurrent update, so lost updates are silent. |
| SERIALIZABLE | Serializable snapshot isolation: detects dangerous read/write patterns and aborts one transaction with `40001`. Requires retry logic. | Plain `SELECT`s become `FOR SHARE` locking reads when autocommit is off, which means more blocking and more deadlocks. |

What this means in review:

- **Know which engine and which level the code runs at.** Frameworks and connection pools can change the default; look for an isolation setting in the configuration.
- **Snapshot reads don't protect read-then-write logic.** At PostgreSQL READ COMMITTED and MySQL REPEATABLE READ alike, two transactions can both read "balance = 100," and both write a value computed from it.
- **Write skew** survives REPEATABLE READ in both engines. Example: two transactions each check "at least 2 doctors on call," and each takes a different doctor off call; both commit, leaving zero. Prevent it with SERIALIZABLE (PostgreSQL), by locking the rows the decision depends on (`SELECT ... FOR UPDATE`), or by materializing the constraint as a row that both transactions must update.
- **Any code running at PostgreSQL REPEATABLE READ or SERIALIZABLE needs a retry loop** around the whole transaction for `40001`, with backoff and a retry cap.

## 4. Lost updates and check-then-act races

Anti-pattern: read a value, decide in application code, write the result back.

```text
qty = SELECT qty FROM inventory WHERE sku = 'A'      -- both workers read 5
UPDATE inventory SET qty = (qty - 1 computed in app) -- both write 4; one sale is lost
```

Fixes, roughly in order of preference:

1. **One atomic statement** that both checks and changes:
   ```sql
   UPDATE inventory SET qty = qty - 1
   WHERE sku = $1 AND qty > 0
   RETURNING qty;          -- PostgreSQL; in MySQL check the affected-row count
   ```
   Zero rows affected means the check failed. In PostgreSQL READ COMMITTED, a concurrent updater waits and then re-evaluates `qty > 0` on the new row version, and an InnoDB `UPDATE` always acts on the latest committed row, so this is safe on both engines.
2. **A constraint plus an upsert** for "create if missing":
   ```sql
   INSERT INTO user_settings (user_id, theme) VALUES ($1, $2)
   ON CONFLICT (user_id) DO UPDATE SET theme = EXCLUDED.theme;       -- PostgreSQL
   ```
   MySQL: `INSERT ... ON DUPLICATE KEY UPDATE ...`. "SELECT, and INSERT if not found" races; the unique constraint is what makes this correct, and the upsert just handles the conflict.
3. **Pessimistic lock** when the decision needs several reads:
   ```sql
   BEGIN;
   SELECT balance FROM accounts WHERE id = $1 FOR UPDATE;   -- others wait here
   -- decide, then
   UPDATE accounts SET balance = $2 WHERE id = $1;
   COMMIT;
   ```
4. **Optimistic concurrency** for user edits that span requests: add a `version` column and write with `UPDATE ... SET ..., version = version + 1 WHERE id = $1 AND version = $2`. Zero rows means someone else changed it; reload and retry, or show a conflict.
5. **Application-level mutex** for work that isn't one row: PostgreSQL `pg_advisory_xact_lock(key)` (released at commit or rollback), MySQL `GET_LOCK(name, timeout)` / `RELEASE_LOCK(name)` (session-scoped, so release it explicitly).

## 5. Lock ordering and deadlocks

A deadlock needs two transactions that each hold a lock the other wants. The usual cause is the same rows locked in different orders:

```text
T1: UPDATE accounts ... WHERE id = 1;   T2: UPDATE accounts ... WHERE id = 2;
T1: UPDATE accounts ... WHERE id = 2;   T2: UPDATE accounts ... WHERE id = 1;   -- deadlock
```

- **Lock in a consistent order.** Sort keys before touching them (transfers lock the lower account ID first). For multi-row changes, take the locks explicitly in key order first:
  ```sql
  -- PostgreSQL; in MySQL use an IN list or a joined temporary table the same way
  SELECT id FROM accounts WHERE id = ANY($1::bigint[]) ORDER BY id FOR UPDATE;
  UPDATE accounts SET ... WHERE id = ANY($1::bigint[]);
  ```
  A bare multi-row `UPDATE` locks rows in whatever order the plan visits them, and two such statements with overlapping sets can deadlock.
- **Keep lock-holding transactions short,** so the window for crossing locks stays small.
- **Use the weakest lock that works.** In PostgreSQL, inserting a child row takes `FOR KEY SHARE` on the referenced parent. `SELECT ... FOR UPDATE` on that parent blocks those inserts, while `FOR NO KEY UPDATE` (enough when you won't change the key) doesn't.
- **MySQL gap locks.** At REPEATABLE READ, locking reads and updates on a range also lock the gaps between index entries, so concurrent inserts into the same range can deadlock. Use precise equality lookups on unique indexes, or READ COMMITTED where the application tolerates it.
- **Fail fast instead of queueing,** when waiting is pointless: `FOR UPDATE NOWAIT`, or `SET LOCAL lock_timeout = '2s'` in PostgreSQL.
- **Deadlocks will still happen occasionally; retry them.** Both engines abort one victim, which the caller should retry like a serialization failure. In MySQL, tell the two lock errors apart: a deadlock (1213) has already rolled back the whole transaction, but a lock wait timeout (1205) rolls back only the statement that waited unless `innodb_rollback_on_timeout` is on. After a 1205 the transaction is still open with its earlier statements applied, so either retry that statement or issue `ROLLBACK` and retry the whole unit; never catch the error and commit as though the work were complete. Diagnose with PostgreSQL's server log (with `log_lock_waits` on) or MySQL's `SHOW ENGINE INNODB STATUS` (section LATEST DETECTED DEADLOCK; `innodb_print_all_deadlocks` logs every one).

## 6. Work queues with SKIP LOCKED

`FOR UPDATE SKIP LOCKED` (PostgreSQL 9.5+, MySQL 8.0+) lets each worker claim rows that no other worker has locked, instead of every worker waiting on the same first row.

PostgreSQL, claiming in one statement:

```sql
WITH next_jobs AS (
  SELECT id FROM jobs
  WHERE status = 'queued' AND run_at <= now()
  ORDER BY run_at
  LIMIT 10
  FOR UPDATE SKIP LOCKED
)
UPDATE jobs j
SET status = 'running', locked_until = now() + interval '5 minutes', attempts = attempts + 1
FROM next_jobs
WHERE j.id = next_jobs.id
RETURNING j.id, j.payload;

-- Supporting index: only the rows workers look for
CREATE INDEX jobs_queued_run_at_idx ON jobs (run_at) WHERE status = 'queued';
```

MySQL: select the IDs with `... ORDER BY run_at LIMIT 10 FOR UPDATE SKIP LOCKED` inside a transaction, `UPDATE` those IDs, then commit. MySQL won't accept `LIMIT` in an `IN (subquery)`, so use two statements.

Review points:

- **Lock only the job rows.** Without a table list, `FOR UPDATE [SKIP LOCKED]` locks the matching rows of every table in the query. If the claim joins jobs to a shared row (its queue, its account), the first worker locks that row, and every other worker then skips all of its jobs (with SKIP LOCKED) or waits on it (without), so the queue runs one worker at a time. Name the table: `FOR UPDATE OF j SKIP LOCKED` in PostgreSQL and in MySQL 8.0+ (use the alias if the table has one), or Django's `select_for_update(skip_locked=True, of=('self',))`. In PostgreSQL, `FOR UPDATE` on the nullable side of an outer join is an error.
- **Claim, commit, then process.** Holding the claiming transaction open while doing the job ties up a connection and pins vacuum for the job's duration (section 7).
- **Plan for crashed workers.** A visibility timeout (`locked_until`) plus a sweeper that returns expired `running` jobs to `queued` gives at-least-once delivery, so handlers must be idempotent.
- **Cap attempts** and move poison jobs to a dead-letter state.
- **Remove or archive finished jobs.** A queue table that only grows makes every claim slower. In PostgreSQL, heavy update churn also creates dead rows that autovacuum must keep up with.
- **Use SKIP LOCKED only for queues.** It deliberately returns an inconsistent view, so never use it in reports or "does this exist?" checks.
- PostgreSQL `LISTEN`/`NOTIFY` can wake idle workers instead of tight polling loops.

## 7. Long transactions and timeouts

What a long-open transaction does:

- Holds every row lock it has taken, blocking writers and sometimes DDL, which then blocks everything queued behind the DDL.
- **PostgreSQL:** its snapshot or transaction ID stops vacuum from removing dead rows newer than it, across the whole database, so tables and indexes bloat. An `idle in transaction` session is the classic culprit. An orphaned prepared transaction (`PREPARE TRANSACTION` never committed) or a replication slot whose consumer has gone away holds the horizon back the same way, and survives restarts. On replicas with `hot_standby_feedback` on, long queries there hold back vacuum on the primary.
- **MySQL:** purge can't discard undo history the transaction might still need, so the history list grows and reads slow down.
- Holds a pooled connection, starving the pool.

Find them:

```sql
-- PostgreSQL: sessions holding back vacuum, oldest first.
-- backend_xid (a transaction that has written) and backend_xmin (an open snapshot) are what pin
-- the cleanup horizon. A READ COMMITTED session idle in a read-only transaction holds neither,
-- so sorting by xact_start alone can point at the wrong session.
SELECT pid, state, backend_xid, backend_xmin,
       greatest(age(backend_xid), age(backend_xmin)) AS horizon_age,
       now() - xact_start AS xact_age,
       wait_event_type, wait_event, left(query, 80) AS query
FROM pg_stat_activity
WHERE backend_xid IS NOT NULL OR backend_xmin IS NOT NULL OR xact_start IS NOT NULL
ORDER BY greatest(age(backend_xid), age(backend_xmin)) DESC NULLS LAST, xact_start
LIMIT 20;

-- Two horizon holders that never appear in pg_stat_activity:
SELECT gid, prepared, owner, age(transaction) AS xid_age FROM pg_prepared_xacts;    -- forgotten two-phase commits
SELECT slot_name, slot_type, active, xmin, catalog_xmin FROM pg_replication_slots;  -- stale or inactive slots

-- PostgreSQL: who is blocking whom
SELECT pid, pg_blocking_pids(pid) AS blocked_by, left(query, 80) AS query
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
```

```sql
-- MySQL
SELECT trx_id, trx_started, trx_state, trx_mysql_thread_id, left(trx_query, 80) AS query
FROM information_schema.INNODB_TRX
ORDER BY trx_started;

SELECT * FROM sys.innodb_lock_waits;
```

Set guardrails per application role or per transaction, not server-wide:

| Purpose | PostgreSQL | MySQL |
|---|---|---|
| Cap one statement's runtime | `statement_timeout` | `max_execution_time` (milliseconds, `SELECT` only) or the `MAX_EXECUTION_TIME` optimizer hint |
| Cap waiting for a lock | `lock_timeout` | `innodb_lock_wait_timeout` (seconds) |
| Kill sessions idle inside a transaction | `idle_in_transaction_session_timeout` (ends the session) | No direct equivalent; `wait_timeout` closes idle connections |
| Cap a whole transaction | `transaction_timeout` (PostgreSQL 17+, ends the session) | None built in |

Example: `ALTER ROLE app_web SET statement_timeout = '5s';`, or `SET LOCAL statement_timeout = '30s';` inside a known-heavy report transaction.

## 8. Bulk writes in batches

One statement that updates or deletes millions of rows holds its locks for the whole run, generates a burst of WAL or binlog that replicas must replay (replication lag), and on failure rolls back everything.

Process in bounded chunks, committing between them:

```sql
-- PostgreSQL: repeat until it affects 0 rows
DELETE FROM events
WHERE id IN (
  SELECT id FROM events
  WHERE created_at < now() - interval '90 days'
  ORDER BY id
  LIMIT 5000
);

-- MySQL: single-table DELETE/UPDATE accept ORDER BY and LIMIT directly
DELETE FROM events WHERE created_at < NOW() - INTERVAL 90 DAY ORDER BY id LIMIT 5000;
```

- For very large tables, walk the key range instead of re-scanning from the start: `WHERE id > :last_id AND id <= :last_id + 10000`, where `:last_id` is a bound parameter carried between batches.
- Pause briefly between batches if replicas lag. Make each batch idempotent so a crash can resume.
- Time-based retention on huge tables is often better served by partitioning and dropping old partitions. That is a schema decision for `data-api:db-migration-safety`.
- Prefer set-based statements (`INSERT ... SELECT`, `UPDATE ... FROM`, multi-row `VALUES`, upserts) to per-row statements from the application. A synchronous web request should not loop over thousands of rows; hand large jobs to a background worker that reports progress.

## 9. Replicas and read-your-writes

Reads routed to an asynchronous replica can miss a write the same user just made. Review any flow that writes and then immediately reads, such as "save and redirect to the detail page" or "create, then list." Route those reads to the primary, or make them wait until the replica has caught up to the write. Never base a check-then-act decision on a replica read.

## 10. Error codes worth handling

| Condition | PostgreSQL SQLSTATE | MySQL error |
|---|---|---|
| Serialization failure: retry the transaction | `40001` | No serializable-snapshot error; InnoDB lost updates are silent. MySQL's deadlock error also carries SQLSTATE `40001`, so a generic "retry on 40001" handler catches it |
| Deadlock: retry the transaction | `40P01` | `1213` (SQLSTATE `40001`); the whole transaction is already rolled back |
| Lock wait timeout / `NOWAIT` failure | `55P03` | `1205` (timeout): only the statement is rolled back unless `innodb_rollback_on_timeout` is on, and the transaction stays open; retry the statement, or `ROLLBACK` and retry the whole transaction (section 5). `3572` (`NOWAIT`) |
| Statement timeout | `57014` (query_canceled) | `3024` (`max_execution_time` exceeded) |
| Unique violation (an upsert or a friendly error may be needed) | `23505` | `1062` |

Handle these by code, not by matching message text. Messages vary by version and locale.
