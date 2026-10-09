# Backfills and bulk data changes

How to change many existing rows without long locks, replica lag, bloat or a job you can't stop. This covers `UPDATE` backfills, bulk `DELETE`/purges and data copies between tables.

## Contents

1. Design checklist
2. Choosing the batch key
3. SQL batch statements (PostgreSQL, MySQL)
4. Driver loop template (application code)
5. In-database loop (PostgreSQL procedure)
6. Throttling signals
7. Verification and cleanup
8. Bulk deletes

## 1. Design checklist

- [ ] **Separate from DDL.** The backfill runs as its own job or script, or a non-transactional migration step, after the expand release has shipped. That ordering means rows written during the backfill are already populated by the new code or the trigger.
- [ ] **Bounded batches.** Each batch is its own short transaction, about 0.1 to 2 seconds. Start around 1,000 to 5,000 rows, measure, and adjust.
- [ ] **Keyset pagination** on an indexed, unique, ordered key. Never `OFFSET`, which re-scans every skipped row and gets slower with each batch.
- [ ] **Idempotent predicate.** Only touch rows that still need the change, so re-runs and overlapping runs do nothing extra.
- [ ] **Checkpoint.** Persist the last processed key (in a progress table, a job record or a log line), so a restart resumes instead of starting over. The idempotent predicate makes a restart from zero correct, just slower.
- [ ] **Throttle.** Pause between batches. Back off when replica lag, lock waits or load rise.
- [ ] **Stoppable.** A kill switch (a flag, a file or a config value) is checked between batches. Stopping mid-run leaves consistent data.
- [ ] **Observable.** Log progress: the key reached, rows changed, batch duration and estimated time remaining.
- [ ] **Set-based.** One `UPDATE` per batch, never a loop that fetches rows into the app and updates them one by one.
- [ ] **Verification query** written before the run starts (section 7).

## 2. Choosing the batch key

- Use the primary key or another unique indexed column. Integer keys allow cheap range batches (`id > a AND id <= b`). Sparse ranges just give smaller batches, which is fine. UUID or other non-sequential keys work with keyset `ORDER BY id LIMIT n`.
- Don't batch on a non-unique column like `created_at` unless you add a tiebreaker (`(created_at, id) > (:ts, :id)`). Without one, ties can drop or repeat rows at the edges of a batch.
- If the predicate is selective (only a few rows need changing), a partial index or an index on the predicate column keeps each batch from scanning the whole key range. Build it concurrently first, and drop it afterwards.

## 3. SQL batch statements

`:name` and `?` below stand for your driver's parameter placeholders.

PostgreSQL. The CTE fixes the batch, the update changes only the rows that need it, and the outer `SELECT` returns the cursor for the next batch whether or not any rows changed:

```sql
WITH batch AS (
  SELECT id FROM customers
  WHERE id > :last_id
  ORDER BY id
  LIMIT :batch_size
), upd AS (
  UPDATE customers c
     SET display_name = c.fullname
    FROM batch b
   WHERE c.id = b.id
     AND c.display_name IS DISTINCT FROM c.fullname
)
SELECT max(id) AS next_last_id FROM batch;   -- NULL when there is nothing left
```

(PostgreSQL always runs a data-modifying CTE to completion, even if the main query doesn't read its output.)

MySQL, using a range on an integer primary key:

```sql
UPDATE customers
   SET display_name = fullname
 WHERE id > ? AND id <= ?                         -- [last_id, last_id + batch_size]
   AND NOT (display_name <=> fullname);           -- null-safe "is different"
```

Loop until `last_id` passes `SELECT MAX(id) FROM customers` (read once at the start; the expand release covers new rows). MySQL also accepts `UPDATE ... ORDER BY id LIMIT n`, but range predicates give predictable index-range locks. Under `REPEATABLE READ`, large ranges take next-key locks that can block concurrent inserts, which is one more reason to keep batches small.

## 4. Driver loop template (application code)

Here is the shape in Python with psycopg 3. The same structure works in any language and driver: one short transaction per batch, a checkpoint, a throttle and a kill switch.

```python
import os, time
import psycopg

BATCH_SIZE = 2_000
PAUSE_S = 0.1
MAX_REPLICA_LAG_S = 5.0
STOP_FILE = "/tmp/backfill_display_name.stop"   # touch this file to stop between batches

BATCH_SQL = """
WITH batch AS (
  SELECT id FROM customers WHERE id > %(last_id)s ORDER BY id LIMIT %(n)s
), upd AS (
  UPDATE customers c SET display_name = c.fullname
  FROM batch b WHERE c.id = b.id AND c.display_name IS DISTINCT FROM c.fullname
)
SELECT max(id) FROM batch
"""

def replica_lag_s(conn) -> float:
    row = conn.execute(
        "SELECT COALESCE(EXTRACT(EPOCH FROM max(replay_lag)), 0) FROM pg_stat_replication"
    ).fetchone()
    return float(row[0])

def run(dsn: str, start_after: int = 0) -> None:
    last_id = start_after
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SET lock_timeout = '2s'")
        conn.execute("SET statement_timeout = '30s'")
        while not os.path.exists(STOP_FILE):
            started = time.monotonic()
            with conn.transaction():                 # one short transaction per batch
                next_id = conn.execute(BATCH_SQL, {"last_id": last_id, "n": BATCH_SIZE}).fetchone()[0]
            if next_id is None:
                print("done", flush=True)
                return
            last_id = next_id
            print(f"checkpoint last_id={last_id} batch_s={time.monotonic() - started:.2f}", flush=True)
            while replica_lag_s(conn) > MAX_REPLICA_LAG_S:   # back off while replicas catch up
                time.sleep(5)
            time.sleep(PAUSE_S)
    print(f"stopped at last_id={last_id}; resume with start_after={last_id}", flush=True)
```

Before running it for real, adapt it:

- Checking `pg_stat_replication` needs a role with monitoring privileges, such as `pg_monitor`. On MySQL, read `Seconds_Behind_Source` from `SHOW REPLICA STATUS` on each replica instead.
- On a lock timeout, retry the batch a few times with backoff instead of crashing.
- Write the checkpoint somewhere durable if the job runs unattended.
- If the project has a job framework (a task queue, a "data migration" runner, a maintenance-script convention), use it for scheduling, retries and logging rather than a bare script.

## 5. In-database loop (PostgreSQL procedure)

PostgreSQL 11+ procedures can `COMMIT` between batches. That's handy when you only have SQL access. The catch is that it has no replica-lag check, and stopping it means canceling the `CALL`.

```sql
CREATE OR REPLACE PROCEDURE backfill_display_name(batch_size int DEFAULT 2000,
                                                  pause interval DEFAULT '100 milliseconds')
LANGUAGE plpgsql AS $$
DECLARE
  last_id bigint := 0;
  next_id bigint;
BEGIN
  LOOP
    WITH batch AS (
      SELECT id FROM customers WHERE id > last_id ORDER BY id LIMIT batch_size
    ), upd AS (
      UPDATE customers c SET display_name = c.fullname
      FROM batch b WHERE c.id = b.id AND c.display_name IS DISTINCT FROM c.fullname
    )
    SELECT max(id) INTO next_id FROM batch;
    EXIT WHEN next_id IS NULL;
    last_id := next_id;
    COMMIT;                                   -- releases row locks; lets vacuum make progress
    RAISE NOTICE 'checkpoint last_id=%', last_id;
    PERFORM pg_sleep_for(pause);
  END LOOP;
END $$;

CALL backfill_display_name();   -- must not be inside an explicit transaction, or COMMIT fails
```

`statement_timeout` applies to the whole `CALL`, so disable or raise it for this session.

## 6. Throttling signals

| Signal | PostgreSQL | MySQL |
|---|---|---|
| Replica lag | `pg_stat_replication.replay_lag` on the primary | `Seconds_Behind_Source` from `SHOW REPLICA STATUS` on each replica |
| Lock contention | `pg_stat_activity` rows with `wait_event_type = 'Lock'` | `sys.innodb_lock_waits`, `sys.schema_table_lock_waits` |
| Load | active sessions in `pg_stat_activity`, CPU/IO metrics | `Threads_running` (`SHOW GLOBAL STATUS LIKE 'Threads_running'`) |
| Bloat / vacuum (PG) | `n_dead_tup` in `pg_stat_user_tables`; autovacuum keeping up | n/a (watch the history list length in `SHOW ENGINE INNODB STATUS`) |

Backfills generate WAL or binlog roughly the size of the rows they rewrite. Check disk space, backup and archiving throughput, and any CDC consumer that has to process every change.

## 7. Verification and cleanup

Write the "remaining work" query before the run, and require it to return 0 before the contract phase:

```sql
SELECT count(*) FROM customers WHERE display_name IS DISTINCT FROM fullname;     -- PostgreSQL
SELECT COUNT(*) FROM customers WHERE NOT (display_name <=> fullname);            -- MySQL
```

- On a huge table, run it in key-range chunks or against a replica.
- Spot-check a random sample against the source of truth for transforms that are more than a copy.
- PostgreSQL: after a large backfill, run `ANALYZE table` so the planner sees the new distribution. Let autovacuum reclaim dead tuples, or run a plain `VACUUM` (not `VACUUM FULL`) if it's falling behind.
- Drop any temporary helper index or progress table once you're done.

## 8. Bulk deletes

The same rules apply: keyset batches that carry a cursor, short transactions and a throttle. Don't restart every batch from the low end of the key (`WHERE created_at < :cutoff ORDER BY id LIMIT n` alone). Each restart has to walk past the dead tuples (PostgreSQL) or delete-marked records waiting for purge (InnoDB) that earlier batches left, so batches get slower as the purge goes on.

Find the upper bound once, up front: `SELECT max(id) FROM events WHERE created_at < :cutoff`. An index on `created_at` makes that cheap. On append-only tables, where `id` and `created_at` grow together, the bound keeps each batch to a short range scan.

```sql
-- PostgreSQL: carry the cursor, as in section 3
WITH batch AS (
  SELECT id FROM events
  WHERE id > :last_id AND id <= :max_id AND created_at < :cutoff
  ORDER BY id
  LIMIT :n
), del AS (
  DELETE FROM events e USING batch b WHERE e.id = b.id
)
SELECT max(id) AS next_last_id FROM batch;      -- NULL when nothing is left

-- MySQL: range on the integer key; loop until last_id passes max_id
DELETE FROM events
 WHERE id > ? AND id <= ?                        -- [last_id, last_id + batch_size]
   AND created_at < ?;
```

- For time-partitioned tables, dropping or detaching a whole old partition is far cheaper than deleting rows (PG: `DETACH PARTITION ... CONCURRENTLY` then `DROP`; MySQL: `ALTER TABLE ... DROP PARTITION`).
- On MySQL, Percona Toolkit's `pt-archiver` does throttled batch purges or archiving if it's already part of your tooling.
- A purge is destructive. Do the data-loss review (export or backup, retention rules, sign-off) before the first batch.
