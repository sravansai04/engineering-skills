# Performance Regressions

Read this when something got slower, uses more CPU, or makes more calls than it used
to, and you need to find out why. For reviewing a diff for performance risk before
it ships, use the `review-suite:performance-review` skill; for tuning one slow query in
isolation, the `data-api:query-review` skill (either one, if installed).

The bundled scripts live in this skill's `scripts/` directory. `${CLAUDE_SKILL_DIR}`
in the commands below is not a shell variable: replace it with the skill directory
path shown under "Reference files" in SKILL.md.

## Contents
1. Measure before you guess
2. Confirm the regression
3. Locate it: profile both versions
4. Usual suspects
5. Bisect on a performance threshold
6. Prove the fix and guard against recurrence

---

## 1. Measure before you guess

Intuition about where time goes is wrong often enough that you should measure first.
Define three things:

- **Metric:** latency (p50 and p99 tell different stories), throughput, CPU time,
  allocations, query count, or bytes transferred. Pick the one the user experiences
  as the regression.
- **Workload:** the exact operation and input size that got slower. Use a realistic
  size, because many regressions only show at production volume.
- **Conditions:** the same machine, build type (release or optimized, never debug),
  configuration, and data, for both versions.

Hygiene:

- Warm up before measuring (JIT compilation, caches, connection pools).
- Run several times and report the median and spread, not one number.
- Run an A/A comparison (the same build twice) to learn the noise floor. A difference
  smaller than the noise is not a finding.
- Reduce noise: close other heavy processes, avoid shared CI runners for precise
  numbers, and watch for thermal throttling and CPU frequency scaling on laptops.

## 2. Confirm the regression

Run the old and new builds back to back on the same machine:

```bash
# Whole commands or CLIs
hyperfine --warmup 3 './old/bin/tool input.dat' './new/bin/tool input.dat'

# Go microbenchmarks
go test -run '^$' -bench . -benchmem -count 10 ./pkg/... > new.txt   # repeat on the old build into old.txt
benchstat old.txt new.txt

# Rust (criterion)
cargo bench -- --save-baseline before    # on the old build
cargo bench -- --baseline before         # on the new build, compares against "before"

# Python (pytest-benchmark)
pytest --benchmark-autosave              # on the old build
pytest --benchmark-compare               # on the new build
```

For JVM code use JMH rather than a hand-written timing loop, since JIT and dead-code
elimination make naive loops misleading. For services, replay a fixed request set
with the team's load tool and compare latency distributions.

Also check how cost scales. Measure at N, 10N, and 100N. If the old version scales
linearly and the new one scales worse, an algorithmic change (often an accidental
nested loop or a repeated lookup) is likely.

## 3. Locate it: profile both versions

Profile the same workload on the good and bad builds, then compare where time goes.
A differential view (new minus old) points straight at the change.

| Stack | CPU profiling | Notes |
|---|---|---|
| Linux, any native or JIT code | `perf record -g -p PID -- sleep 30`, then `perf report` | Frame pointers or debug info improve stacks |
| Python | `py-spy record -o profile.svg --pid PID` or `py-spy top --pid PID`; `python -m cProfile -o out.prof script.py` | py-spy samples a live process without restarting it |
| JVM | `jcmd PID JFR.start duration=60s filename=rec.jfr` (JDK Flight Recorder); async-profiler | Inspect in JDK Mission Control or convert to flame graphs |
| Go | `go test -cpuprofile cpu.out ...` or `/debug/pprof/profile`; `go tool pprof -http=:8080 cpu.out` | `go tool pprof -diff_base old.out new.out` shows the difference |
| Node.js | `node --cpu-prof app.js` writes a `.cpuprofile`; `node --inspect` with DevTools | Open `.cpuprofile` files in Chrome DevTools |
| Browser | DevTools Performance panel | Check long tasks, layout thrashing, and bundle size |
| .NET | `dotnet-trace collect -p PID`; `dotnet-counters monitor -p PID` | Counters show GC and thread pool pressure live |

If CPU time is flat but wall-clock time grew, the time is spent waiting. Use tracing
(spans per call), I/O and lock-contention profiles, and query logs rather than a CPU
profiler.

## 4. Usual suspects

Check these in roughly this order:

1. **More round trips:** N+1 queries, chattier remote calls, loops that call a service
   per item. Count queries or calls per request on both versions.
2. **Lost caching:** a cache key that now includes a varying value, a cache disabled
   by configuration, memoization removed in a refactor.
3. **Algorithmic change:** linear search in a loop, repeated sorting, string
   concatenation in a loop, regex with catastrophic backtracking.
4. **Database plan change:** missing or unused index, different plan after a data
   growth or statistics change, implicit type casts that prevent index use. Inspect
   the plan with the database's EXPLAIN facility.
5. **Allocation and GC pressure:** more temporary objects, larger payloads,
   boxing, copying large structures.
6. **Contention:** a wider lock, a smaller pool, synchronous I/O on a hot path,
   blocking calls inside an async event loop.
7. **Logging and instrumentation:** debug logging left on, expensive string
   formatting even when the log level is off, high-cardinality metrics.
8. **Dependency or runtime upgrade:** changed defaults (pool sizes, timeouts,
   serialization strategy, compression).
9. **Build and config:** debug build, optimizations disabled, wrong flags, a feature
   flag that enabled an expensive path.

## 5. Bisect on a performance threshold

When you know a fast version and a slow version, bisect with a check that:

1. Builds the revision (the adapter's `-b` skips it if the build fails).
2. Runs the workload several times and takes the median.
3. Exits 0 if the median is below a threshold set midway between the good and bad
   medians, 1 if it isn't, and 125 if the workload can't run at that revision.

Save this outside the repository as `/tmp/perf-check.sh` and make it executable. It
uses hyperfine and jq; any timer that reports a median works the same way.

```sh
#!/bin/sh
# Exit 0 if the workload is fast, 1 if slow, 125 if it can't be measured here.
THRESHOLD=0.45   # seconds: midway between the good median (0.30) and the bad median (0.60)
json=$(mktemp) || exit 125
hyperfine --runs 10 --warmup 2 --export-json "$json" './bin/tool /tmp/input.dat' >/dev/null 2>&1 || exit 125
# hyperfine 2.x nests the median under "summary"; 1.x keeps it at the top level
median=$(jq '.results[0].summary.time_wall_clock.median // .results[0].median' "$json")
rm -f "$json"
case "$median" in ''|null) exit 125 ;; esac
echo "median ${median}s, threshold ${THRESHOLD}s"
awk -v m="$median" -v t="$THRESHOLD" 'BEGIN { exit !(m < t) }'
```

```bash
git bisect start --term-old=fast --term-new=slow
git bisect fast v3.1.0
git bisect slow HEAD
git bisect run "${CLAUDE_SKILL_DIR}/scripts/bisect-check.sh" -b 'make build' -- /tmp/perf-check.sh
```

Don't pass `-n` to the adapter here: the median over several runs already absorbs the
noise, and with `-n` a single slow run would mark the revision slow. Run the check by
hand at both endpoints first (fast must exit 0, slow must exit 1). The gap between good
and bad must be several times the noise floor from section 1, or bisect will wander.
See `git-history-and-bisect.md` for the full procedure and its pitfalls.

## 6. Prove the fix and guard against recurrence

- Rerun the same comparison from section 2 under identical conditions. The fix should
  restore the metric to the old level, within noise.
- Explain the mechanism (step 4 of the main workflow). For example: "the new
  serializer re-reads the schema on each call: 3 extra file reads per request."
- Add a guard that is deterministic: assert the number of queries per request, the
  number of calls to a dependency, or allocations in a benchmark, or add a
  complexity test with a large N and a generous bound. Wall-clock thresholds in
  ordinary unit tests become flaky tests. Keep timing benchmarks in a dedicated
  benchmark job that compares against a baseline.
