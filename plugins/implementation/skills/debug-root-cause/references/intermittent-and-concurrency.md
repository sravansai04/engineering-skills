# Intermittent Failures, Heisenbugs, and Races

Read this when a failure doesn't happen every time: flaky tests, "1 in 50 requests",
failures that vanish under a debugger or when you add logging, and suspected race
conditions, deadlocks, or hangs.

The bundled scripts live in this skill's `scripts/` directory. `${CLAUDE_SKILL_DIR}`
in the commands below is not a shell variable: replace it with the skill directory
path shown under "Reference files" in SKILL.md. Run the commands from the project root.

## Contents
1. Name the source of nondeterminism
2. Quick discriminating experiments
3. Make it fail more often
4. Observe without changing the timing
5. Tools by stack
6. Common race shapes and their real fixes
7. Deterministic regression tests for nondeterministic bugs
8. Proving the fix

---

## 1. Name the source of nondeterminism

Every intermittent failure has at least one input that varies from run to run. Find
that input and the bug turns deterministic. The usual candidates:

| Source | Typical signs |
|---|---|
| Thread, async, or process interleaving | Fails under load or parallelism; disappears under a debugger or with extra logging; corrupted or lost updates |
| Test order and shared state | Passes alone, fails in the full suite or only in some orders; global variables, singletons, caches, environment variables, shared DB rows, files, fixed ports |
| Time | Fails near midnight, month end, DST changes, or on slow machines; hard-coded timeouts; `sleep` in tests; comparisons with "now" |
| Randomness | Unseeded RNG, generated test data, hash or set iteration order, UUID ordering |
| External resources | Network calls, rate limits, eventual consistency, DNS, third-party sandboxes |
| Resource exhaustion | Connection pool, file descriptors, memory, disk, thread pool saturation; often coincides with timeouts |
| Undefined behavior (native code) | Uninitialized memory, use-after-free, data races; changes with optimization level or allocator (see `crashes-without-stack-traces.md` section 5) |
| Distributed delivery | At-least-once delivery (duplicates), out-of-order messages, clock skew between hosts, retries that are not idempotent |

## 2. Quick discriminating experiments

Run these first. They are cheap, and each one eliminates whole rows of the table
above.

- **Run the test alone, many times.** If it never fails alone but fails in the suite,
  suspect shared state or test order. If it also fails alone, the cause is inside the
  test or the code under test.
- **Run the suite in a fixed order, then shuffled with a recorded seed.** If one seed
  fails every time, you have an order dependency. Reproduce it with that seed, then
  shrink the set of preceding tests by halving until you find the polluting test.
- **Run serially, then in parallel.** If it fails only in parallel, suspect shared
  resources (DB, files, ports, global state) or a real race.
- **Freeze time and seed randomness.** If the failure disappears, the cause is in
  time or random-data handling.
- **Change the speed.** Run under CPU contention or on a throttled container. If the
  failure rate rises, you have a timing window. Real races and too-tight timeouts
  both behave this way, so read the failing output to tell them apart.
- **Collect the failures.** Save the output of every failing run
  (`"${CLAUDE_SKILL_DIR}/scripts/repeat-run.sh"` keeps those logs) and compare them. Is it always the same assertion, stack, or
  input? A single, consistent failure signature points to one mechanism. Several
  signatures may mean several bugs.

## 3. Make it fail more often

A bug that fails 1 time in 500 is too slow to iterate on. Raise the rate first, then
debug.

- Loop the narrowest test: `"${CLAUDE_SKILL_DIR}/scripts/repeat-run.sh" -n 500 -u -- CMD`
  stops at the first failure and keeps its log. If a run can hang, add a per-run
  timeout or the first hung run blocks the loop forever:
  `"${CLAUDE_SKILL_DIR}/scripts/repeat-run.sh" -n 300 -t 120 -d 'jcmd $PID Thread.print' -- CMD`
  kills any run still going after 120 seconds, records it as TIMEOUT, and first
  appends a thread dump of the stuck process to that run's log. Use the dump command
  that fits the stack (section 5), and set the timeout well above a normal run.
  `$PID` is the process the script started. If that is a wrapper such as a build
  tool, `repeat-run.sh -h` shows how to reach the real process.
- Add contention: run several copies at once, add CPU load (`stress-ng --cpu 8`,
  where available), or limit CPUs (`docker run --cpus=0.5 ...`, `taskset -c 0 CMD`
  on Linux). Slow or crowded schedulers widen race windows.
- Widen the suspected window on purpose. Insert a short delay or a yield between the
  two operations you suspect, such as between the check and the act, or between the
  read and the write. If the failure rate jumps, you have strong evidence for that
  interleaving. This delay is a diagnostic probe. Remove it afterwards, and never ship
  it as the fix.
- Shrink timeouts and pool sizes in a test configuration to surface exhaustion and
  timing bugs quickly.
- Use randomized scheduling tools where they exist (section 5).

## 4. Observe without changing the timing

Heisenbugs vanish when you look at them because printing, debugging, and breakpoints
change the timing. Observe with less disturbance:

- Record events in memory (a ring buffer or an append-only list) with a monotonic
  timestamp, a thread, task, or goroutine ID, and a sequence number. Dump it only when
  the failure occurs. Writing to an in-memory buffer costs far less than synchronous
  I/O.
- Log at operation boundaries (lock acquired or released, message sent or received,
  state transitions), not inside tight loops.
- Capture state at the moment of failure: a thread dump or goroutine dump, a core
  dump, or a heap dump. Configure the process to write these automatically on crash
  or on a signal.
- **For a hang, the dump of the stuck process is the key evidence.** Take it before
  anything kills the process: a deadlock shows as threads each waiting on a lock
  another holds, and pool starvation as every worker blocked on work queued behind
  it. `repeat-run.sh -t SECS -d CMD` does this automatically for a looped
  reproduction. Test-runner timeouts that dump stacks help too: `go test -timeout`
  panics with every goroutine's stack, and the pytest-timeout plugin dumps all
  threads when a test overruns.
- Prefer record-and-replay when available (`rr` on Linux). Record the failing run
  once, then replay it deterministically in a debugger as many times as you need,
  including stepping backwards.
- Use correlation IDs to rebuild the sequence of events across processes and
  services from logs or traces.

## 5. Tools by stack

Use whichever matches the project. Check the project's test configuration first: it
may already have repeat, shuffle, or sanitizer options wired in.

**Go**
- `go test -race -count=200 -run '^TestName$' ./pkg/...` runs the data-race detector
  with many repetitions. `-count` also bypasses the test cache.
- `go test -shuffle=on` randomizes test order and prints the seed. Rerun with
  `-shuffle=SEED`.
- Goroutine dump of a hung process: send `SIGQUIT`, or read `/debug/pprof/goroutine?debug=2`
  when `net/http/pprof` is enabled.
- `go.uber.org/goleak` fails tests that leak goroutines.

**C, C++, Rust (native)**
- ThreadSanitizer: compile and link with `-fsanitize=thread`. AddressSanitizer and
  UBSan: `-fsanitize=address,undefined`. Don't combine TSan with ASan in one build.
- `valgrind --tool=helgrind` or `--tool=drd` detect races and lock-order problems,
  with heavy slowdown.
- `rr record --chaos ./prog` (Linux) randomizes scheduling while recording, then
  `rr replay` debugs that exact run.
- Rust: `loom` model-checks concurrent code by exploring interleavings. `cargo +nightly
  miri test` detects undefined behavior and some data races in `unsafe` code.

**JVM (Java, Kotlin)**
- Thread dump: `jcmd PID Thread.print` (or `jstack PID`). Deadlocks are reported at
  the end of the dump.
- JUnit 5 random order: `@TestMethodOrder(MethodOrderer.Random.class)`. Pin the order
  with the `junit.jupiter.execution.order.random.seed` configuration parameter. The
  seed in use is logged at CONFIG level.
- Stress and interleaving harnesses: jcstress for low-level Java concurrency, Lincheck
  for Kotlin and Java data structures.

**Python**
- Repeat: `pytest --count=200 -x path::test_name` (pytest-repeat plugin).
- Order: pytest-randomly shuffles by default once installed. Rerun with
  `--randomly-seed=SEED`, or disable it with `-p no:randomly`.
- Parallel: `pytest -n auto` (pytest-xdist) exposes shared-state assumptions.
- `python -X dev` enables extra runtime checks. `PYTHONASYNCIODEBUG=1` turns on asyncio
  debug mode, which reports never-awaited coroutines and slow callbacks.
- Hangs: `py-spy dump --pid PID` prints every thread's stack without stopping the
  process. `python -X faulthandler` dumps tracebacks on fatal signals.

**JavaScript / TypeScript**
- Jest: `--runInBand` (serial), `-t 'name'` (one test), `--randomize --seed=N`
  (shuffle within files), and `--detectOpenHandles` (finds leaked timers and sockets
  that keep the process alive).
- Vitest: `--sequence.shuffle.tests`, `--sequence.shuffle.files`, `--sequence.seed=N`,
  and `--no-file-parallelism`.
- The commonest causes are a missing `await`, a fire-and-forget promise, and a timer
  left running between tests. Use fake timers and await every asynchronous assertion.

**.NET**
- For hung or deadlocked processes, run `dotnet-dump collect -p PID`, then open the
  dump with `dotnet-dump analyze` and inspect thread stacks (its `clrstack` command).
  `dotnet-stack report -p PID` gives a quick stack snapshot of a live process.

## 6. Common race shapes and their real fixes

| Shape | Example | Fix direction (not a sleep or a retry) |
|---|---|---|
| Check-then-act (TOCTOU) | `if not exists(x): create(x)` from two workers | Make it atomic: unique constraint plus handling the conflict, a lock around both steps, or an atomic create-if-absent API |
| Lost update (read-modify-write) | Two requests read a balance, both add, both write | Atomic increment, compare-and-swap, optimistic version column, or row lock inside one transaction |
| Unsafe lazy initialization | Two threads both initialize a singleton | The language's once-only primitive or static initializer |
| Mutation during iteration | One thread iterates a collection while another appends | Iterate a snapshot, use a concurrent collection, or hold one lock for both |
| Unsafe publication | Object shared before construction finishes | Publish only after full construction, through a safe channel (lock, volatile/atomic, queue) |
| Async ordering assumption | Assumes callback A runs before B; missing `await` | Make the dependency explicit: await, chain, or join |
| Lock-order deadlock | Thread 1 takes A then B, thread 2 takes B then A | One global lock order; reduce lock scope; timeouts that report rather than hide |
| Test waits by sleeping | `sleep(1)` then assert | Wait on the condition itself: latch, future, or polling with a deadline |
| Shared test fixture | Tests share DB rows, temp files, or ports | Isolate per test: transaction rollback, unique temp dirs, port 0, fresh state |
| Duplicate or out-of-order delivery | Consumer processes the same message twice | Idempotency key, dedupe table, or sequence or version checks |

## 7. Deterministic regression tests for nondeterministic bugs

Prefer controlling the nondeterminism over looping and hoping:

- **Time:** inject a clock interface or use the framework's fake timers. Then test the
  boundary (23:59:59, DST transitions, leap day, timeouts) directly.
- **Randomness:** inject the RNG, or seed it, and test the specific value that failed.
- **Interleaving:** add a test-only hook, latch, or barrier that pauses one actor
  between the two racy operations while the other runs. This reproduces the bad
  ordering on every run. Many teams expose a small "pause point" interface that
  production wires to a no-op.
- **Order dependence:** write a test that runs the polluting test's side effect and
  then the victim, in that order, in one test.

If none of these is practical, a bounded stress test (N concurrent operations,
assert the invariant afterwards) is the fallback. Record its pre-fix failure rate so
the post-fix result means something.

## 8. Proving the fix

- Apply the pass-count rule from the main workflow (Step 8) to the conservative
  failure rate measured before the fix. `"${CLAUDE_SKILL_DIR}/scripts/repeat-run.sh"`
  prints both numbers.
- Run under the same amplification (load, parallelism, shuffle) that exposed the bug.
  A fix that passes only in calm conditions isn't proven.
- For data races in languages that have a detector, the detector must report clean
  on the regression test.
- Explain why the new code is correct for *every* interleaving, not just why the
  failing one is gone. Locks, atomics, and transactions give that guarantee. Timing
  changes don't.
