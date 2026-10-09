# Multi-deploy migration recipes

These are release-by-release playbooks for changes that would break running code if done in one step. "Release" means a separate production deploy that has been confirmed healthy before the next one ships. Engine-specific statements are in `postgresql.md` and `mysql.md`, and the backfill mechanics are in `backfills.md`.

Each recipe follows the same rule: **only start a step once the previous release, and any rollback target, no longer depends on what the step removes.**

## Contents

1. Add a required column
2. Rename a column
3. Change a column's type
4. Add a unique constraint
5. Add a foreign key
6. Drop a column
7. Drop a table
8. Add or remove an enum / status value
9. Move a column to another table, or split a table
10. Change what existing data means

## 1. Add a required column

**With a constant default (one step).** PostgreSQL 11+ and MySQL with `ALGORITHM=INSTANT` add `NOT NULL DEFAULT constant` without a rewrite. Old code's inserts get the default. Done.

**No sensible constant default (the value is derived per row):**

| Release | Migration | Code |
|---|---|---|
| A | add the column, nullable | write it on every insert/update; reads tolerate NULL |
| (job) | batched backfill of existing rows | |
| B | enforce NOT NULL. PG: the scan-free recipe (`postgresql.md` §4.1). MySQL: `MODIFY ... NOT NULL` after verifying zero NULLs. It's an in-place full rebuild, and replicas lag by its whole duration, so on large or replicated tables run it through an online tool (`mysql.md` §7). Restate the full column definition (`mysql.md` §4.1) | reads may now assume a value |

Don't enforce NOT NULL in release A. Instances still running the previous version insert without the column and would fail.

## 2. Rename a column

The example renames `customers.fullname` to `customers.display_name`.

| Release | Migration | Code |
|---|---|---|
| A | add `display_name` (nullable); optionally a sync trigger | write **both** columns (or rely on the trigger); read `fullname` |
| (job) | backfill `display_name` from `fullname` | |
| B | | read `display_name`; still write both |
| C | if `fullname` is NOT NULL with no default, give it a default first. PG: `SET DEFAULT` or `DROP NOT NULL`, both metadata-only. MySQL: `ALTER COLUMN fullname SET DEFAULT '', ALGORITHM=INSTANT` (making it `NULL` rebuilds the table) | stop writing `fullname`; remove it from the ORM mapping or ignore list |
| D | drop the trigger and its function **first**, then `fullname`. On PG, put both in one transaction. On MySQL they're two auto-committed statements, so keep that order: a trigger that names a dropped column makes every write to the table fail | |

A PostgreSQL sync trigger lets code that isn't release-aware (other services, scripts) keep working. Set a lock timeout, because `CREATE TRIGGER` takes `SHARE ROW EXCLUSIVE`:

```sql
CREATE OR REPLACE FUNCTION customers_sync_display_name() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    NEW.display_name := COALESCE(NEW.display_name, NEW.fullname);
    NEW.fullname     := COALESCE(NEW.fullname, NEW.display_name);
  ELSIF NEW.display_name IS DISTINCT FROM OLD.display_name THEN
    NEW.fullname := NEW.display_name;
  ELSIF NEW.fullname IS DISTINCT FROM OLD.fullname THEN
    NEW.display_name := NEW.fullname;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER customers_sync_display_name
  BEFORE INSERT OR UPDATE ON customers
  FOR EACH ROW EXECUTE FUNCTION customers_sync_display_name();
```

The same shape works in MySQL with `BEFORE INSERT` and `BEFORE UPDATE` triggers that use `NEW.` and `OLD.` (one trigger per event). Older gh-ost releases refuse to migrate a table that has triggers, so finish any gh-ost work on the table before you add them.

## 3. Change a column's type

First check whether the change is metadata-only on your engine (`postgresql.md` §4.6, `mysql.md` §4). If it is, it's a single step with a lock timeout.

Otherwise:

- **MySQL:** run the `MODIFY COLUMN` through gh-ost or pt-online-schema-change. They do the shadow copy for you. Restate the column's full definition, or its default, comment and charset are silently dropped (`mysql.md` §4.1). Then make sure the app tolerates the new type during the cut-over window.
- **PostgreSQL (e.g. an `int` primary key to `bigint`):** add a new column and swap it in. Keep it in sync with a **trigger**, not app dual-writes. The swap renames columns under running code, so no app version may ever refer to `col_new` by name.

| Step | Action |
|---|---|
| 1 | Inventory everything attached to `col`: its default and sequence (`pg_get_serial_sequence('t', 'col')`) or identity, every index and constraint on it, foreign keys in other tables that reference it (`pg_constraint` where `confrelid = 't'::regclass`), and views. For a `serial` column, run `ALTER SEQUENCE t_col_seq AS bigint` now. Since PostgreSQL 10 a `serial` sequence is created `AS integer` and stops at 2,147,483,647 however wide the column gets. The change is brief, metadata-only and safe to run early |
| 2 | Add `col_new bigint`, nullable, no default |
| 3 | A `BEFORE INSERT OR UPDATE` trigger sets `NEW.col_new := NEW.col` |
| 4 | Batched backfill `col_new = col` where they differ (`backfills.md`) |
| 5 | Make `col_new` NOT NULL with the scan-free recipe (`postgresql.md` §4.1). If you skip this, step 6's `PRIMARY KEY USING INDEX` runs a full-scan `SET NOT NULL` inside the swap. Build `CREATE UNIQUE INDEX CONCURRENTLY` on `col_new`, plus a concurrent copy of every other index that covers `col`. Widen each referencing child column first, with this same recipe on the child table |
| 6 | The swap: one short transaction with a lock timeout, in this order. **(a)** Drop the forward trigger, or replace it with a reverse trigger (`NEW.col_old := NEW.col`) if you want a real rollback window. The old trigger names `col_new`, which won't exist after the rename, so leaving it fails every insert and update with `record "new" has no field "col_new"`. **(b)** Drop each foreign key that references the old key. The old key's index backs them, so dropping the key fails without `CASCADE`, and `CASCADE` drops them silently. **(c)** Drop the old primary-key constraint, then `ALTER COLUMN col DROP DEFAULT, ALTER COLUMN col DROP NOT NULL`, so inserts that don't mention the old column still succeed. **(d)** Rename `col` to `col_old` and `col_new` to `col`. **(e)** Move the default and ownership: `ALTER COLUMN col SET DEFAULT nextval('t_col_seq')` and `ALTER SEQUENCE t_col_seq OWNED BY t.col`. Without the ownership move, dropping `col_old` later drops the sequence too. **(f)** `ADD CONSTRAINT t_pkey PRIMARY KEY USING INDEX t_col_new_key`. **(g)** Re-add each foreign key, and any `CHECK` that was on `col`, with `NOT VALID`. **(h)** Re-create views that select the column. A view follows the column it was built on, not its name, so it would keep reading `col_old` |
| 7 | `VALIDATE CONSTRAINT` each re-added constraint, each as its own step (`postgresql.md` §4.3) |
| 8 | After the rollback window: drop the reverse trigger and its function first, then `col_old`. Its old indexes go with it |

- **Identity instead of `serial`:** an identity column's sequence belongs to that column and can't be moved. Either convert it to a plain sequence default in an earlier release, or do this in step 6. Before (c), read the current value with `SELECT pg_sequence_last_value(pg_get_serial_sequence('t', 'col')::regclass)`, then run `ALTER COLUMN col DROP IDENTITY`, which also drops its sequence. In place of (e), after (d), run `ALTER COLUMN col ADD GENERATED BY DEFAULT AS IDENTITY (START WITH <that value plus a margin>)`. The new column must already be NOT NULL (step 5).
- **The rollback window is only real with the reverse trigger.** Without it, nothing keeps `col_old` current after the swap. Even with it, rollback to the `int` column works only until new values pass 2,147,483,647.
- Each child table's own swap re-points its foreign-key column the same way. The swap is invisible to code that uses the column by name, as long as every client handles the wider type, for example 64-bit IDs in JavaScript.

## 4. Add a unique constraint

1. Find duplicates (`GROUP BY col HAVING count(*) > 1`). Deciding which duplicate wins is a **product decision**, not a migration detail, so get it decided.
2. Ship code that prevents new duplicates (an upsert, or a check before insert) and handles the engine's unique-violation error. Otherwise the index build can fail late on a duplicate written concurrently.
3. Repair the existing duplicates (batched).
4. Build the index online: PG `CREATE UNIQUE INDEX CONCURRENTLY` then `ADD CONSTRAINT ... UNIQUE USING INDEX`; MySQL `ADD UNIQUE INDEX ..., ALGORITHM=INPLACE, LOCK=NONE`. On PG, if the build fails, drop the leftover index straight away: it can keep rejecting duplicate writes while queries ignore it (`postgresql.md` §4.5).

## 5. Add a foreign key

1. Index the referencing column online.
2. Count and resolve orphans. Whether to delete, null out or re-parent them is a data decision.
3. Ship code that never writes orphans and handles the FK-violation error.
4. PG: add the FK with `NOT VALID`, then `VALIDATE CONSTRAINT`. MySQL: in-place add needs `foreign_key_checks=0`, which skips validating existing rows, so step 2 is the only validation you get. Online tools have FK limitations (`mysql.md` §7).

## 6. Drop a column

| Release | Migration | Code |
|---|---|---|
| A | if the column is NOT NULL with no default, make inserts that omit it succeed. PG: `DROP NOT NULL` or `SET DEFAULT`, both metadata-only. MySQL: `ALTER COLUMN c SET DEFAULT <v>, ALGORITHM=INSTANT`; avoid `MODIFY ... NULL` on large tables, because it rebuilds the table | stop reading and writing it everywhere; tell the ORM to forget it (see below) |
| B (after rollback window) | drop the column. If a trigger names it, drop the trigger first | |

Releases A and B have to be separate. Tell the ORM to forget the column in release A, otherwise it keeps naming it in queries:

- Rails: `self.ignored_columns += ["col"]`, then drop the column in the next release.
- Django: remove the field from model state only, with `migrations.SeparateDatabaseAndState(state_operations=[migrations.RemoveField(...)], database_operations=[])`, then drop the column in a later migration.
- Other ORMs (Hibernate/JPA, EF Core, Prisma, SQLAlchemy, TypeORM): remove the field from the mapping in release A and ship the drop separately. Watch for generated SQL that lists every mapped column, and for `SELECT *` combined with cached prepared statements.

Also search beyond the app: SQL in other repos, views, functions, triggers, reports, ETL jobs, CDC consumers and search-index builders.

## 7. Drop a table

1. Stop all reads and writes in code. Ship it.
2. Prove nobody is using the table. Sample the access counters twice, some time apart (PG `pg_stat_user_tables`, MySQL `performance_schema.table_io_waits_summary_by_table`). Check the database logs and other repos.
3. Take an export or snapshot of the table and record where it is. Confirm it can be restored.
4. Optionally, revoke privileges or rename the table to something like `orders_legacy_retired` for a soak period. An unknown reader then fails loudly but recoverably, because renaming it back is instant.
5. Drop it after the soak period, with sign-off.

## 8. Add or remove an enum / status value

**Adding** (readers before writers):

1. Schema: add the value. In PG it's `ALTER TYPE ... ADD VALUE`, which can't be used in the same transaction. In MySQL `ENUM`, append it at the end so the change is instant.
2. Release: every reader (API serializers, clients, workers, reports) tolerates the new value.
3. Release: writers start producing it.

**Removing:**

1. Release: stop writing the value.
2. Backfill existing rows to the replacement value.
3. Release: readers stop handling it.
4. Schema. PG enums can't drop a value. You have to create a new type and run `ALTER COLUMN ... TYPE new_enum USING col::text::new_enum`, which rewrites the table. MySQL `ENUM` removal needs a table copy. On large tables, use an online tool, or accept that the value stays in the type definition unused.

For value sets that change often, a `text` column with a `CHECK` constraint, or a lookup table with a foreign key, is cheaper to evolve than a native enum. On PG, replace the `CHECK` with `NOT VALID` + `VALIDATE`. MySQL has no `NOT VALID` path: adding an enforced `CHECK` copies the table (`mysql.md` §4), so the lookup table is the cheaper choice there.

## 9. Move a column to another table, or split a table

This is the rename recipe across tables:

1. Create the new table (additive).
2. Dual-write in the app, or with a trigger in the database.
3. Batched backfill.
4. Switch reads, behind a flag if you have one, and compare old and new results for a while if you can.
5. Stop writing the old location.
6. Drop it after the rollback window.

Keep the old and new data consistent while both are live. Write both in the same transaction, or use an outbox. Don't do a best-effort second write.

## 10. Change what existing data means

Never reinterpret stored values in place: switching cents to dollars, local time to UTC, changing an encoding, or changing an ID format. Old code would read new-meaning data as old-meaning data, and the reverse. Add a new column with the new meaning (and a name that says so, such as `amount_cents` or `created_at_utc`), dual-write, backfill with the conversion, switch reads, then contract. Record the conversion rule and the cut-over time in the migration or an ADR.
