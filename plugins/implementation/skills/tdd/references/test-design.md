# Test design: specifying behavior, choosing a level, staying deterministic

SKILL.md keeps a one-line rule for each topic. This file has the detail: how to write a test that reads as a specification, which level a test belongs at, and how to remove each source of nondeterminism. The rules are language-neutral. Runner-specific tools are in the language references.

## Write tests that specify behavior

- **Test through the public interface.** Assert on results a caller can observe:
  - return values
  - state readable through the public API
  - effects at a system boundary: a row written, a message published, a request sent

  Litmus test: would a behavior-preserving refactor break this test? If so, the test is coupled to the implementation, not the behavior.
- **Arrange-Act-Assert.** Build the inputs, perform one action, then check the outcome, with a blank line between the three parts. Given/When/Then is the same structure. More than one act usually means more than one behavior, so split the test.
- **One behavior per test.** Several assertions are fine when they describe one outcome, such as the status and body of one response. Separate behaviors go in separate tests, so that a failure names the broken one.
- **Name tests as specifications.** State the behavior and its condition, so the list of failing names reads like a list of broken requirements. Good names:
  - `test_rejects_coupon_after_expiry`
  - `it("charges shipping only below the free-shipping threshold")`
  - `TestSlugify_CollapsesRepeatedSeparators`

  Bad names: `test_coupon2`, `it("works")`.
- **Write the assertion first** and work backwards to the arrange step. It keeps the test focused on the outcome rather than the setup.
- **Compute expected values independently.** Derive them from the requirement, by hand, or with a simpler oracle. Never paste in the output the code just produced, because then the test only checks that the code does what it does. The one deliberate exception is a characterization test (SKILL.md, "When TDD is a poor fit"), which records current behavior on purpose and is labeled as such.
- **Keep logic out of tests.** Loops and conditionals that compute expectations can share the bug they are meant to catch. For many examples of one rule, use the runner's parametrized or table-driven form (shown in each language reference).

## Put each test at the right level

Test at the lowest level that can observe the behavior with confidence. Move up a level only when the risk lives in the wiring between parts.

| Level | What it exercises | Use it for | Cost |
|---|---|---|---|
| Unit | One unit of behavior in memory, with no I/O | Domain rules, calculations, parsing, validation, state machines | Milliseconds. Most tests should be here, and the suite must run in seconds |
| Integration | Your code plus a real dependency you control (database, filesystem, queue, your own HTTP layer) | Queries, transactions, serialization, migrations, adapter code that wraps a third party | Slower. Use the real engine (a container or temp instance), not a different in-memory engine with different semantics |
| Contract | The agreement between your service and a provider or consumer | Service boundaries owned by different teams, and keeping your own fakes honest | Moderate. Catches drift between a fake and the real thing |
| End-to-end | The deployed system through its UI or public API | A handful of critical user journeys | Slow and prone to flakiness. Keep them few |

The TDD loop works at every level; only the cycle time changes. If the unit suite takes minutes, nobody runs it after every small step, and the loop dies. Treat a slow unit suite as a defect worth fixing.

A quick way to place a test: ask what would have to be wrong for it to fail. If the answer is "a rule in our code", it is a unit test. If the answer is "the way our code talks to the database (or queue, or HTTP layer)", it is an integration test. If the answer is "the other team changed their API", it is a contract test.

## Keep tests deterministic

A test that sometimes fails teaches the team to ignore red, and that undoes the point of TDD. Remove the source of variation rather than adding retries.

| Source | Fix |
|---|---|
| Wall-clock time | Inject a clock or pass `now` in, or use the runner's fake timers. Never assert against the real "now" |
| Timers and sleeps | Advance fake time, or wait on a condition with a timeout. Never `sleep` and hope |
| Randomness | Inject the random source or seed it. Assert properties (in range, unique, length) rather than specific draws |
| Ordering | Each test builds its own state. Compare unordered results as sets, or sort them first. Run with a shuffled order to flush out hidden dependencies |
| Network | No real external calls in unit tests. Use a fake behind your own interface, or a local stub server. Make an unexpected outbound request fail the test, not just log a warning |
| Concurrency | Synchronize on explicit signals (channels, latches, awaited promises). Use the language's race detector or virtual-time tools |
| Environment | Pin the timezone and locale. Use temp directories. Set and restore env vars per test. Avoid shared global state |

Design the seam in from the first test: a clock or random source passed in as an argument costs nothing up front, and retrofitting one later is a refactor.

Quarantining a flaky test is a tracking step, not a fix. When an existing test is already flaky and the cause is unknown, treat it as a debugging task (the `implementation:debug-root-cause` skill, if installed) rather than a TDD cycle.
