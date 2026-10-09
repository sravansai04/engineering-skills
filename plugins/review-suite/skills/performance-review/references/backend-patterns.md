# Backend Performance Patterns

Red flags, fixes, and short multi-stack examples for each backend checklist category in SKILL.md. Jump to the section you need. The examples show shape, not complete programs.

## Contents

1. [I/O in loops and N+1](#1-io-in-loops-and-n1)
2. [Unbounded work](#2-unbounded-work)
3. [Query shape and indexes (surface level)](#3-query-shape-and-indexes-surface-level)
4. [Algorithmic complexity](#4-algorithmic-complexity)
5. [Memory](#5-memory)
6. [Caching](#6-caching)
7. [Work in the request path](#7-work-in-the-request-path)
8. [Network calls](#8-network-calls)
9. [Concurrency and resource pools](#9-concurrency-and-resource-pools)

**Traps in common fixes.** Check a proposed fix against these before recommending it, because each one swaps one incident for another:

- A cache in front of an N+1 or a full scan (§6, "Cache masking a bad access pattern").
- Replacing a sequential loop with unbounded parallelism (§8 Chattiness, §9 Pool exhaustion).
- A background job that isn't enqueued after commit, idempotent, or chunked (§7).
- Retries at every layer, or retries on non-idempotent calls (§8 Retries).
- An index added without counting its write cost (§3).
- Paginating a collection fetch join on older Hibernate versions (§1 Gotchas).
- A transaction split around I/O with no recovery path (§9).
- A keyset predicate whose `OR` isn't parenthesized (§2).

---

## 1. I/O in loops and N+1

**Red flags**
- A database query, ORM relation access, cache get, HTTP call, or file read inside `for`, `while`, `map`, a comprehension, or a recursive function.
- Hidden loops that issue a lazy load once per row: serializers or DTO mappers, template loops, GraphQL field resolvers, computed properties or getters, `toJSON`/`__str__`, per-item event handlers or validators.
- Per-item `exists()`, `count()`, `save()`, `update()`, or `delete()` calls.
- A cache N+1: one `GET` per item is still N network round trips.
- Sequential `await` inside a loop over independent items.

**Why it hurts.** Cost is N round trips. Each one pays network latency plus server work. At N = 1,000 and about 1 ms per round trip that is a full second, and the database sees 1,000 times the query volume.

**Fixes**
- Fetch in one query: collect the ids, issue one `WHERE id IN (...)` (or `= ANY($1)` with an array bind), build a map, and look items up in the loop.
- Use the ORM's eager or batch loading:

| Stack | Eager / batch load | Make lazy loads fail loudly |
|---|---|---|
| Django | `select_related` (FK, JOIN), `prefetch_related` / `Prefetch` (collections, second query), or `.fetch_mode(models.FETCH_PEERS)` (6.1+), which batches a per-row FK access into one second query | `.fetch_mode(models.FETCH_RAISE)` (6.1+) raises `FieldFetchBlocked`. It covers ForeignKey, OneToOne (including reverse), deferred fields, and generic relations, but not reverse-FK or many-to-many managers, so keep query-count tests for those. Before 6.1, use query-count tests or a package such as django-seal or nplusone |
| Rails | `includes`, `preload`, `eager_load` | `strict_loading` |
| SQLAlchemy | `selectinload`, `joinedload` | `raiseload` |
| JPA / Hibernate | `JOIN FETCH`, `@EntityGraph`, `@BatchSize` | Hibernate statistics in tests |
| EF Core | `Include` / `ThenInclude`, `AsSplitQuery()` for multiple collections | lazy loading is opt-in (`UseLazyLoadingProxies` or `ILazyLoader`), so check whether it was turned on |
| Laravel Eloquent | `with()` | `Model::preventLazyLoading()` |
| Prisma | `include`, or `findMany({ where: { id: { in: ids } } })` | n/a |
| GraphQL (any) | a DataLoader-style batcher created per request | n/a |

- Bulk writes: Django `bulk_create`/`bulk_update`, Rails `insert_all`/`upsert_all`, EF Core `ExecuteUpdate`/`ExecuteDelete`, Laravel `insert`/`upsert`, Prisma `createMany`, multi-row `INSERT ... VALUES`, `INSERT ... SELECT`, `UPDATE ... FROM`, or `COPY`. With Hibernate, JDBC batching needs `hibernate.jdbc.batch_size` (plus `hibernate.order_inserts` / `hibernate.order_updates` when several entity types are written), and inserts don't batch at all when ids come from `IDENTITY` columns. The driver matters too: MySQL Connector/J still sends one statement per row unless the URL sets `rewriteBatchedStatements=true`, and PgJDBC rewrites batched inserts into multi-row form only with `reWriteBatchedInserts=true`.
- Batch cache reads with `MGET` or the client's multi-get.

**Gotchas**
- JOIN-based eager loading of more than one collection multiplies rows (a cartesian product). Prefer separate-query loading (`prefetch_related`, `selectinload`, `preload`, `AsSplitQuery`) for collections.
- A prefetched relation is only used if the code reads it the prefetched way. In Django, `obj.items.filter(...)` after `prefetch_related("items")` issues a fresh query.
- Don't paginate a collection fetch join on Hibernate versions before 7.4. They can't put `LIMIT` in the SQL, so they load every matching row and paginate in memory, logging only a warning ("firstResult/maxResults specified with collection fetch; applying in memory"). The N+1 fix becomes an unbounded-memory problem. Page the parent ids first, then fetch their collections with `JOIN FETCH ... WHERE id IN (:ids)` or `@BatchSize`, and set `hibernate.query.fail_on_pagination_over_collection_fetch=true` so the mistake fails loudly. Hibernate 7.4 and later push the limit into a SQL subquery instead.
- Very large `IN` lists hit bind-parameter caps (SQL Server: 2,100 per statement, PostgreSQL and MySQL: 65,535) and bloat the query text. Bind one array parameter where the driver supports it, or chunk.
- A DataLoader shared across requests is a cache with no invalidation, and can leak data between users. Create one per request.

```python
# Before: 1 + N queries
for order in Order.objects.filter(status="open"):
    send(order.customer.email)          # lazy load per order

# After: 1 query
for order in Order.objects.filter(status="open").select_related("customer"):
    send(order.customer.email)
```

```ts
// Before: N sequential round trips
const users = [];
for (const id of ids) users.push(await db.user.findUnique({ where: { id } }));

// After: 1 round trip, then O(1) lookups
const rows = await db.user.findMany({ where: { id: { in: ids } } });
const byId = new Map(rows.map((u) => [u.id, u]));
```

```java
// Before: N+1 through a lazy collection
List<Invoice> invoices = repo.findByStatus(OPEN);
for (Invoice i : invoices) lineCount += i.getLines().size();   // one query per invoice

// After: fetch join (or @EntityGraph on the repository method)
@Query("select distinct i from Invoice i join fetch i.lines where i.status = :s")
List<Invoice> findWithLines(@Param("s") Status s);
```

---

## 2. Unbounded work

**Red flags**
- `findAll()`, `.all()`, `fetchall()`, or a `SELECT` with no `LIMIT` in a request path, against a table that grows.
- List endpoints with no pagination, or a client-supplied `limit` with no server-side maximum.
- `OFFSET` pagination on large tables. The cost grows with the offset because skipped rows are still read, and pages shift when rows are inserted between requests.
- Synchronous "export all" or "select all" operations, or a fan-out to every user or account inside one request or one transaction.
- Loop bounds, recursion depth, or allocation sizes taken from user input or untrusted data.
- Unbounded queues and pools. Java's `Executors.newFixedThreadPool` uses an unbounded work queue, `newCachedThreadPool` creates threads without limit, and `newVirtualThreadPerTaskExecutor` (Java 21+) starts one virtual thread per task, so nothing but the downstream pool limits it. Python's `queue.Queue()` and `asyncio.Queue()` default to unbounded. Spawning one goroutine or task per input item has no limit.
- `COUNT(*)` over a large table on every page load just to show "page 1 of N".

**Fixes**
- Enforce a server-side maximum page size, and reject or clamp anything larger.
- Use keyset (seek) pagination for large or deep lists:

```sql
-- Needs an index on (status, created_at, id)
SELECT id, created_at, title
FROM posts
WHERE status = :status
  AND (created_at, id) < (:last_created_at, :last_id)   -- row-value form; not supported everywhere
ORDER BY created_at DESC, id DESC
LIMIT 50;

-- Portable expansion of the same predicate. The parentheses around the OR are required.
WHERE status = :status
  AND (created_at < :last_created_at
       OR (created_at = :last_created_at AND id < :last_id))
```

Always parenthesize the `OR`. Without the parentheses, `AND` binds first, so the second branch ignores the other filters and the page picks up rows from other statuses, or other accounts, which is a data-exposure bug as well as a wrong result. The row-value form only works when every `ORDER BY` key sorts in the same direction. Mixed directions need the expanded form, with the comparison flipped for each key that sorts the other way.

- Replace exact totals with a "has more" flag (fetch `limit + 1` rows), or use an estimate where exactness doesn't matter.
- Process large sets in bounded chunks keyed by id, and move exports and fan-outs to background jobs (section 7).
- Bound every queue and pool, and decide what happens when it's full (block, shed load, or reject).

---

## 3. Query shape and indexes (surface level)

Flag these as suspicions. Leave plan reading and index design to `data-api:query-review`.

**Red flags**
- New `WHERE`, `JOIN`, or `ORDER BY` columns on a large table with no matching index in the schema or the migration.
- An indexed column wrapped in a function or cast: `WHERE lower(email) = ?`, `WHERE date(created_at) = ?`, or comparing a column to a parameter of a different type. Use an expression index, normalize on write, or turn the predicate into a range (`created_at >= :day AND created_at < :next_day`).
- Leading-wildcard search (`LIKE '%term'`). A plain B-tree index can't serve it.
- `ORDER BY ... LIMIT` that no index can satisfy, which sorts the whole filtered set to return 20 rows.
- `SELECT *` pulling wide or large columns (blobs, big JSON, text) that the code never reads.
- A new index on a write-heavy table, or one that duplicates an existing index's leading columns. Every index costs write throughput and storage.

---

## 4. Algorithmic complexity

Flag these only when n can actually be large. Quadratic over 20 items is fine. State the n.

| Pattern | Cost | Fix |
|---|---|---|
| `x in list`, `list.includes(x)`, `list.contains(x)` inside a loop | O(n·m) | Build a `Set` or dict once, outside the loop |
| Nested loops to match two collections by key | O(n·m) | Index one side in a hash map by key, then do one pass |
| `find` / `filter` inside `map` | O(n·m) | Same as above |
| JS `reduce` returning `{...acc, [k]: v}` or `[...acc, x]` | O(n²) copies | Mutate a local accumulator, or use `Object.fromEntries` / `Map` |
| Removing from the front in a loop: JS `shift()`, Python `list.pop(0)`, Java `ArrayList.remove(0)` | O(n) each | Deque (`collections.deque`, `ArrayDeque`) or an index pointer |
| Java, C#, or Go string `+=` in a loop that can run thousands of times | O(n²) copying | `StringBuilder`, `strings.Builder`, or `join`. JS engines (rope strings) and CPython (in-place append) usually make `+=` linear, so flag it there only with a profile |
| Sorting inside a loop, or sorting to get the min, max, or top-k | O(n log n) per iteration | One pass, a heap, or sort once outside the loop |
| Recomputing a loop-invariant value per iteration (parsing config, compiling a regex, building a formatter or client, deep-cloning) | repeated constant work × n | Hoist it out of the loop |
| Recursion over overlapping subproblems with no memoization | exponential | Memoize, or use iterative dynamic programming |
| Nested quantifiers in a regex applied to untrusted input, e.g. `(a+)+$` | exponential backtracking | Rewrite the pattern, use a linear-time engine, or bound the input length. Also send it to `review-suite:secure-code-review` |

```js
// Before: O(n*m); each find scans all users
const rows = orders.map((o) => ({ ...o, user: users.find((u) => u.id === o.userId) }));

// After: O(n + m)
const usersById = new Map(users.map((u) => [u.id, u]));
const rows = orders.map((o) => ({ ...o, user: usersById.get(o.userId) }));
```

---

## 5. Memory

**Red flags: whole-payload loads**
- Reading an entire file or body: Python `f.read()` or `json.load` on large files, `cursor.fetchall()`; Node `fs.readFile`/`readFileSync`, `await res.json()` on large responses; Java `Files.readAllBytes`/`readAllLines`; Go `io.ReadAll`; .NET `File.ReadAllBytes`/`ReadAllText`.
- Materializing a large ORM result set into a list.
- Building a full export (CSV, JSON, PDF) as one string or buffer before sending it.
- Several full copies alive at once (raw bytes, decoded text, parsed objects, transformed objects). Base64 adds about 33% on top.

**Streaming fixes**

| Need | Option |
|---|---|
| Large file or HTTP body | Python: iterate the file object; `requests.get(url, stream=True)` with `iter_content`. Node: `fs.createReadStream` with `pipeline` from `node:stream/promises`. Java: `Files.lines` or `InputStream.transferTo` inside try-with-resources. Go: `io.Copy`, `bufio.Scanner` (its default 64 KiB token limit fails on long lines, so raise it with `Scanner.Buffer`). .NET: `Stream.CopyToAsync` |
| Large JSON | Go `json.Decoder` with `Token()`; .NET `JsonSerializer.DeserializeAsyncEnumerable`; Python `ijson`; NDJSON instead of one giant array |
| Large DB result | Django `.iterator(chunk_size=...)`; Rails `find_each` / `in_batches`; SQLAlchemy `yield_per`; Laravel `lazyById` / `chunkById`; psycopg named (server-side) cursors; PgJDBC `setFetchSize`, which only streams with autocommit off and a forward-only result set |
| Large export | Stream rows to the response or to object storage as they're produced, or generate it in a background job (section 7) |

**Red flags: growth in long-lived processes** (servers, workers, daemons, single-page apps)
- Module-level or static maps and lists that are only ever added to (an "in-memory cache" with no eviction).
- Event listeners or subscriptions registered per request and never removed. Node's `MaxListenersExceededWarning` is a common symptom.
- Timers and intervals that are never cleared, and closures capturing large objects that outlive the request.
- Goroutines or tasks blocked forever on a channel or future with no cancellation. Pass a context or cancellation token and make sure every exit path releases them.
- Request-scoped data stored on a singleton or a thread-local that is never cleared, especially with pooled threads.
- Python `functools.lru_cache` on instance methods keeps every `self` alive until it is evicted. `functools.cache` is unbounded.
- Small views retaining big parents: a Go subslice or substring keeps the whole backing array alive. Copy it (`strings.Clone`, `copy` into a new slice) when you keep a small piece of something large.

**Allocation churn.** High allocation rates on hot paths cause GC pressure. Report this only with a profile showing allocation or GC time. It is a classic micro-optimization trap otherwise.

---

## 6. Caching

**Correctness first**
- The key must include every input that changes the value: user or role, permissions, account or organization, locale, feature flags, API version, query parameters. A missing dimension serves one user's data to another, which is a data leak, so also flag it for `review-suite:secure-code-review`.
- Invalidation: list every write that makes an entry stale, and confirm each one invalidates or updates it. A TTL is the backstop, not the plan. Decide whether a user must see their own write immediately (read-your-writes).
- Don't hand out mutable cached objects by reference. A caller that mutates one corrupts it for everyone.

**Load behavior**
- **Stampede.** When a hot key expires, many concurrent requests recompute it at once and hit the backing store together. Mitigations: coalesce requests for the same key (single-flight, e.g. Go's `golang.org/x/sync/singleflight`), a short recompute lock or lease, serve-stale-while-revalidate, probabilistic early refresh, and TTL jitter so many keys don't expire together.
- **Cache masking a bad access pattern.** If the miss path does an N+1 or a full scan, a cold start, deploy, or flush sends the full cost to the database at once. Fix the miss path.
- **Cache down.** Does every request then fall through to the database? Is there a timeout on the cache client, and a circuit breaker?
- **Negative caching.** Repeated lookups for missing keys can be cached briefly. Don't cache transient errors for long.

**Resource behavior**
- Unbounded in-process caches are memory leaks. Require a maximum size with an eviction policy (LRU or similar) and a TTL.
- With in-process caches on N instances you get N copies, N cold starts, and inconsistent views between instances. A shared cache trades that for a network hop.
- Large values cost serialization time and network transfer on every hit. Cache the smaller derived value if that's all callers need.
- Ask how the hit rate will be observed. A cache nobody measures can't be shown to help.

---

## 7. Work in the request path

**Move it to a background job when the user doesn't need the result before the response, or when it involves:** email, SMS, or push sending; outbound webhooks; calls to slow or flaky third parties; file generation (PDF, images, exports, archives); media processing; a fan-out over many records; long CPU-heavy computation.

**A background job only helps if:**
- It's enqueued **after the transaction commits** (`transaction.on_commit`, `after_commit` hooks, or a transactional outbox). Otherwise the job can run before its data is visible, or for a write that was rolled back.
- The handler is **idempotent**. Most queues deliver at least once, and retries re-run it.
- Work is **chunked** with a bounded batch size, and large fan-outs enqueue child jobs rather than one giant job.
- The payload carries ids, not large blobs. Retries use **backoff**, failures go to a **dead-letter** destination, every job has a **timeout**, and queue depth and age are observable.
- The UI has a way to show progress or completion if the user is waiting on the result.

**Blocking an event loop or a shared executor**
- Node: `fs.*Sync`, `crypto.pbkdf2Sync` / `scryptSync`, `JSON.parse` of multi-megabyte bodies, or long synchronous loops in a request handler stall every concurrent request. Use the async APIs or `worker_threads`. Note that async `fs`, `dns.lookup`, `crypto.pbkdf2` / `scrypt`, and `zlib` all share the libuv threadpool, which has 4 threads by default (`UV_THREADPOOL_SIZE`). Heavy use of them queues behind it under load, even though the event loop stays free.
- Python asyncio: `requests`, `time.sleep`, synchronous DB drivers, or CPU-heavy work inside `async def` blocks the loop. Use async clients, or `asyncio.to_thread` / a process pool. On standard (GIL) builds, CPU-bound threads don't run in parallel, so use processes for CPU work.
- JVM: blocking I/O in `CompletableFuture.supplyAsync(...)` without an explicit executor runs on the common ForkJoinPool, which parallel streams also share, and starves it. Blocking calls inside a reactive pipeline need a dedicated scheduler (e.g. Reactor's `Schedulers.boundedElastic()`). Virtual threads (Java 21+) make thread-per-task cheap, so the database or HTTP pool becomes the only limit: bound concurrency against it with a `Semaphore`. On JDK 21 to 23, a `synchronized` block around blocking I/O pins the carrier thread, so use `ReentrantLock` there. JDK 24 (JEP 491) removed that pinning.
- .NET: sync-over-async (`.Result`, `.Wait()`) on request threads leads to thread-pool starvation under load.

---

## 8. Network calls

**Chattiness**
- Per-item calls where the remote side offers a batch endpoint. Use it, or propose one.
- Independent calls made sequentially. Run them concurrently **with a bound**: `errgroup.Group` with `SetLimit` in Go, a semaphore with `asyncio.gather` or a `TaskGroup` in Python, `p-limit` or chunked `Promise.all` in Node, a bounded executor on the JVM. Unbounded fan-out just moves the pile-up to the remote service.
- Over-fetching: pulling whole objects to read one field, or skipping pagination on remote list calls.
- Tail latency in fan-out. A request that waits on 10 parallel calls is as slow as the slowest one, so the caller's p99 is worse than any single dependency's p99.

**Timeouts.** Every outbound call needs a connect timeout and an overall or read timeout that fit the caller's own deadline. Library defaults range from none (Python `requests`, Go's zero-value `http.Client` and `http.Get`) to minutes (.NET `HttpClient` defaults to 100 seconds), which rarely matches a user-facing latency budget. Propagate deadlines downstream where the stack supports it (contexts, cancellation tokens, `AbortSignal.timeout` with `fetch`).

**Retries**
- Retry only idempotent operations, or ones protected by an idempotency key. Blindly retrying a non-idempotent `POST` can charge a card twice.
- Retry on connection errors and on 408, 429, 502, 503, and 504. Don't retry other 4xx responses. Honor `Retry-After`.
- Use exponential backoff with jitter and cap both the attempt count and the total time. Synchronized retries without jitter arrive in waves.
- Retry at one layer. Attempts multiply across layers (the arithmetic is in impact-estimation.md).
- For dependencies that fail hard, use a retry budget or a circuit breaker so the caller fails fast instead of queuing.

**Connection reuse**
- Creating a new HTTP client per call loses keep-alive and pays a TCP plus TLS handshake every time. Under load it can exhaust sockets. In .NET use `IHttpClientFactory` or a long-lived `HttpClient`. In Python use a `requests.Session` or a shared `httpx.Client`. In Go reuse one `http.Client`.
- Large JSON responses with no compression, or chatty protocols over high-latency links.

---

## 9. Concurrency and resource pools

**Transactions held across slow work.** A transaction that stays open during an HTTP call, email send, file upload, or user think-time keeps a pooled connection checked out and keeps its row locks. Other writers queue behind those locks, the pool drains, and the database shows sessions "idle in transaction". The fix is: read, commit, do the I/O, then write the result in a new short transaction. Use an outbox when the side effect must be tied to the commit.

```python
# Before: connection and row locks held for the length of the payment call
with db.transaction():
    order = Order.lock(order_id)           # SELECT ... FOR UPDATE
    result = payments.charge(order.total)  # 200 ms to several seconds over the network
    order.mark_paid(result.id)

# After: short transactions; the external call happens outside any transaction
with db.transaction():
    order = Order.lock(order_id)
    if order.status != "new":
        return                             # already in flight or done; a retry must not charge again
    order.status = "payment_pending"

result = payments.charge(
    order.total,
    idempotency_key=f"order-{order.id}",   # the same key on every attempt, including the reconciler's
    timeout=5,                             # bounded; a timeout means "outcome unknown", not "failed"
)

with db.transaction():
    updated = db.execute(
        "UPDATE orders SET status = 'paid', charge_id = :charge "
        "WHERE id = :id AND status = 'payment_pending'",
        {"charge": result.id, "id": order_id},
    ).rowcount
    # 0 rows: a retry, webhook, or reconciler already moved the order on. Treat it as handled.
```

**Splitting a transaction around I/O needs a recovery path.** A crash, deploy, or timeout between a successful charge and the second transaction leaves the customer charged and the order stuck in `payment_pending`. Close that window in one of two ways. A reconciler job can find orders that have sat in the pending state longer than a threshold and re-drive them with the same idempotency key, so the provider returns the original result instead of charging again. Or the provider's webhook can be the source of truth for the final transition. Either way, the final write must be a conditional state transition (`WHERE status = 'payment_pending'`), never an unconditional "mark paid", so that duplicates and late arrivals can't apply it twice or overwrite a later state. When you recommend this split in a review, say which recovery path the author needs.

**Pool exhaustion**
- Unbounded parallel work (`Promise.all` over thousands of items, parallel streams, a goroutine or virtual thread per item) where each task takes a connection. Bound the concurrency below the pool size, or batch the work.
- Pool size × instances can exceed the database's connection limit. Check the arithmetic, and size pools with Little's Law (see impact-estimation.md).
- Connections leaked on error paths (no `finally`, `with`, `using`, or `defer` to release them).
- An unbounded wait for a connection. When the pool drains, requests should fail fast, not hang. The checkout timeout should be shorter than the request deadline. Examples are HikariCP `connectionTimeout`, SQLAlchemy `pool_timeout`, and node-postgres `connectionTimeoutMillis`, which defaults to 0, meaning it waits forever.
- No server-side backstop. PostgreSQL's `statement_timeout` and `idle_in_transaction_session_timeout`, or MySQL's `max_execution_time` for `SELECT`s, kill a stuck statement or an abandoned transaction instead of letting it hold locks and a connection indefinitely. They are often set per role or per connection, so check the application's connection settings as well as the server config.

**Hot spots and lock scope**
- A single row every request updates (global counters, "last seen", balances) serializes writers. An atomic `UPDATE ... SET n = n + 1` fixes lost updates but still queues on the row lock. For very hot counters, use sharded counters or append-only events with periodic aggregation.
- Read-modify-write in application code is both a race and a contention source. Use atomic SQL, optimistic concurrency (a version column), or short explicit locks.
- `SELECT ... FOR UPDATE`, mutexes, or `synchronized` blocks wrapped around slow work or I/O. Shrink the critical section to the state change.
- A process-wide lock on a hot path, such as a global lock around a shared cache or client.
- Locks taken in inconsistent orders across code paths cause deadlocks and retry storms. Acquire them in one consistent order.
- Thread-pool self-deadlock: tasks in a bounded pool that block waiting on other tasks submitted to the same pool.
