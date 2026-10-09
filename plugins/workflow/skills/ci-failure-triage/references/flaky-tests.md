# Flaky Tests: Reproduce, Fix, Quarantine

A flaky test both passes and fails on the same code. It is a real bug, either in the test or in the code it tests, and it costs every engineer who hits it a re-run and a little more trust in CI. The goal is to make it fail on demand, remove the nondeterminism, and prove that it holds up. Quarantine is the fallback when that can't happen promptly.

## Contents

1. Establish that it is flaky
2. Categories, how to reproduce each, and the fix
3. Repeat-and-randomize commands by framework
4. Proving the fix
5. Quarantine: rules and tracking-issue template

## 1. Establish that it is flaky

- **Same code, different outcomes.** You need a pass and a fail on the same SHA. A pass on a different commit or merge base doesn't count, because the code changed in between.
- **Gather history before theorizing.** Note which runners, matrix legs, times of day and neighboring tests show up in the failing runs. Search CI history for the test name. Clustering is the strongest clue: failures only on one OS, only in the first minutes past midnight UTC, or only when a particular other test runs earlier.
- **Ask whether this change made it flaky.** A new test that shares a fixture, a new background task, or a slower code path can turn a stable test flaky. If so, the fix belongs in this PR. If the flake predates this change, the decision tree's LEAF 10 says what happens to the current PR.
- **A property-based failure is not a flake.** If the failing test is property-based (generated inputs) and the framework printed a falsifying example or a replay seed, it found a real input that breaks the code. Re-run it with that example or seed and treat it as a regression.

## 2. Categories, how to reproduce each, and the fix

| Category | Typical clues | Reproduce by | Fix |
|---|---|---|---|
| **Timing / async** | Fixed `sleep`s, "element not found", "expected 3 events, got 2", fails more often on slower or busier runners | Repeating the test under CPU pressure (`docker run --cpus=1 ...`, running it alongside a busy workload, `taskset` on Linux) | Wait for the condition itself: an awaited promise or future, an event or callback, or polling with a deadline. Use fake timers for time-driven logic. In browser tests, use the framework's auto-waiting locators and assertions instead of fixed waits. |
| **Order dependence / shared state** | Passes alone, fails in the full suite, or the reverse. Module-level caches, singletons, global config, env vars changed in place, DB rows left behind, mocks or fake timers never restored | Random order with a fixed seed, then bisecting to the smallest pair of tests that fails (section 3) | Give each test its own state: reset in teardown, roll back a transaction per test, build fresh fixtures, restore mocks, timers and env vars. Avoid mutable module-level state in code under test. |
| **Parallelism / resource contention** | "Address already in use", collisions on temp files or directories, unique-constraint violations on shared test data, only fails with several workers | Running with CI's worker count (`-n 4`, `--maxWorkers`, `-p`) or more | Bind to port 0 and read back the assigned port. Use per-test temp directories and per-worker database or schema names. Generate unique IDs instead of fixed ones. |
| **Concurrency bug in the code** | Wrong values under load, deadlocks, failures detected by a race detector | A race detector (`go test -race`, ThreadSanitizer, ...) and high iteration counts | Fix the synchronization in the product code. This is a product bug that the test happened to catch. |
| **Network / external services** | DNS errors, timeouts or 5xx from third-party sandboxes, package downloads during tests | Running with networking disabled (`docker run --network none ...`) | Fake external services at your own boundary, or use record/replay. Keep real third-party contract tests in a separate, non-blocking job. |
| **Time and dates** | Fails near midnight, month end, year end, a DST change or a leap day. Fails only in some time zones. Two "now" timestamps compare as equal or out of order | Changing the time zone (`TZ=Pacific/Kiritimati`, UTC+14, and `TZ=Pacific/Pago_Pago`, UTC-11, put the date boundary in different places), or pinning the clock (`faketime 'YYYY-MM-DD HH:MM:SS' cmd` for programs that read the clock through libc; it doesn't affect every runtime) | Inject a clock and pin it in tests. Keep the time zone explicit. Add test cases on both sides of each boundary. Compare timestamps with tolerance only when imprecision is part of the contract. |
| **Randomness** | Unseeded random test data, random IDs that occasionally collide or sort differently | Fixing the seed and looping | Seed the generator per test and log the seed on failure. Make assertions independent of the generated values. |
| **Unordered results** | Expected `[a, b]`, got `[b, a]`. Hash map or set iteration, directory listing order, SQL without `ORDER BY`, results collected from concurrent workers | Looping. Order often changes between runs or platforms | Sort before comparing, compare as sets or multisets, or add `ORDER BY` if the order is part of the contract. |
| **Resource leaks** | Later tests in a run fail with "too many open files", connection-pool exhaustion or rising memory | Running the full suite in one process, or repeating the test many times in one process | Close files, connections, servers and subscriptions in teardown. Detect leaks with tools such as Jest's `--detectOpenHandles`. |

## 3. Repeat-and-randomize commands by framework

Read the project's test config first, and add the CI job's flags to whatever you run. Install a plugin only if the project already uses it, or you have checked that it fits.

### Any runner: a shell loop

```bash
for i in $(seq 1 50); do
  <the exact test command> || { echo "failed on iteration $i"; break; }
done
```

### Python (pytest)

```bash
pytest path/test_x.py::test_name -x                  # run one test, stop at the first failure
pytest path/test_x.py::test_name --count=50 -x       # pytest-repeat plugin
pytest --randomly-seed=12345                         # pytest-randomly: replay the seed it printed
pytest -p no:randomly                                # pytest-randomly: disable shuffling to compare
pytest -n 4                                          # pytest-xdist: match CI's parallelism
```

### JavaScript (Jest)

```bash
npx jest path/to/file.test.ts -t "test name" --runInBand   # one test, serial
npx jest --randomize --seed=1234                           # shuffle within files, replay a seed
npx jest --detectOpenHandles                               # find leaked handles that keep the process alive
```

### JavaScript (Vitest)

```bash
npx vitest run --sequence.shuffle                       # prints the seed it used
npx vitest run --sequence.shuffle --sequence.seed=1234  # replay that order
```

### End-to-end (Playwright)

```bash
npx playwright test path/spec.ts --repeat-each=20 --retries=0 --trace on
```

Playwright reports a test that failed and then passed on a retry as "flaky". Its scaffolded config enables retries on CI, so check the report for that status before treating a green as clean.

### Go

```bash
go test -run '^TestName$' -count=200 -race ./pkg/...   # -count also bypasses the test cache
go test -shuffle=on ./...                              # prints the seed with -test.shuffle
go test -shuffle=1234567890 ./pkg/...                  # replay that order
```

### Ruby (RSpec)

```bash
rspec --order random --seed 1234
rspec --seed 1234 --bisect                             # finds the minimal set of examples that fails
```

### JVM

```bash
mvn -Dtest='FooTest#bar' test                          # Maven Surefire: one test method
./gradlew test --tests 'com.example.FooTest' --rerun-tasks
```

JUnit 5's `@RepeatedTest(100)` repeats a test inside one run. Surefire's `rerunFailingTestsCount` labels tests that fail and then pass as flaky. That makes it a detector, not a fix.

### .NET

```bash
dotnet test --filter "FullyQualifiedName~MyNamespace.MyTests"
```

### Bisecting an order dependence by hand

1. Take the failing seed.
2. Run the failing test together with the first half of the tests that ran before it in that order.
3. Keep whichever half still produces the failure, and repeat until two tests remain: the polluter and the victim.
4. The fix normally belongs in the polluter's cleanup, the state it leaves behind, rather than in the victim.

## 4. Proving the fix

A flaky test that passed once proves nothing. Before you call it fixed:

- **Run it under the condition that used to break it.** That means the same seed, the same time zone or pinned clock, the same CPU constraint, and the same worker count. It must pass every time.
- **Then run it many times.** Use enough iterations that the old failure rate would almost certainly have shown up. If it failed 1 run in 20, 100 clean iterations is reasonable evidence. If it failed 1 in 200, you need far more iterations, or a deterministic reproduction.
- **Run the full suite in random order** with a few seeds, so the fix hasn't simply moved the pollution somewhere else.
- **Record the numbers in the PR**, for example "0 failures in 200 iterations with `--cpus=1`; previously 9 in 200".

## 5. Quarantine: rules and tracking-issue template

Quarantine only when all three hold:

- The flake blocks other people.
- A real fix can't land promptly.
- The test doesn't cover code that the current change touches.

Quarantining a test that guards your own diff hides your regression. Filing the issue and committing the skip are both visible to others, so get the user's go-ahead before either.

1. **File the tracking issue first** (template below), with a named owner and a review date. Without an owner and a date, a quarantined test is a deleted test that nobody admits to.
2. **Disable the test with the framework's own mechanism, and put the issue link in the reason:**
   - **Python:** `@pytest.mark.skip(reason="flaky: <issue link>")`, or a project-defined `quarantine` marker deselected in the blocking job.
   - **JavaScript:** `it.skip("...")` with a `// flaky: <issue link>` comment directly above it.
   - **Go:** `t.Skip("flaky: <issue link>")`.
   - **JVM:** `@Disabled("flaky: <issue link>")`, or a JUnit `@Tag("quarantine")` excluded in the blocking job.
   - **RSpec:** `skip "flaky: <issue link>"`, or a `:quarantine` tag excluded in the blocking job.
3. **Keep collecting signal where you can.** Run quarantined tests in a separate, non-blocking job, so you can tell when the fix works.
4. **Keep it narrow.** Quarantine the one test, never the file or suite. Don't add or raise automatic retries as a substitute: that hides every future flake and real concurrency bug along with this one. An existing retry policy that reports flaky results somewhere tracked is a detector, not a fix, and is fine to keep.
5. **Un-quarantine on evidence.** Re-enable the test once the fix lands and it passes the proof in section 4. If the review date passes without a fix, decide explicitly whether to fix it, rewrite it, or delete it with a stated reason, and record that decision on the issue.

### Tracking-issue template

```markdown
Title: Flaky test: <test id>

**Test:** <path::name>
**Failure (verbatim):** <first error line(s)>
**Evidence:** <N failures in M runs since DATE>, with links: <run 1>, <run 2>, ...
**Where it fails:** <OS / matrix leg / time of day / worker count / neighbors, if clustered>
**Suspected category:** <timing | order/shared state | parallelism | concurrency | network | time/date | randomness | unordered results | leak>, because <evidence>
**Quarantined in:** <PR/commit>, via <skip/tag mechanism>; still runs in: <non-blocking job, or "nowhere">
**Owner:** <person or team>
**Review by:** <date>
**Exit criteria:** fix merged, plus <K> clean iterations under <condition>, plus green random-order runs with <S> seeds
```
