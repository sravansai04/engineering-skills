# Building a Safety Net for Legacy Code

Read this when the code you're about to refactor has no tests, thin tests, or tests that run the code without checking its results. The goal is not good tests. The goal is a quick, reliable alarm that goes off when behavior changes. Better tests can come later, through `implementation:tdd`.

## Contents

1. Decide what "behavior" to pin
2. Characterization tests, step by step
3. Golden-master (approval / snapshot) tests
4. Making output deterministic
5. Getting untestable code into a harness
6. Measuring the net: coverage and mutation testing
7. When you can't build a net
8. After the refactor

---

## 1. Decide what "behavior" to pin

List the observable outputs of the code you'll touch:

- Return values, and the exceptions and errors raised for bad input.
- State changes: database rows, files written, in-memory state other code reads.
- Outbound calls: HTTP requests, published messages, emails, and the arguments they carry.
- Output that someone consumes: rendered HTML, reports, CSV exports, API responses, and log lines that alerts depend on.

Anything on this list that the net doesn't observe can change without anyone noticing. Pin what the refactor could plausibly disturb and skip what it can't reach.

## 2. Characterization tests, step by step

A characterization test records what the code *does*, not what it *should* do.

1. Call the unit with a realistic input.
2. Assert against a value you know is wrong, such as `"???"` or `-1`.
3. Run the test. The failure message shows the actual value.
4. Paste the actual value in as the expected value. Name the test after the observed behavior.
5. Repeat for each branch and boundary (empty, zero, negative, null, maximum, unusual characters) until coverage of the code you'll touch is high (section 6).
6. If a value looks wrong, **pin it anyway**. Add a comment and an issue link. Fixing it now turns the refactor into a behavior change.
7. **Except** when the wrong value is a security vulnerability (an authorization bypass, an injection) or active data loss or corruption. Then stop characterizing. Report it through the security or incident process, not a public issue tracker or a comment that explains it, and fix it first in its own change; refactor on top of the fix afterwards. Never commit a test that asserts an unfixed exploitable behavior in a repo whose readers you don't control: the test, its comment and the issue together are a disclosure.

```python
# Characterization: pins current behavior, not intended behavior.
def test_discount_pins_current_behavior():
    assert legacy_discount(total=0, tier="gold") == 0
    assert legacy_discount(total=100, tier="gold") == 15.0
    # Tier match is case-sensitive today, so "GOLD" gets no discount.
    # Possibly a bug: ISSUE-123. Do not change during the refactor.
    assert legacy_discount(total=100, tier="GOLD") == 0
```

Commit these tests on their own, passing against the unmodified code, before any refactoring commit.

## 3. Golden-master (approval / snapshot) tests

When the surface is big, or its output is large (a report, rendered markup, a computed schedule), run many inputs through the code, serialize everything it produces into one file, and fail on any difference. You review the output once, then the tool guards it.

```javascript
// Jest or Vitest: one snapshot covering many input combinations
test("formatInvoice golden master", () => {
  const lines = [];
  for (const currency of ["USD", "EUR", "JPY"])
    for (const amount of [0, 0.005, 1, 999.995, -42])
      for (const locale of ["en-US", "de-DE"])
        lines.push(`${currency}|${amount}|${locale} => ${formatInvoice({ currency, amount, locale })}`);
  expect(lines.join("\n")).toMatchSnapshot();
});
```

```go
// Go: golden file under testdata/ (the go tool ignores that directory when building).
// The -update flag is a convention you define yourself; it is not built into go test.
var update = flag.Bool("update", false, "rewrite golden files")

func TestRenderReport_Golden(t *testing.T) {
	got := RenderReport(fixtureInput())
	path := filepath.Join("testdata", "report.golden")
	if *update {
		if err := os.WriteFile(path, []byte(got), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	want, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if got != string(want) {
		t.Errorf("output differs from %s; diff before updating", path)
	}
}
```

Tools by stack:

| Stack | Tool | Notes |
|---|---|---|
| JS / TS | Jest or Vitest snapshots | `toMatchSnapshot()`, `toMatchInlineSnapshot()`; update with `-u` |
| Python | `syrupy` (pytest plugin) | `snapshot` fixture; update with `pytest --snapshot-update` |
| Python | `approvaltests` | `verify(...)`, plus `verify_all_combinations` for combinatorial inputs |
| Java, C#, C++ and others | ApprovalTests family | Same approve-a-file workflow across languages |
| .NET | Verify | Built-in scrubbers for GUIDs, dates and paths |
| Rust | `insta` | `assert_snapshot!` / `assert_debug_snapshot!`; review with `cargo insta review` |
| Go | Golden files in `testdata/` | See the example above |
| PHP | `spatie/phpunit-snapshot-assertions` | `assertMatchesSnapshot()` and variants |

Rules that keep golden masters useful:

- **Never regenerate a snapshot inside a refactor commit.** A diff means behavior changed. Investigate it, revert the step, or (if the change really is intended) move it into a separate behavior-change commit.
- **Run snapshot suites in CI mode during a refactor.** Outside CI, Jest and Vitest write any snapshot they can't find and pass the test. Snapshots are keyed by test file and test name, so renaming or moving a test, which counts as a structural edit, orphans the old snapshot and silently creates a fresh, passing one; a `toMatchInlineSnapshot()` with no argument rewrites the test source the same way. `jest --ci`, or `CI=true` for both Jest and Vitest, makes a missing snapshot fail instead. Check the run summary for "written" or "obsolete" snapshot counts, which mean a test moved or was renamed, and move the `__snapshots__` file along with its test file. Other tools are stricter by default: syrupy fails on a missing snapshot unless run with `--snapshot-update`, insta stages new snapshots as `.snap.new` files for review instead of accepting them, and an approval-test "received" file never replaces the "approved" one on its own.
- **Keep the output readable**, one case per line with its inputs, so a failure says *which* input changed.
- **Pick inputs deliberately.** Use boundary values, every enum or variant, combinations of the parameters that interact, and a sample of real production-shaped inputs with personal data removed. Add inputs until coverage of the code you'll touch is high.

### Capturing side effects

- Replace collaborators with fakes or spies that record calls. Snapshot the recorded calls alongside the return value.
- For database effects, use a disposable database or wrap each test in a rolled-back transaction, then snapshot the relevant rows.
- For outbound HTTP, use record-and-replay libraries (for example vcrpy, Polly.js, WireMock, go-vcr), so tests are deterministic and offline.

## 4. Making output deterministic

A golden master that flaps is worse than none, because people learn to ignore it. Remove the nondeterminism first:

| Source | Fix |
|---|---|
| Current time | Inject a clock, or freeze it: `jest.useFakeTimers()` with `jest.setSystemTime()`, `vi.useFakeTimers()`, or Python's `freezegun` / `time-machine` |
| Random values, UUIDs | Seed the generator or inject a deterministic one; otherwise scrub the values to placeholders |
| Unordered collections | Sort them before serializing (hash maps and sets, Go map iteration, database rows without `ORDER BY`) |
| Time zone, locale | Pin them in the test environment (for example `TZ=UTC`) and set the locale explicitly |
| Floating-point formatting | Format to a fixed precision in the serialized output |
| Paths, hostnames, line endings, memory addresses | Scrub or normalize them |
| Concurrency | Run the code single-threaded in the test, or wait for completion and sort the results |

If you have to modify production code to inject a clock or RNG, do it as a tiny, tool-driven refactor first (section 5) and commit it on its own.

## 5. Getting untestable code into a harness

Legacy code often can't be instantiated in a test: hard-wired database connections, static singletons, `new` calls deep inside. You need a **seam**, a place where behavior can be substituted without editing the code under test. Common kinds:

- **Object seam:** pass the dependency in (constructor or parameter), or override a method in a test subclass.
- **Module or link seam:** substitute at import or link time (module mocking, a test implementation chosen by build config or DI).
- **Configuration seam:** select a fake implementation through configuration.

Minimal dependency-breaking moves are acceptable *before* tests exist, as long as they're tiny and preferably tool-driven, with the compiler as your check:

- **Parameterize the constructor:** add a constructor parameter for the dependency, and keep the old constructor delegating with the real default.
- **Extract an interface** from a concrete collaborator, so a fake can implement it.
- **Subclass and override:** move the problematic call into its own method, then override it in a test subclass.
- **Wrap a static or global** behind an instance method or small adapter that tests can replace.

Commit each of these on its own, before the characterization tests that depend on it.

## 6. Measuring the net: coverage and mutation testing

**Coverage** tells you which code the tests *execute*. Look at the files you'll touch, and look for branch coverage, not just lines.

| Stack | Command (scope it to the module you're touching) |
|---|---|
| Python (pytest-cov) | `pytest --cov=yourpkg.orders --cov-branch --cov-report=term-missing tests/orders` |
| Jest | `npx jest --coverage --collectCoverageFrom='src/orders/**' src/orders` |
| Vitest | `npx vitest run --coverage` (requires `@vitest/coverage-v8` or `@vitest/coverage-istanbul`) |
| Go | `go test -coverprofile=cover.out ./internal/orders/...` then `go tool cover -func=cover.out` (statement coverage, not branch) |
| Rust | `cargo llvm-cov` (cargo-llvm-cov) or `cargo tarpaulin` |
| JVM | JaCoCo: Gradle `jacoco` plugin (`./gradlew test jacocoTestReport`) or `jacoco-maven-plugin` |
| .NET | `dotnet test --collect:"XPlat Code Coverage"` (coverlet collector) |
| Ruby | SimpleCov, started at the top of the test helper |
| PHP | `XDEBUG_MODE=coverage vendor/bin/phpunit --coverage-text` (needs Xdebug or PCOV) |

Prefer the project's own coverage task if one exists (look in CI config and task-runner files).

**Mutation testing** tells you whether the tests would *notice* a change. The tool makes small edits (flips a comparison, deletes a statement), reruns the tests, and reports which mutants survived. A surviving mutant in code you're about to refactor is a gap in the net. These runs are slow, so limit them to the files you'll touch.

| Stack | Tool | Invocation |
|---|---|---|
| JS / TS | StrykerJS | `npx stryker run` (limit with the `mutate` setting) |
| .NET | Stryker.NET | `dotnet stryker` |
| JVM | PIT (pitest) | `mvn org.pitest:pitest-maven:mutationCoverage`, or the Gradle pitest plugin |
| Python | mutmut | `mutmut run` |
| Rust | cargo-mutants | `cargo mutants` (`--file` or `--in-diff` to scope it) |
| PHP | Infection | `vendor/bin/infection` |

Without a tool, do it by hand. Make three or four deliberate breaks in the target code, check that each one turns a test red, and revert.

## 7. When you can't build a net

If the code genuinely can't be tested in the time available:

- **Don't refactor it.** Make the change you came to make, as small as possible, and record the debt.
- If you need to *add* behavior, **sprout** it: write the new logic as a new, fully tested function or class and call it from the legacy code with a one-line edit. Or **wrap** it: rename the old method, then create a new method with the original name that calls the old one plus the new behavior. Either way, new code is tested and old code is left alone.
- Restrict yourself to tool-driven refactorings whose correctness the tool guarantees (a rename within a statically typed, reflection-free scope, or extracting a pure expression), and say in the report that no net existed.

## 8. After the refactor

- Keep characterization tests that describe meaningful behavior. Rename them to state intent once you understand it.
- Large snapshot blobs are brittle long-term. Plan to replace them with focused, intent-revealing tests (`implementation:tdd`), in a separate change.
- File issues for every "pinned, possibly a bug" comment so they don't get lost. Security and data-corruption findings are the exception: they go through the private process in section 2, step 7.
