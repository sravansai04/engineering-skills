# Measurement: Getting Evidence for a Performance Finding

Read this before running a profiler, benchmark, query counter, query plan, or load test, and when judging a benchmark someone else wrote. Use the project's own tooling first, and only fall back to the generic tools below when nothing exists.

## Contents

1. [Pick the instrument by question](#1-pick-the-instrument-by-question)
2. [Measure the PR head against its base](#2-measure-the-pr-head-against-its-base)
3. [Find what the project already has](#3-find-what-the-project-already-has)
4. [Count queries in a test](#4-count-queries-in-a-test)
5. [Query plans](#5-query-plans)
6. [Profilers by stack](#6-profilers-by-stack)
7. [Micro-benchmarks and how to judge one](#7-micro-benchmarks-and-how-to-judge-one)
8. [Load tests](#8-load-tests)
9. [Reading a profile](#9-reading-a-profile)
10. [Safety rules](#10-safety-rules)

---

## 1. Pick the instrument by question

| Question | Instrument | Cost to run |
|---|---|---|
| Is this an N+1? How many queries does the path issue? | Query-count test, or the traces for an existing request | Low |
| Is this query slow at real data sizes? Is the index used? | `EXPLAIN` on realistic data, handed off to `data-api:query-review` | Low to medium |
| Where does the CPU time go? | Sampling CPU profiler | Low |
| Where does the latency go when the code mostly waits? | Wall-clock profiler, or distributed traces | Low |
| Why does memory grow? | Heap profiler or heap snapshot diff | Medium |
| Is version A faster than version B for this function? | Micro-benchmark harness at a realistic N | Medium |
| How does the service behave under concurrent load? | Open-model load test in an isolated environment | High |

Choose the cheapest instrument that answers the question. Distributed traces or APM data, if the team already has them, are often the fastest evidence of all: a request with 200 near-identical database spans is an N+1 in production.

---

## 2. Measure the PR head against its base

A measurement only counts as evidence for a PR if it ran against the PR's code. The user's checkout may be another branch, or may have uncommitted work, and a single number with no baseline can't show what the change did. Run the same measurement at both revisions:

```bash
# HEAD_SHA and BASE_SHA come from SKILL.md step 1. For a branch: its tip, and its merge base with the default branch
ROOT="$(mktemp -d)"                                  # outside the user's checkout
git worktree add --detach "$ROOT/perf-head" "$HEAD_SHA"
git worktree add --detach "$ROOT/perf-base" "$BASE_SHA"
# install dependencies and run the identical command in each worktree
git worktree remove --force "$ROOT/perf-head"
git worktree remove --force "$ROOT/perf-base"
```

- A fresh worktree has no installed dependencies, build output, or local config. Install them the way the project documents. If that is too slow or needs secrets you don't have, say so, and give the measurement as a suggested test in the finding's Verify line instead.
- When the target is the current branch, including uncommitted work, you can measure in place. Delete any scratch file you add there before you finish, and still build the base in a worktree for the comparison.
- Otherwise, write scratch query-count tests and benchmarks only inside the worktrees. To run the same new test against the base, copy it into the base worktree too. Removing the worktrees removes the scratch files with them.
- Report both numbers with the revision each came from, e.g. "base `a1b2c3d`: 2 queries at N=10 and at N=100; head `d4e5f6a`: 12 and 102".

---

## 3. Find what the project already has

```bash
# Scripts and task runners
grep -A30 '"scripts"' package.json 2>/dev/null
ls Makefile justfile Taskfile.yml pyproject.toml Cargo.toml 2>/dev/null
grep -nE '^(bench|perf|profile|load)[^:]*:' Makefile 2>/dev/null

# Existing benchmarks (git grep searches tracked files only, so it skips dependency folders)
git grep -lE 'func Benchmark|@Benchmark|criterion_group!|\[Benchmark\]|pytest\.mark\.benchmark|[^a-zA-Z]bench\(' | head

# Existing query-count assertions
git grep -nE 'assertNumQueries|django_assert_num_queries|assert_queries_count|expectsDatabaseQueryCount' | head

# CI jobs that build, benchmark, or measure size
ls .github/workflows .gitlab-ci.yml .circleci 2>/dev/null
```

Also read `README` and `CONTRIBUTING` for documented profiling or benchmarking workflows. An existing harness gives results the team already trusts.

---

## 4. Count queries in a test

A query-count test is the best evidence for N+1 findings. It turns a structural argument into a measured one, and once the fix lands it stays as a regression guard. Render or call the path with two different N values (say 2 and 20). If the count changes, the cost scales with N.

| Stack | How |
|---|---|
| Django | `self.assertNumQueries(n)` as a context manager. In pytest-django, the `django_assert_num_queries` fixture. `CaptureQueriesContext(connection)` to inspect the queries |
| Rails 7.2+ | `assert_queries_count(n) { ... }` and `assert_no_queries { ... }`. On older versions, subscribe to `sql.active_record` through `ActiveSupport::Notifications`. The Bullet gem flags N+1s in test or development |
| Laravel | `$this->expectsDatabaseQueryCount(n)`, which is checked at teardown, or `DB::listen` / `DB::enableQueryLog()` |
| SQLAlchemy | An `event.listen(engine, "before_cursor_execute", counter)` hook |
| Hibernate / JPA | `hibernate.generate_statistics=true`, then `sessionFactory.getStatistics().getPrepareStatementCount()`. Or a JDBC proxy such as datasource-proxy |
| EF Core | A `DbCommandInterceptor` that counts commands, or `LogTo` while testing |
| Prisma | `log: [{ emit: "event", level: "query" }]` with `prisma.$on("query", ...)` |
| Anything else | Wrap the driver or connection to count executed statements, or read the ORM's query log |

---

## 5. Query plans

Check plans against data that is realistic in size and distribution. On a 50-row development table a sequential scan is the right plan, so a tiny-data plan says nothing about production.

| Database | Command | Notes |
|---|---|---|
| PostgreSQL | `EXPLAIN (ANALYZE, BUFFERS) SELECT ...` | From PostgreSQL 18, buffer statistics are included automatically when `ANALYZE` is used |
| MySQL 8.0.18+ | `EXPLAIN ANALYZE SELECT ...` | `TREE` format by default. From 8.3 (including 8.4 LTS and 9.x), `EXPLAIN ANALYZE FORMAT=JSON` also works after `SET explain_json_format_version = 2` (the default from 9.5), which is easier for tools to compare. Like PostgreSQL's, it executes the statement |
| SQLite | `EXPLAIN QUERY PLAN SELECT ...` | |
| SQL Server | `SET STATISTICS IO ON; SET STATISTICS TIME ON;` with the actual execution plan enabled | |

`EXPLAIN ANALYZE` **executes** the statement. For `INSERT`, `UPDATE`, or `DELETE`, wrap it in a transaction and roll back (`BEGIN; EXPLAIN ANALYZE ...; ROLLBACK;`). Even then, row locks are taken while it runs. Interpreting plans and designing indexes is `data-api:query-review`'s job, so hand over the plan with the context of which code path issues it and at what N.

---

## 6. Profilers by stack

Prefer **sampling** profilers. Their overhead is low enough for realistic workloads, and they don't distort small, frequently called functions the way instrumenting profilers do. Profile an optimized build under a realistic workload.

| Stack | CPU / wall-clock | Memory |
|---|---|---|
| Python | `py-spy record -o profile.svg --pid PID` or `py-spy record -o profile.svg -- python app.py`; `py-spy top --pid PID`; `python -m cProfile -o out.prof script.py` | `tracemalloc` (stdlib); `memray run script.py`, then `memray flamegraph` on the output file |
| Node.js | `node --cpu-prof app.js` (opens in DevTools); `node --inspect` and the DevTools Performance tab | `node --heap-prof`; heap snapshots through `--heapsnapshot-signal=SIGUSR2` or `v8.writeHeapSnapshot()` |
| Go | `go test -bench=. -cpuprofile cpu.out` (one package at a time), then `go tool pprof -http=:8080 cpu.out`. For services, `net/http/pprof` and `go tool pprof http://HOST:PORT/debug/pprof/profile?seconds=30` | `-memprofile mem.out`; `/debug/pprof/heap`; `/debug/pprof/goroutine` for goroutine leaks |
| JVM | JFR: `java -XX:StartFlightRecording=duration=60s,filename=rec.jfr ...` or `jcmd PID JFR.start duration=60s filename=rec.jfr`. async-profiler: `asprof -d 30 -f flame.html PID`, with `-e wall` for wall-clock and `-e lock` for contention | `asprof -e alloc ...`; `jcmd PID GC.heap_dump heap.hprof`, analyzed in a heap analyzer |
| .NET | `dotnet-trace collect --process-id PID`; `dotnet-counters monitor --process-id PID` | `dotnet-gcdump collect --process-id PID` |
| Ruby | `rbspy record --pid PID`; `stackprof` | `memory_profiler` gem |
| Rust | `cargo flamegraph` (from the `flamegraph` crate); `perf` | `heaptrack`, or the `dhat` crate |
| PHP | Xdebug in profile mode (`xdebug.mode=profile`), or SPX | Xdebug or SPX memory reports |
| Linux, any native process | `perf record -g -p PID`, then `perf report` | |

Attaching to another process may need elevated privileges, and some platforms restrict it. Ask before using `sudo`.

---

## 7. Micro-benchmarks and how to judge one

**Harnesses**

| Stack | Harness | Guard against dead-code elimination |
|---|---|---|
| Go | `testing.B`, run with `go test -bench=NAME -benchmem -count=10`, compared using `benchstat old.txt new.txt` | `for b.Loop() { ... }` (Go 1.24+). On older versions, keep results alive (e.g. `runtime.KeepAlive` or a package-level sink) |
| JVM | JMH | Return the value, or pass it to `Blackhole.consume` |
| Rust | `criterion` via `cargo bench` | `std::hint::black_box` |
| .NET | BenchmarkDotNet | Return the value from the benchmark method |
| Python | `python -m timeit`, `pyperf`, `pytest-benchmark` | (interpreted, so this is less of an issue) |
| JS / TS | `vitest bench`, `tinybench`, `mitata` | Use the result, since JITs eliminate unused work |
| Ruby | `benchmark-ips` | |
| Whole commands | `hyperfine --warmup 3 'old-command' 'new-command'` | |

**Validity checklist.** Apply this to any benchmark you write and to any benchmark offered as evidence in a PR.

- [ ] It exercises the **changed code path**, not a convenient neighbour.
- [ ] Inputs have realistic **size and shape**, including the skewed worst case and not just the median.
- [ ] It runs an optimized or release build, on a quiet machine, with no debugger attached and the same hardware for both versions.
- [ ] It includes **warm-up** for JIT runtimes and reports steady state.
- [ ] It does **many runs** and reports variance. Differences inside the noise don't count as wins. Use the harness's statistical comparison (benchstat, criterion, BenchmarkDotNet, `pyperf compare_to`).
- [ ] Results are consumed, and inputs aren't compile-time constants the optimizer can fold.
- [ ] Setup and teardown are excluded from the timed region, unless they are part of the real cost.
- [ ] Cache state matches reality. Hammering one hot input measures a warm cache that production may never see.
- [ ] Latency is reported as percentiles (p50, p95, p99), not only as a mean.
- [ ] The local win is put in **end-to-end context** (Amdahl's law). A 50% speedup of a function that takes 2% of request time saves 1%.

---

## 8. Load tests

- **Use an open model.** Closed-loop generators send the next request only after the previous one finishes. When the server slows down, they send less, which hides the slowdown (coordinated omission). Use arrival-rate load instead: k6's `constant-arrival-rate` or `ramping-arrival-rate` executors, or `wrk2` with a fixed `-R` rate. Treat results from closed-loop tools such as `wrk` or `ab` as optimistic. With k6, watch `dropped_iterations`: if it is non-zero, the target rate wasn't reached.
- **Match the environment to the question:** production-like data volume, the same instance sizes and pool settings, realistic payloads, and a realistic mix of endpoints.
- **Report** throughput at the latency objective, p50/p95/p99, error rate, and where the knee is (the load at which latency starts climbing steeply). Watch the bottleneck resources too: CPU, pool wait time, database connections, queue depth.
- **Run long enough** to expose leaks, GC pauses, cache expiry, and pool exhaustion. A 30-second run shows none of them, so use soak tests for long-lived-process concerns.
- Mind the dependencies: third-party APIs, rate limits, paid services, and shared databases that the test will hit.

---

## 9. Reading a profile

- In a flame graph, **width** is the share of samples and the vertical axis is stack depth. Colour usually means nothing. Look for wide frames with a lot of self time, and wide plateaus under one call site.
- **CPU profiles can't see waiting.** Time blocked on I/O, locks, or sleeps doesn't show up. If the request is slow but the CPU profile looks idle, switch to wall-clock profiling (async-profiler `-e wall`, `py-spy record --idle` to keep samples from waiting threads) or use traces.
- Compare profiles from the same workload before and after the change. A single profile shows where time goes, not whether the change made it worse.
- Map hot frames back to the cost formula from the review's step 3. If the profile disagrees with your formula, the formula is wrong. Revise the finding.

---

## 10. Safety rules

- Don't run load tests, `EXPLAIN ANALYZE` on writes, heap dumps, or profilers against **production or shared environments** without explicit permission from the owner. Heap dumps can pause the process and contain sensitive data.
- Don't leave scratch query-count tests, benchmarks, generated profiles, heap dumps, or benchmark output in the author's working tree, and don't commit them, unless the author asks or the project already tracks such files. Keep them in a scratch worktree (section 2) or paste them into the review as suggested tests.
- Debug and profiling endpoints (such as Go's `net/http/pprof`) must not be reachable publicly. If a change adds one, flag it for `review-suite:secure-code-review`.
