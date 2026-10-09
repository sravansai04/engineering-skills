# ORM-Generated Queries

ORMs make it easy to write code whose SQL you never see. Review the statements the ORM emits, not the method calls. This file covers how to see those statements, how to fix N+1 and over-fetching in common ORMs, and which raw-SQL escape hatches are safe.

API names are given for orientation. Confirm them against the version the project pins, which you can find in its lockfile (`requirements*.txt`, `poetry.lock`, `Gemfile.lock`, `pom.xml`/`build.gradle`, `*.csproj`, `package-lock.json`, `go.mod`, `mix.lock`, `composer.lock`).

## Contents

1. See the SQL and count it
2. Recognizing N+1
3. Eager-loading APIs
4. The opposite failure: cartesian explosion
5. Over-fetching and bulk work
6. Other ORM traps
7. Locking and transactions through the ORM
8. Raw SQL: safe and unsafe forms

---

## 1. See the SQL and count it

| ORM | Print the emitted SQL | Count queries in a test |
|---|---|---|
| Django | Set the `django.db.backends` logger to DEBUG (it logs only when `DEBUG=True`); `connection.queries`; `print(qs.query)` (parameters are not quoted properly, so don't paste it back as-is) | `self.assertNumQueries(n)`; pytest-django's `django_assert_num_queries` fixture |
| Rails ActiveRecord | Development log; `relation.to_sql`; `relation.explain` | Subscribe to `sql.active_record` via `ActiveSupport::Notifications`; the Bullet gem flags N+1 in development |
| SQLAlchemy | `create_engine(url, echo=True)`, or the `sqlalchemy.engine` logger at INFO | Listen for `before_cursor_execute` with `sqlalchemy.event.listen(engine, ...)` and count |
| Hibernate / JPA | Logger `org.hibernate.SQL` at DEBUG, bind values via `org.hibernate.orm.jdbc.bind` at TRACE (Hibernate 6); Spring Boot `spring.jpa.show-sql=true` | `hibernate.generate_statistics=true`, then `Statistics.getPrepareStatementCount()` |
| Entity Framework Core | `optionsBuilder.LogTo(Console.WriteLine)`; `query.ToQueryString()`; `EnableSensitiveDataLogging()` shows parameter values (development only) | A `DbCommandInterceptor` that counts |
| Prisma | `new PrismaClient({ log: ['query'] })` | `log: [{ emit: 'event', level: 'query' }]` plus `prisma.$on('query', ...)` |
| Sequelize | `logging: console.log` (add `benchmark: true` for timings) | Count in the `logging` callback |
| TypeORM | `logging: ["query"]` in the data source options; `queryBuilder.getSql()` | Custom logger that counts |
| GORM (Go) | `db.Debug()`, or the logger at `logger.Info` level; `db.ToSQL(...)` | Callback or custom logger |
| Ecto (Elixir) | Queries log at debug level in development; `Ecto.Adapters.SQL.to_sql(:all, Repo, query)` | Attach to the repo's telemetry query event |
| Laravel Eloquent | `DB::enableQueryLog()` then `DB::getQueryLog()`; `DB::listen(...)`; `$query->toSql()` | Count via `DB::listen` |

Run the code path once with logging on (one request, one job, one test) and record how many statements ran and which ones repeat. A query-count assertion in a test is the cheapest regression guard for N+1 problems; suggest one when you fix one.

## 2. Recognizing N+1

In the log, it looks like one query for the list followed by the same statement repeated with a different ID each time:

```
SELECT * FROM orders WHERE customer_id = 7 ORDER BY created_at DESC LIMIT 50
SELECT * FROM customers WHERE id = 7
SELECT * FROM order_items WHERE order_id = 9001
SELECT * FROM order_items WHERE order_id = 9002
... 48 more
```

Where it hides in code:

- Templates or serializers touching `order.items` or `order.customer.name` inside a loop.
- GraphQL resolvers that resolve a field per parent. Batch them with a DataLoader-style loader.
- Computed properties or methods that run a query and get called per row.
- Callbacks, signals, or lifecycle hooks that query per saved row during bulk operations.
- Permission checks evaluated per row.

Each query is fast, which is why it survives review. The cost is round trips × rows, and it grows with page size and data volume.

## 3. Eager-loading APIs

Two strategies: **join** (one query, with parent columns repeated per child row) and **separate query** (a second `WHERE parent_id IN (...)` or `= ANY(...)` query per relation). Use joins for to-one relations and separate queries for to-many relations, for the reason given in section 4.

| ORM | To-one (join) | To-many (separate query) | Make lazy loads fail loudly |
|---|---|---|---|
| Django | `select_related('customer')` | `prefetch_related('items')`; `Prefetch('items', queryset=...)` to filter or order the children | No built-in switch; rely on `assertNumQueries` |
| Rails | `eager_load(:customer)` (LEFT OUTER JOIN), or `includes` (chooses a strategy) | `preload(:items)`, or `includes(:items)` | `strict_loading` on a relation, model, or association (6.1+) |
| SQLAlchemy | `joinedload(Order.customer)` | `selectinload(Order.items)` | `raiseload('*')`, or `lazy="raise"` on the relationship |
| Hibernate / JPA | `JOIN FETCH` in JPQL; `@EntityGraph` (Spring Data) | `@BatchSize` or `hibernate.default_batch_fetch_size` (loads lazy collections in batches); `@Fetch(FetchMode.SUBSELECT)` | No built-in switch; assert statement counts |
| EF Core | `.Include(o => o.Customer)` | `.Include(o => o.Items)` with `.AsSplitQuery()` | Lazy loading is off unless proxies or `ILazyLoader` are configured, so unloaded navigations stay empty instead of querying |
| Prisma | `include: { customer: true }` | `include: { items: true }` | Relations are never lazy-loaded; they are absent unless included or selected |
| Sequelize | `include: [Customer]` | `include: [{ model: Item, separate: true }]` (hasMany) | n/a |
| TypeORM | `relations: { customer: true }`, or `leftJoinAndSelect` in the query builder | Same APIs; lazy relations are Promises, so `await` in a loop is the N+1 | n/a |
| GORM | `Joins("Customer")` | `Preload("Items")` | n/a |
| Ecto | `join` plus `preload: [customer: c]` | `preload: [:items]` or `Repo.preload(orders, :items)` | Never lazy-loads: an unloaded association is an `Ecto.Association.NotLoaded` struct |
| Laravel | `with('customer')` | `with('items')`; `load('items')` on an existing collection | `Model::preventLazyLoading()` (typically in non-production) |

After the fix, re-count the queries: 1 + (number of eager-loaded relations) is the target, independent of row count. Then check that the eager query uses an index on the child's foreign-key column.

## 4. The opposite failure: cartesian explosion

Eager-loading two or more **collections** through joins multiplies rows: 50 orders × 20 items × 5 payments is 5,000 wide rows to build 50 objects. This is the ORM version of join fan-out (correctness-traps.md, section 6). The ORM deduplicates the objects, so results look right while transfer and hydration cost explode.

- Load collections with separate queries: Django `prefetch_related`, Rails `preload`, SQLAlchemy `selectinload`, EF Core `AsSplitQuery()`, Sequelize `separate: true`.
- Hibernate refuses to join-fetch two `List` (bag) collections at once (`MultipleBagFetchException`). Don't "fix" that by switching to `Set`; fetch the second collection in its own query.
- **Pagination plus a collection join fetch.** `LIMIT` would cut through child rows, so Hibernate applies the limit in memory after loading everything, and logs a warning saying so. Page the parent IDs first, then fetch the children for those IDs.

## 5. Over-fetching and bulk work

**Fetch only what's used.**

| ORM | Select fewer columns | Skip change tracking for read-only work |
|---|---|---|
| Django | `only()`, `defer()`, `values()`, `values_list()` | n/a (no identity map) |
| Rails | `select(:id, :name)`, `pluck(:id)` | n/a |
| SQLAlchemy | `load_only(...)`, or select specific columns | Select columns instead of entities |
| JPA | DTO or interface projections | Read-only query hints / `@Transactional(readOnly = true)` |
| EF Core | `.Select(o => new { o.Id, o.Total })` | `.AsNoTracking()` |
| Prisma | `select: { id: true, total: true }` | n/a |

Loading a whole entity can pull large text, JSON, or blob columns and prevents index-only scans.

**Write in sets, not loops.** Loading N objects, changing a field, and saving each one is N round trips and N statements. Prefer one set-based statement:

- Django: `QuerySet.update()`, `bulk_create()`, `bulk_update()`
- Rails: `update_all`, `insert_all`, `upsert_all`
- SQLAlchemy: an `update()` statement, or `session.execute(insert(Model), [dicts])`
- JPA: a bulk JPQL `UPDATE`/`DELETE` (`@Modifying` in Spring Data)
- EF Core 7+: `ExecuteUpdate()` / `ExecuteDelete()`
- Laravel: `Model::where(...)->update([...])`, `upsert()`

Bulk statements usually **skip per-object callbacks, signals, validation, and auditing hooks**, and they bypass the ORM's in-memory state (the JPA persistence context, the EF change tracker). Check whether the code relied on any of that before switching, and call it out in the review.

**Stream large reads** instead of loading them into memory: Django `.iterator()`, Rails `find_each` / `in_batches`, SQLAlchemy `yield_per`, JPA query streaming with a fetch size.

## 6. Other ORM traps

- **Counting and existence.** Django `len(qs)` loads every row while `qs.count()` and `qs.exists()` don't. Rails `relation.length` loads, `count` always queries, `size` uses whichever is already loaded, and `exists?` is the cheapest "any?". The same distinctions exist in most ORMs.
- **Default ordering.** A model-level default order (Django `Meta.ordering`, Rails `default_scope { order(...) }`) adds `ORDER BY` to every list query, to `first`/`last`, to iteration and export loops, and to the queries behind prefetches and eager loads, often forcing a sort the caller didn't need and steering index choice. Current Django and Rails strip it from `count()` and `exists()` / `exists?`, so don't report those. Django releases before 4.0 could also leak `Meta.ordering` columns into `GROUP BY`, which changed aggregation results. Prefer no default order, and order explicitly where it matters.
- **Filters across to-many relations duplicate parents.** Django `Order.objects.filter(items__sku='X')` joins and returns an order once per matching item. The `.distinct()` that usually follows is the DISTINCT smell; prefer `Exists(...)` subqueries.
- **Type mismatches from the language.** Binding a decimal type against an integer column, or a string against a UUID or number column, can make the database cast the column and skip its index (correctness-traps.md, section 20).
- **Generated `IN` lists.** `filter(id__in=big_list)` and equivalents expand to one placeholder per element. See index-design.md, section 11, for array binds and chunking.
- **Query in a property.** A model property or method that runs a query looks like a field access in templates and serializers, which makes N+1 invisible in code review. Grep for them.

## 7. Locking and transactions through the ORM

| ORM | Transaction block | Row lock | Skip locked rows (queues) |
|---|---|---|---|
| Django | `with transaction.atomic():` | `select_for_update()` | `select_for_update(skip_locked=True)` |
| Rails | `Model.transaction do ... end` | `lock`, `with_lock` | `lock("FOR UPDATE SKIP LOCKED")` |
| SQLAlchemy | `with session.begin():` | `with_for_update()` | `with_for_update(skip_locked=True)` |
| JPA / Spring | `@Transactional` | `@Lock(LockModeType.PESSIMISTIC_WRITE)` | Hibernate maps a lock timeout of `-2` to SKIP LOCKED |
| EF Core | `BeginTransaction()` | Raw SQL (`FromSql`) with `FOR UPDATE` | Raw SQL |
| GORM | `db.Transaction(func(tx *gorm.DB) error { ... })` | `Clauses(clause.Locking{Strength: "UPDATE"})` | `clause.Locking{Strength: "UPDATE", Options: "SKIP LOCKED"}` |
| Laravel | `DB::transaction(fn () => ...)` | `lockForUpdate()` | `lock('for update skip locked')` |

Watch for:

- **A locking query that joins.** Without a table list, `FOR UPDATE` locks the matching rows of every joined table, so a claim query joined to a shared parent row (a queue, an account) makes every worker wait on, or skip past, that one row. Name the table to lock: Django `select_for_update(skip_locked=True, of=('self',))`, SQLAlchemy `with_for_update(skip_locked=True, of=Job)`, or raw `FOR UPDATE OF j SKIP LOCKED`. In PostgreSQL, locking the nullable side of an outer join is an error. See concurrency-and-safety.md, section 6.
- **A lock outside a transaction.** In autocommit mode, `SELECT ... FOR UPDATE` releases its lock immediately. Django raises an error for `select_for_update()` outside `atomic()`; most ORMs don't warn.
- **Spring `@Transactional` self-invocation.** Calling a `@Transactional` method from another method of the same class bypasses the proxy, so no transaction starts.
- **Request-wide transactions** (Django `ATOMIC_REQUESTS`, open-session-in-view patterns) keep transactions and connections open during template rendering and external calls. See concurrency-and-safety.md on long transactions.

## 8. Raw SQL: safe and unsafe forms

The ORM protects you only while values travel as parameters. Every escape hatch has a safe form and an unsafe form that look similar.

| Stack | Safe (parameterized) | Unsafe (string-built) |
|---|---|---|
| Django | `Model.objects.raw("... WHERE id = %s", [id])`; `cursor.execute(sql, params)` | `raw(f"... WHERE id = {id}")`; string-formatted values in `extra()` |
| Rails | `where("email = ?", email)`; `where(email: email)`; `find_by_sql(["... ?", v])` | `where("email = '#{email}'")`; passing request params into `order()` or `pluck()` as raw SQL |
| SQLAlchemy | `text("... WHERE id = :id")` with a parameter dict | f-strings or `%` formatting into `text()` |
| JDBC / JPA | `PreparedStatement` with `?`; JPQL `:name` parameters; `createNativeQuery(sql).setParameter(...)` | Concatenating into `createQuery` / `createNativeQuery` / `Statement.execute` |
| EF Core | `FromSql($"... {id}")` (EF Core 7+; the interpolation becomes parameters); `FromSqlRaw(sql, parameters)` with placeholders | `FromSqlRaw` given a concatenated or pre-interpolated string |
| Prisma | `` prisma.$queryRaw`... WHERE id = ${id}` `` (tagged template) | `$queryRawUnsafe` with concatenation |
| node-postgres / mysql2 / Knex | `query('... $1', [id])`; `execute('... ?', [id])`; `whereRaw('x = ?', [v])` | Template literals into the SQL string |
| Go `database/sql` | `db.QueryContext(ctx, "... $1", id)` (`?` for MySQL) | `fmt.Sprintf` into the query |
| Laravel | `DB::select('... ?', [$id])`; `whereRaw('x = ?', [$v])` | `whereRaw("x = $v")` |

Identifiers (column names for sorting, table names) cannot be parameters in any of these. Map user input through an allowlist; see concurrency-and-safety.md, section 1.
