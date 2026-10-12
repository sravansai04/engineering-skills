---
name: tdd
description: "Builds code test-first in a red-green-refactor loop, including regression-test-first bug fixes and tests for untested code, and answers test-design questions (what to mock, which level). Use for \"use TDD\", \"write the test first\", \"write a regression test for this bug\", \"write tests for this module\". Not for a whole ticket (build-feature), e2e tests (browser-testing), an unexplained or flaky failure (debug-root-cause), restructuring (refactor-safely), or red CI (ci-failure-triage)."
---

# Test-Driven Development

Grow code in small, verified steps. Each test states the next behavior wanted; watching it fail proves it can detect that behavior's absence. Write just enough code to pass, then clean up while green. A test seen going red then green is evidence; one never seen failing is only a hope. Code that is awkward to test is usually awkward to use, so the loop also shapes design.

If the skill's arguments (in Claude Code, typed arguments appear after ARGUMENTS: at the end of this skill) name a behavior or a bug, use them to seed the test list or the reproduction. Otherwise take the request from the conversation.

## Workflow

### 0. Pick the mode

- **Build new behavior:** sections 1, 2, 3, then finish (6) and report (7).
- **Fix a reproducible bug:** section 1, then section 4 using the section 3 cycle for the fix, then 6 and 7. If the bug won't reproduce or the cause can't be located, start with the `implementation:debug-root-cause` skill if installed, or reproduce it first by hand.
- **Add tests to existing code** ("write tests for this module", an untested helper, no behavior change wanted): section 1, then section 5, then 6 and 7. Before a refactor, the characterization tests in `implementation:refactor-safely` are the better fit.
- **Answer a test-design question** (what to double, which level, how to make a new test deterministic): answer from the Test design rules below and the matching reference, show one example test written to fail first, and skip the baseline and the report.

The Test design rules apply in every mode.

### 1. Set up before the first test

1. **Find the project's own test command.** Don't assume a stack. Check task runners (`package.json` scripts, `Makefile`, `justfile`, `Taskfile.yml`), then language config (`pyproject.toml`, `tox.ini`, `go.mod`, `Cargo.toml`, `pom.xml`, `build.gradle*`, `*.csproj`, `Gemfile`), then CI workflow files, then `CONTRIBUTING.md` or `README.md`. Prefer the project's wrapper (`npm test`, `make test`, `./gradlew test`), since it often sets env vars, config, or test databases a bare runner call misses. With npm, pass runner args after `--`: `npm test -- -t "name"`.
2. **Learn to run a single test.** Each test gets run dozens of times, so a run must take seconds. Adapt the table below to the project's wrapper.
3. **Baseline the scope you will run at finish:** the full suite if it's reasonably fast, otherwise the affected packages plus the finish-time command. If anything is already red, record the failing test IDs and tell the user. Continue only if those failures are unrelated and the user agrees. Leave them out of your red/green signal and don't fix them along the way, since that muddies the change.
4. **Read the language reference** for the stack (see Reference files). If none matches (Rust, JVM, .NET, Ruby, a JS runner other than Jest or Vitest), apply this file's rules with the project's own runner.

| Stack | Run one test | Useful extras |
|---|---|---|
| Python / pytest | `python -m pytest tests/test_cart.py::test_empty_cart_total_is_zero` | `-x` stop at first failure, `--lf` rerun last failures, `-k "expr"` |
| Jest | `npx jest src/cart.test.ts -t "empty cart"` | `--onlyFailures`, `--watch` |
| Vitest | `npx vitest run src/cart.test.ts -t "empty cart"` | `npx vitest` watch mode, `--bail 1` |
| Go | `go test ./cart -run '^TestTotal$' -v` | keep `-v` to see your test run, `-race`, `-shuffle=on` |
| Rust / cargo | `cargo test empty_cart` (substring filter) | `-- --nocapture` |
| Java / Maven | `mvn -Dtest=CartTest#emptyCartTotalIsZero test` (single module) | Multi-module, from the root: `mvn -pl <module> -am -Dtest=CartTest#emptyCartTotalIsZero -Dsurefire.failIfNoSpecifiedTests=false test`, or run inside the module |
| Java, Kotlin / Gradle | `./gradlew test --tests 'com.example.CartTest.emptyCartTotalIsZero'` | `./gradlew :module:test --tests ...` in a multi-project build |
| .NET | `dotnet test --filter "FullyQualifiedName~CartTests"` | |
| Ruby / RSpec | `bundle exec rspec spec/cart_spec.rb:42` | `--only-failures` (needs `example_status_persistence_file_path`) |

### 2. Write the test list

Before any test code, list the behaviors the change needs, one line each, phrased as outcomes:

- Good: "total of an empty cart is zero", "rejects a coupon past its expiry date"
- Bad: "add a `discounts` dict", "write the `applyCoupon` loop"

Include degenerate cases, boundaries, and errors. If there are acceptance criteria or a plan (for example from the `implementation:plan-feature` skill), derive the list from them. Show the list to the user when scope is non-trivial: it's the cheapest moment to catch a misunderstanding.

When a new case comes up mid-cycle, add it to the list and finish the current cycle first.

### 3. The cycle

Repeat red, green, refactor until the list is empty. A cycle should take minutes. If a step stays red much longer, it's too big. Undo only the edits made since the last green (revert your own hunks, or restore the previous contents of the files you touched) and pick a smaller test. Never run a tree-wide `git reset`, `restore`, `checkout`, `stash` or `clean` while the tree holds changes you didn't make.

#### Red: one failing test, failing for the right reason

1. **Pick the next test:**
   - **Degenerate case first** (empty, zero, none, one item). It forces the interface into existence while the logic is trivial. If it passes against a zero-value stub, start with the simplest non-trivial case and return to it later.
   - **Then** the simplest happy path, the case that forces generalization, boundaries (at, just below, just above the limit), then errors and combinations.
   - **Stay one small step from the current code.** If passing a test needs a big jump, write a smaller one first.
   - **Once the basics exist, pick the test whose outcome is least certain.** It teaches the most.
2. **Write exactly one test.** Name it as a specification, use Arrange-Act-Assert, assert through the public interface (Test design rules).
3. **Predict the failure, then run the single test.** For example: "expected 0, got None".
4. **Check the failure is the right one:**
   - **Right:** the assertion fails because the behavior is missing.
   - **Also right:** the code under test raises during the act because the behavior is missing (`KeyError`, `ValueError`, `TypeError`, a null dereference, a panic). Accept it if predicted and the stack trace points into production code. Prefer an assertion failure when a trivial stub gets you there.
   - **Not yet:** a compile error, import error, or missing symbol. Legitimate first red in typed languages, but it proves nothing about the assertion. Add the smallest stub that compiles and rerun.
   - **Wrong:** a typo, broken fixture, missing dependency, or an exception from test code or setup rather than the act. Fix the test and rerun. Don't touch production code yet.
5. **If the test passes immediately, find out why.** Confirm it was collected: the test count should rise by one (Go prints no count, so use `-v` and look for its `=== RUN` line). Tests go missing outside the naming pattern, without an `await`, or with the assertion in a callback that never runs. If it was collected, the behavior exists already or the test misses its target: break the production code on purpose (invert a condition, return a wrong constant), watch the test fail, restore. Never move on with a test you haven't seen fail. Tests written after the code (section 5) and characterization tests pass on their first run by design, so they get the deliberate break instead.

#### Green: the simplest code that passes

1. **Write the least code that makes this and all previous tests pass**, using one of:
   - **Fake it:** return a constant when the next step isn't obvious. Refactoring or the next test removes it.
   - **Obvious implementation:** write the real logic when confident. On an unexpected red, drop back to faking.
   - **Triangulate:** when the general rule is unclear, add a second example so a hardcoded answer can't pass both. Generalize once two examples demand it.
2. **Don't add code no test demands yet.** Put the behavior on the list. Untested "while I'm here" branches are where defects hide.
3. **Run the test, then the surrounding suite.** A pass that breaks an earlier test isn't green.
4. **Leave the test alone.** If the test was wrong, go back to red deliberately: fix it, see it fail correctly, continue. Weakening, deleting, or skipping an assertion to get green defeats the loop.

#### Refactor: improve the design with everything green

1. **Only refactor on green, and add no behavior while refactoring.** Mixing the two means a failure can't say which change broke things.
2. **Remove duplication,** including between the test and the code (the faked constant). Then improve names, extract functions, simplify conditionals.
3. **Refactor tests too.** Move noisy setup into builders or fixtures, but keep each test readable on its own: clear, slightly repetitive tests beat clever helpers that hide what is checked.
4. **Run the tests after each small step.** If one breaks, the refactor changed behavior or the test is coupled to implementation. Undo the step and find out which.
5. **Hand off big restructurings** (splitting a module, changing a data model) to the `implementation:refactor-safely` skill if installed. Otherwise keep the same discipline: small steps, green after each.

Commit only if the user wants commits; then each green, or each finished list item, is a cheap rollback point (the `workflow:commit-message` skill in the workflow plugin covers wording, if installed). Otherwise the report's Cycles table records the green checkpoints.

#### Optional outer loop for user-visible features

For a feature spanning several units, first write one failing acceptance or integration test for the whole feature. Keep it red while inner unit cycles build the pieces. The feature is done when it passes.

### 4. Bug fixes: reproduce first

1. **Write a failing test that reproduces the reported symptom** at the lowest level that shows it. If it won't reproduce or the cause can't be located, switch to the `implementation:debug-root-cause` skill (if installed) and come back with a reproduction.
2. **Confirm it fails the way the report describes.** A different failure reproduces a different bug. Record the observed failure for the report.
3. **Make the smallest fix that turns it green,** then run the surrounding suite.
4. **Name the test after the behavior, not the ticket** (`test_total_ignores_removed_items`). Put the ticket reference in a comment.
5. **Look for siblings.** The same mistake often lives in parallel code paths. Add a failing test for each one found, and record where you looked.
6. **Keep the test.** It guards against the regression coming back.

### 5. Existing code: add tests after the fact

The code already exists, so a test cannot fail first by itself. Make every test earn its place anyway:

1. **Write the behavior list from the code and its callers,** not from the implementation's branches alone: what callers rely on, the inputs they actually pass, the errors they handle. Add the degenerate cases and boundaries the code should handle. Show the list when scope is non-trivial.
2. **Write each test against the public interface,** with expected values derived from the requirement, a caller's use, or the docs, never pasted from the code's output.
3. **Prove each test can fail.** Mutate the production line it guards (invert a condition, return a wrong constant, drop a branch), watch the test fail for the right reason, then restore the line by hand (red step 5). A test that survives the mutation checks nothing.
4. **Report suspected bugs instead of encoding them.** When the code's actual behavior looks wrong (a boundary off by one, a swallowed error), do not write a test that pins it. List it in the report, or write the test for the intended behavior marked as an expected failure if the runner supports one, and ask whether to fix it now (section 4).

### 6. Finish

1. Rerun the baseline scope from section 1 (the full suite when fast). Nothing outside the recorded baseline failures may fail.
2. Run the project's linters, formatter, and type checker, found the same way as the test command.
3. Review the diff of your own edits, leaving aside changes you didn't make. Every production branch you added should be covered by a test that went red first. If not, add a test or delete the branch.
4. Record anything left on the test list as a follow-up.
5. For a full pre-merge check, hand off to the `implementation:verify-before-done` skill if installed. Otherwise the steps above are the check; report their results.

### 7. Report

End with the report under Report format, so the user can audit the loop rather than trust it.

## Report format

```
## TDD report: [feature or bug]

Test command: [exact command used]
Baseline before changes: [N passed; pre-existing failures by test ID, or "all green"]

Test list:
- [x] [behavior 1]
- [ ] [deferred behavior]: [why it was deferred]

Cycles:
| # | Test (spec name) | Red: observed failure | Green: change made | Refactor |
|---|------------------|-----------------------|--------------------|----------|
| 1 | empty cart total is zero | AssertionError: expected 0, got None | return 0 | none |
| 2 | total sums item prices | expected 15, got 0 | sum prices | removed faked constant |

Reproduced symptom (bug fixes): [observed failure, matching the report]
Siblings checked (bug fixes): [paths searched and result]
Final run: [result, compared with the baseline]; lint/type check: [result]
Doubles used: [what was faked or mocked, and why it's a boundary]
Follow-ups: [untested risks, deferred items, flaky or slow tests noticed]
```

For a test that passed on arrival and was proven by a deliberate break, say so in its Red cell, e.g. "passed on arrival; failed with the guard removed". When adding tests to existing code, every Red cell records that break, and suspected bugs go under Follow-ups.

## Test design rules

### Write tests that specify behavior

- Test through the public interface. A behavior-preserving refactor should never break a test.
- Arrange-Act-Assert, with one act and one behavior per test.
- Name each test as a specification of behavior and condition (`test_rejects_coupon_after_expiry`, not `test_coupon2`).
- Compute expected values from the requirement, never by pasting the code's output. Characterization tests are the exception (When TDD is a poor fit, below).
- Keep loops and conditionals out of tests; use the runner's parametrized or table form.

Reasoning and examples: `references/test-design.md`.

### Put each test at the right level

Test at the lowest level that observes the behavior with confidence: **unit** for rules and calculations, **integration** for your code against a real dependency you control, **contract** for agreements across team boundaries, **end-to-end** for a few critical journeys (end-to-end and browser tests: `frontend:browser-testing`). Move up only when the risk lives in the wiring. A unit suite that takes minutes kills the loop; treat it as a defect. The level table is in `references/test-design.md`.

### Test doubles: real first, mock at your own boundaries

Prefer, in order: the real object, a **fake** (a working lightweight implementation, such as an in-memory repository), a **stub** (canned answers), a **mock or spy** (verifies calls). Each step down tests less of reality and couples the test more to how the code works.

- **Double only at architectural boundaries you own.** Define a small interface in your code for the outside world (clock, payment gateway, email sender, repository) and fake that. Don't mock a third-party client's classes: their behavior isn't yours to specify, so the mock encodes guesses. Wrap the library in a thin adapter covered by an integration test against the real thing or a local stand-in.
- **Mock outgoing commands; stub incoming queries.** "Exactly one confirmation email was sent" is a legitimate interaction test, because sending is the behavior. "A helper was called to fetch a value" is not; assert on what the code did with the value.

Before moving on, run the smell checklist in `references/test-doubles.md`, which also covers fake design and contract tests that keep fakes honest.

### Keep tests deterministic

A test that sometimes fails teaches the team to ignore red. Control each source of variation (wall-clock time, timers, randomness, ordering, network, concurrency, environment) by injecting or pinning it, never with retries or sleeps. Design the seam, such as an injected clock, in from the first test. Fixes per source are in `references/test-design.md`; runner tools are in each language reference. An existing test that is already flaky for an unknown reason is a job for the `implementation:debug-root-cause` skill, not a TDD cycle.

### When TDD is a poor fit and what to do instead

Change the order of work, not whether it gets tested.

- **Exploratory spikes** (unfamiliar API, feasibility question, performance experiment). Timebox throwaway code, write down what you learned, delete the spike, and rebuild with TDD. Promoted spike code imports the design debt tests would have prevented.
- **Legacy code with no seams.** Add characterization tests and seams first (the `implementation:refactor-safely` skill covers this), then resume TDD for the new behavior.
  - **Characterization tests deliberately break two rules.** They record what the code does today, so they pass on first run and take expected values from actual output. Prove each can fail by temporarily mutating the production code (red step 5). Label them as characterization in the name or a comment, so a later reader knows the value is recorded behavior, not a requirement.
- **Thin wiring and configuration.** Cover it with an integration or smoke test, not unit tests that restate the config.
- **Visual layout and UX feel.** Use review, screenshots, or visual regression tooling (end-to-end and browser tests: `frontend:browser-testing`). Still use TDD for the state and logic behind the view.
- **Generated code.** Test the generator or the contract, not the output.

### Common mistakes not covered above

- **Testing private methods.** It couples tests to structure and blocks refactoring. If a private piece deserves its own tests, extract it into a unit with a public interface.
- **Asserting on log text.** Log wording isn't a contract. When an audit event or metric *is* a requirement, inject the sink at a boundary and assert on structured fields.
- **Snapshot abuse.** A snapshot records whatever the code produced, so it never fails first, and big diffs get approved unread. Keep snapshots small, deterministic, and inline where possible; use targeted assertions for logic; never bulk-update without reading the diff.
- **Treating coverage as the goal.** Coverage shows what ran, not what was checked. When test strength is in question, mutation testing (Stryker for JS/TS, mutmut for Python, PIT for Java) shows whether tests catch changes.
- **Testing the framework,** such as asserting the ORM saves or the HTTP library parses JSON. Test your rules, plus one integration test that the wiring works.

## Related skills

- `implementation:debug-root-cause` when a failure won't reproduce or its cause can't be located.
- `implementation:refactor-safely` for restructuring beyond the refactor step, and `implementation:plan-feature` for work that needs a plan first.
- `implementation:build-feature` when the request is a whole ticket or feature rather than one unit.
- `frontend:browser-testing` for end-to-end and browser tests, and `workflow:ci-failure-triage` when a test passes locally but CI is red.
- `implementation:verify-before-done` for the full pre-merge check, and `workflow:commit-message` for commit wording.

Skills are named here as `plugin:skill`; an agent that lists skills by bare name knows each one by the part after the colon (`review-suite:pr-review` is `pr-review`). If a skill named here isn't installed, give the short version inline and list the deeper pass as a follow-up.

## Reference files

Read only what applies.

- `references/python.md`: Python projects. pytest collection gotchas, a worked cycle, parametrize, fakes, determinism tools.
- `references/typescript.md`: TypeScript or JavaScript with Jest or Vitest. A worked cycle, `test.each`, async pitfalls, cleanup between tests, fake timers, network interception that fails the test, snapshots.
- `references/go.md`: Go projects. Confirming a test ran, table-driven tests, a worked cycle, interfaces as seams, `httptest`, `testing/synctest`, `-race`, `-shuffle`.
- `references/test-doubles.md`: any stack. Read when isolating a dependency, designing a fake, writing a contract test, or checking for over-mocking.
- `references/test-design.md`: any stack. Read when naming or structuring tests, choosing a test's level, or removing a source of nondeterminism.

With no matching language reference, apply this file with the project's own runner plus the two stack-neutral references.
