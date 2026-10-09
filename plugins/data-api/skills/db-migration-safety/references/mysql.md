# MySQL migration reference

This covers InnoDB online DDL, metadata locks and online schema-change tools. The behavior below is from the MySQL 8.4 manual, with version notes where it changed. The current long-term-support lines are 8.4 and 9.7 (GA April 2026). 8.0 reached end of life in April 2026, so treat 8.0-only notes as legacy. MariaDB, Percona Server, Aurora and Vitess-based platforms share much of it but differ in details (MariaDB has its own `INSTANT` rules and supports `IF [NOT] EXISTS` on columns and indexes). If you're on one of those, check its docs. Start by running `SELECT VERSION();`.

## Contents

1. DDL is not transactional
2. ALGORITHM and LOCK: make the server refuse a slow plan
3. Metadata locks: the outage nobody expects
4. Operation matrix (InnoDB), and 4.1 `MODIFY`/`CHANGE` restate the whole column
5. INSTANT limits and version caveats
6. INPLACE caveats: replica lag, online log, disk
7. Online schema-change tools: gh-ost and pt-online-schema-change
8. Idempotency in MySQL
9. Monitoring and measurement

## 1. DDL is not transactional

- Every DDL statement commits any open transaction implicitly, before and after it runs. Since 8.0 each DDL statement is atomic on its own, but a migration made of several statements isn't. If statement 3 of 5 fails, statements 1 and 2 stay applied.
- If the migration tool wraps the file in `BEGIN`/`COMMIT`, that protects nothing. The tool may also fail to record the version after a partial apply, so the next run repeats statements 1 and 2 and fails.
- Consequences: keep **one DDL statement per migration** where possible, make each re-runnable (section 8), and keep data changes (`INSERT`/`UPDATE`) in separate migrations or jobs.

## 2. ALGORITHM and LOCK: make the server refuse a slow plan

| Algorithm | Meaning |
|---|---|
| `INSTANT` | Metadata-only change in the data dictionary. A brief exclusive metadata lock; data untouched |
| `INPLACE` | No row-by-row copy, but it may rebuild the table in place. Usually allows concurrent DML. A brief exclusive metadata lock at the start and end |
| `COPY` | Copies the table row by row into a new one. **Concurrent DML is blocked** for the duration |

If you leave `ALGORITHM` out, MySQL picks `INSTANT`, then falls back to `INPLACE`, then to `COPY`, without telling you. **State the algorithm you expect**, and the statement fails instead of quietly falling back:

```sql
ALTER TABLE orders ADD COLUMN fulfilled_at DATETIME NULL, ALGORITHM=INSTANT;
ALTER TABLE orders ADD INDEX idx_orders_customer (customer_id), ALGORITHM=INPLACE, LOCK=NONE;
```

- With `ALGORITHM=INSTANT`, only `LOCK=DEFAULT` is allowed, so leave out the `LOCK` clause.
- `LOCK=NONE` asks for concurrent reads and writes, and errors if they can't be allowed. `LOCK=SHARED` blocks writes. `LOCK=EXCLUSIVE` blocks everything.
- If the server rejects the clause, that's information. The change needs a table copy, so use an online schema-change tool on a large table (section 7).

## 3. Metadata locks: the outage nobody expects

Even `INSTANT` and `INPLACE` changes need an exclusive **metadata lock (MDL)** for a moment. Here's how that goes wrong:

1. Some session has an open transaction that touched `orders`. It might be a long report, or an app connection that started a transaction and never committed.
2. `ALTER TABLE orders ...` waits for the exclusive MDL (`Waiting for table metadata lock`).
3. While the `ALTER` waits, every new query on `orders` queues behind it. The table is down.

`lock_wait_timeout` (which covers metadata locks, not row locks) **defaults to 31536000 seconds, one year**. So always set it low for migrations, and retry on `ER_LOCK_WAIT_TIMEOUT` (error 1205):

```sql
SET SESSION lock_wait_timeout = 5;
```

`innodb_lock_wait_timeout` (50 seconds by default) is a different setting for InnoDB row locks. Changing it does nothing for MDL waits.

Before you run DDL, look for long or idle transactions:

```sql
SELECT trx_mysql_thread_id AS thread_id, trx_started,
       TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age_s, LEFT(trx_query, 80) AS query
FROM information_schema.INNODB_TRX ORDER BY trx_started;

SELECT * FROM sys.schema_table_lock_waits;          -- who is waiting on which metadata lock, and who holds it
```

## 4. Operation matrix (InnoDB)

| Operation | Best algorithm | Rebuilds table? | Concurrent DML | Notes |
|---|---|---|---|---|
| Add column | `INSTANT` | no | yes | 8.0.12+ for the last position, 8.0.29+ for any position (but avoid 8.0.29 itself, section 5). Row-version limit (section 5) |
| Drop column | `INSTANT` (8.0.29+, run a later patch release) | no | yes | Earlier versions: `INPLACE` with a rebuild |
| Rename column (same type and nullability) | `INSTANT` (8.0.28+) | no | yes | Breaks running code; use expand/contract. A column referenced by a foreign key from another table can only be renamed `INPLACE` |
| Set or drop column default | `INSTANT` | no | yes | |
| Add `VIRTUAL` generated column | `INSTANT` | no | yes | Non-partitioned tables only |
| Add `STORED` generated column | `COPY` | yes | **no** | Use an online tool on large tables |
| Extend `ENUM`/`SET` by appending members | `INSTANT` | no | yes | Only if the storage size doesn't change. Inserting in the middle or reordering needs `COPY` |
| Extend `VARCHAR` within the same length-byte bucket | `INPLACE` | no | yes | 0-255 bytes or 256+ bytes. Crossing 255 bytes needs `COPY`. Bytes = chars × charset max width, so with `utf8mb4` `VARCHAR(63)` to `VARCHAR(64)` crosses (252 to 256 bytes) |
| Shrink `VARCHAR`, or change a column's data type | `COPY` | yes | **no** | Online tool. Changing one column's charset or collation with `MODIFY` is a type change too: expect `COPY`, and state `ALGORITHM=INPLACE` to let the server tell you |
| Make column `NULL` | `INPLACE` | yes | yes | Full rebuild with substantial reorganization, and replicas lag by its whole duration (section 6). If the goal is only that inserts which omit the column succeed, `ALTER COLUMN ... SET DEFAULT` with `ALGORITHM=INSTANT` is usually enough. Otherwise use an online tool on large tables |
| Make column `NOT NULL` | `INPLACE` | yes | yes | Full rebuild, so use an online tool on large or replicated tables. Needs strict SQL mode. Fails if NULLs exist. In non-strict mode, NULLs can be silently converted to the type's implicit default, so check `@@sql_mode` and clean the data first |
| Add secondary index | `INPLACE`, `LOCK=NONE` | no | yes | Waits for open transactions at the end. Replicas lag (section 6) |
| Drop or rename index | `INPLACE` | no | yes | Metadata-only |
| Add `FULLTEXT` index | `INPLACE` | the first one may rebuild | **no** | Online tool on hot tables |
| Add `SPATIAL` index | `INPLACE`, `LOCK=SHARED` | no | **no** | |
| Add foreign key | `INPLACE` only with `foreign_key_checks=0`, otherwise `COPY` | no | yes (with checks off) | **With checks off, existing rows aren't validated.** Run the orphan query first |
| Drop foreign key | `INPLACE` | no | yes | |
| Add enforced `CHECK` constraint (8.0.16+) | `COPY` | yes | **no** (`LOCK=SHARED` at best) | There's no `NOT VALID` equivalent, so existing rows are checked by copying the table. Use an online tool on large tables. Adding it `NOT ENFORCED` skips the check, but switching it to `ENFORCED` later re-checks every existing row, so expect the same table copy then |
| Drop `CHECK` constraint | `INPLACE` | no | yes | Metadata-only |
| Add primary key | `INPLACE` | yes | yes | Rebuild; expensive on big tables |
| Change the table's default charset (`CHARACTER SET = x`) | `INPLACE` | yes, if the encoding differs | yes | Sets the default for columns added later; existing columns keep their charset |
| Convert existing data (`CONVERT TO CHARACTER SET x`) | `INPLACE` with `LOCK=SHARED`, or `COPY` | yes, if the encoding differs | **no** | Writes are blocked for the whole rebuild. The manual's table says concurrent DML isn't permitted, although its syntax example shows `LOCK=NONE`. Plan for blocked writes. On large or hot tables (a `utf8mb3` to `utf8mb4` move, say), use an online tool (section 7) |
| Rename table | `INSTANT` | no | yes | Breaks running code |
| `OPTIMIZE TABLE` | `INPLACE` (no clause allowed) | yes | yes | Not in-place for tables with `FULLTEXT` indexes |

Orphan check before adding a foreign key:

```sql
SELECT COUNT(*) FROM orders o LEFT JOIN customers c ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL AND c.id IS NULL;
```

### 4.1 `MODIFY` and `CHANGE` restate the whole column

`MODIFY COLUMN` and `CHANGE COLUMN` replace the column's entire definition. Any attribute you leave out is dropped, not carried over: `DEFAULT`, `COMMENT`, `CHARACTER SET` and `COLLATE` (the column falls back to the table default), `ON UPDATE CURRENT_TIMESTAMP`, `AUTO_INCREMENT`, `INVISIBLE`. Index membership is kept. A lost default on a `NOT NULL` column makes old code's inserts fail in strict mode, which is an outage. A changed charset or collation can turn the plan into a table copy, and it changes uniqueness and sort order.

- Copy the current definition from `SHOW CREATE TABLE` and change only the part you mean to change.
- Diff `SHOW CREATE TABLE` before and after on the rehearsal copy.
- To change only a default, use `ALTER COLUMN c SET DEFAULT ...` or `ALTER COLUMN c DROP DEFAULT` with `ALGORITHM=INSTANT`. It touches nothing else.

The same applies to the `--alter` string you hand to gh-ost or pt-online-schema-change.

## 5. INSTANT limits

- Each instant add or drop creates a new row version. A table allows at most **64 row versions (255 as of MySQL 9.1.0)**. After that the server returns `ERROR 4092 ... Maximum row versions reached`, and you need an `INPLACE`/`COPY` rebuild. A rebuild (`ALTER TABLE ... FORCE`, `OPTIMIZE TABLE`) resets the counter. To check:

```sql
SELECT NAME, TOTAL_ROW_VERSIONS FROM information_schema.INNODB_TABLES WHERE NAME = 'shop/orders';
```

- `INSTANT` isn't available for `ROW_FORMAT=COMPRESSED` tables, tables with a `FULLTEXT` index, temporary tables, or tables in the data-dictionary tablespace. It also can't be combined with non-instant clauses in the same statement.
- **Don't run instant column changes on 8.0.29.** That release was withdrawn because instantly added or dropped columns could be read back incorrectly. Use a later patch release.
- **Check your backup tooling.** Tables that carry instant row versions (`TOTAL_ROW_VERSIONS > 0`) have tripped up physical backup tools. Older Percona XtraBackup releases refused to back them up. Confirm your backup tool and version handle them, or clear the versions with a rebuild (`OPTIMIZE TABLE`, or an online tool with `--alter "ENGINE=InnoDB"`).

## 6. INPLACE caveats: replica lag, online log, disk

- **Replica lag.** An in-place DDL statement replicates as a single statement, and replicas start it only after it has finished on the source. A 40-minute index build on the source means about 40 more minutes of lag on every replica, and multithreaded replicas still treat DDL as a barrier. For big tables behind replicas that serve reads or failover, use an online tool. Those copy in small replicated chunks and throttle on lag.
- **Schema visibility.** Until a replica has applied the DDL, it still has the old schema. Code that reads the new column from replicas fails with unknown-column errors for the whole lag, even though the migration "finished" on the source. Before releasing that code, confirm the change on each replica, for example with `information_schema.COLUMNS`.
- **Online alter log.** Concurrent DML during an in-place rebuild is buffered in a temporary log capped by `innodb_online_alter_log_max_size`. If heavy writes overflow it, the DDL fails at the end and rolls back, after all that time.
- **Disk.** A table rebuild needs room for a second copy of the table plus sort files (in `innodb_tmpdir` or `tmpdir`).
- Every `INPLACE` operation still needs its exclusive MDL at the end, so the timeout and long-transaction checks in section 3 still apply.

## 7. Online schema-change tools

Reach for one when the change needs `COPY` or a rebuild on a large or hot table, or when replica lag from in-place DDL isn't acceptable. Both tools copy rows into a shadow table in chunks, keep it in sync, then swap names in a brief cut-over.

| | gh-ost | pt-online-schema-change |
|---|---|---|
| Sync mechanism | reads the binary log (no triggers) | triggers on the original table |
| Server requirements | MySQL 5.7+; row-based replication with `binlog_row_image=FULL` on the server it reads | privileges to create triggers on the table |
| Key requirement | a shared `PRIMARY KEY` or unique key with no NULLs | a `PRIMARY KEY` or unique index |
| Foreign keys | **not supported**; it bails out when it finds one | handled via `--alter-foreign-keys-method` (`auto`, `rebuild_constraints`, `drop_swap`, `none`); understand each before you use it |
| Existing triggers | historically unsupported; recent releases document `--include-triggers` (check your version) | `--preserve-triggers` |
| Default mode | no-op unless `--execute` | requires exactly one of `--dry-run` or `--execute` |
| Leftover artifacts | `_TABLE_gho` (ghost), `_TABLE_ghc` (changelog), `_TABLE_del` (old table) | `_TABLE_new`, `_TABLE_old`, triggers `pt_osc_DB_TABLE_ins/upd/del` |

gh-ost example. Do a no-op run first, then add `--execute`. The `--alter` string restates the whole column (section 4.1), so copy your own column's attributes from `SHOW CREATE TABLE`:

```bash
gh-ost \
  --host=replica-1.db.internal --user=migrator --ask-pass \
  --database=shop --table=orders \
  --alter="MODIFY COLUMN note VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'customer note'" \
  --chunk-size=1000 \
  --max-load=Threads_running=25 \
  --critical-load=Threads_running=1000 \
  --max-lag-millis=1500 \
  --throttle-control-replicas=replica-2.db.internal \
  --postpone-cut-over-flag-file=/tmp/ghost-orders.postpone \
  --exact-rowcount --verbose
# then re-run with --execute; delete the postpone file when you are ready to cut over
```

pt-online-schema-change example (same full column definition):

```bash
pt-online-schema-change \
  --alter "MODIFY COLUMN note VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'customer note'" \
  D=shop,t=orders,h=primary.db.internal,u=migrator --ask-pass \
  --chunk-time 0.5 --max-lag 1 \
  --max-load Threads_running=25 --critical-load Threads_running=50 \
  --dry-run
# then re-run with --execute instead of --dry-run
```

Operational notes:

- gh-ost connects to a replica by default. Connecting it straight to the primary needs `--allow-on-master`. Pausing: create the `--throttle-flag-file` (if configured) or use the interactive socket (`--serve-socket-file`). Aborting: create the `--panic-flag-file` (if configured).
- Budget disk for a full second copy of the table, plus binlog or trigger write amplification while it runs.
- Cut-over takes a brief lock and still waits for metadata locks. Schedule it off-peak, and use the postpone flag (gh-ost) so a person decides when it happens.
- After an aborted run, clean up the artifacts listed above before you retry. gh-ost's `--initially-drop-ghost-table` / `--initially-drop-old-table` exist for this. pt-osc tries to clean up its own triggers on failure; check that it did.
- If your hosting platform has its own online-DDL facility (for example, Vitess-based platforms), prefer it. It's integrated with that platform's replication and cut-over.

## 8. Idempotency in MySQL

MySQL supports `CREATE TABLE IF NOT EXISTS` and `DROP TABLE IF EXISTS`, but **not** `ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS` or `DROP COLUMN/INDEX IF EXISTS`. Those are MariaDB extensions. Guard with `information_schema` and a prepared statement:

```sql
SET @exists := (SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'orders'
                  AND COLUMN_NAME = 'fulfilled_at');
SET @ddl := IF(@exists = 0,
               'ALTER TABLE orders ADD COLUMN fulfilled_at DATETIME NULL, ALGORITHM=INSTANT',
               'DO 0');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
```

For indexes, use `information_schema.STATISTICS` (`INDEX_NAME`), and for constraints `information_schema.TABLE_CONSTRAINTS`. Always filter on `TABLE_SCHEMA = DATABASE()`, or a table with the same name in another schema gives a false match. You can do the same check in the migration tool's code instead. Because DDL auto-commits, the check and the `ALTER` aren't atomic, so make sure only one migration runner is active at a time.

## 9. Monitoring and measurement

```sql
-- size and approximate rows
SELECT TABLE_ROWS, ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024) AS size_mb
FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'orders';

-- statements stuck on metadata locks
SHOW FULL PROCESSLIST;          -- State: "Waiting for table metadata lock"

-- replica lag (run on each replica; MySQL 8.0.22+ naming)
SHOW REPLICA STATUS;            -- Seconds_Behind_Source

-- is a table still read or written? sample twice and compare
SELECT COUNT_READ, COUNT_WRITE FROM performance_schema.table_io_waits_summary_by_table
WHERE OBJECT_SCHEMA = DATABASE() AND OBJECT_NAME = 'orders_legacy';
```

- Stop a runaway statement with `KILL QUERY thread_id;`. Killing a long in-place `ALTER` rolls it back, which can take a while too.
- InnoDB `ALTER TABLE` progress shows up in `performance_schema.events_stages_current` once the `stage/innodb/alter%` instruments and the stage consumers are enabled.
- `TABLE_ROWS` is an estimate for InnoDB. Use it for sizing, never for verification.
