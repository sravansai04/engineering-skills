# Proving a simplification preserves behavior

A green test suite is evidence, not proof. It only speaks for the inputs it
exercises and the outcomes it asserts. This file covers what "behavior"
includes, the transformations that most often change it by accident, how to
build confidence when the tests are thin, and the checkpoint mechanics.

## Contents

1. Observable behavior checklist
2. Equivalence traps by transformation
3. Building confidence beyond the existing tests
4. Coverage commands
5. Checkpointing

---

## Observable behavior checklist

Ask these of every hunk in the final diff. A "yes" means the hunk is tier 2
or 3, not a pure simplification.

- **Outputs**: Could the return value differ in value, type, precision,
  ordering, or identity (same object versus a copy)?
- **Errors**: Could a different error escape, an error stop escaping, or an
  error's type, message, code, or exit status change? Messages count when a
  client parses them, a test matches them, or a user reads them.
- **Side effects**: Could writes (database, files, network, cache, queue)
  happen a different number of times or in a different order? Could an
  argument or shared state be mutated that was not before, or vice versa?
- **Timing semantics**: Eager versus lazy, sync versus async, sequential
  versus concurrent, retries, timeouts, cancellation.
- **Shared state and concurrency**: Could another thread, task, or request
  now interleave differently with this code? Did a check, read, or copy move
  out from under a lock, across an `await` or `yield`, or outside a
  transaction? Is a collection that used to be copied now returned, stored,
  or shared by reference, so that callers or other threads can see or mutate
  it? Single-threaded unit tests almost never catch these, so a "no" here
  must come from reasoning about the interleavings, not from a green run.
- **Resource lifecycle**: Is every lock released, handle closed, transaction
  committed or rolled back, span ended, on every path including early exits
  and errors?
- **Consumed observability**: Log lines matched by alerts, dashboards, audit
  pipelines, or support runbooks; metric names and labels; trace span names.
- **Public surface**: Exported names, signatures, default argument values,
  type definitions, serialized field names, names read by reflection,
  templates, routes, CLI flags, config and environment keys.
- **Performance class**: Big-O, allocations in hot paths, number of queries
  or network round trips. "Simpler" code that turns a set lookup into a list
  scan, or a batched query into one per item, is a regression.

## Equivalence traps by transformation

| Transformation | Trap | Example |
|---|---|---|
| Null check to truthiness | Truthiness also rejects zero, empty string, false, and (in Python) empty collections | Python `if x is not None` vs `if x`; JS `x != null` vs `if (x)` |
| `??` to `\|\|` (or the reverse) | `\|\|` replaces every falsy value, `??` only null and undefined | `count \|\| 10` is 10 when count is 0; `count ?? 10` is 0 |
| Loose to strict equality | Coercion cases change | JS `"1" == 1` is true, `"1" === 1` is false |
| Value versus identity equality | Works in tests, fails at scale | Java `Integer` `==` is true only inside the cached range (-128 to 127 by default); Python `is` on ints and strings is an implementation detail |
| Early return or guard clause | Skips cleanup the original reached | Manual `unlock()` / `close()` after the early exit; `defer`, `finally`, `with`, `using` are safe |
| Inverting a compound condition | De Morgan errors; boundary errors | `!(a && b)` is `!a \|\| !b`; `>=` inverts to `<` |
| Reordering checks | A different error wins when several apply; a check with a side effect runs a different number of times | Validation that returns the first failure |
| Merging two loops or hoisting a call | Side effects interleave differently; a non-pure call now runs once instead of per iteration | Hoisting `now()` or `next_id()` out of a loop |
| List to generator, eager to lazy | Second iteration yields nothing; side effects run later or never | Python generators, Java streams (single use), C# `IEnumerable` LINQ queries re-run on every enumeration, Kotlin sequences |
| Copy to in-place (or the reverse) | Callers or other threads holding a reference see mutation, or stop seeing it | Python `sorted(x)` vs `x.sort()`; JS spread vs `push`; returning an internal list instead of a copy; storing a caller's list without copying it; iterating a shared collection without the snapshot that protected it from concurrent changes |
| List dedupe to set | Order changes | Python `set` and Java `HashSet` are unordered and Go map iteration is randomized; JS `Set` keeps insertion order; in Python, `list(dict.fromkeys(xs))` dedupes while keeping order |
| Hand-rolled helper to stdlib or shared helper | Edge cases differ | `itertools.groupby` only groups consecutive keys; rounding: Python `round(2.5)` is 2 (half to even), JS `Math.round(2.5)` is 3 and `Math.round(-2.5)` is -2 |
| Removing a catch | Callers now see errors they never saw; or, for a rethrow-only clause, a broader sibling handler below it now catches what used to escape | Any catch that returned a default; Python `except ValueError: raise` before `except Exception: return None`, or the Java/C# equivalent with `catch (IOException e) { throw e; }` before `catch (Exception e)` |
| Removing a repeated check or read | A lock, `await`, transaction, or I/O call between the two makes the second one see different state | Double-checked locking; re-reading a row after `SELECT ... FOR UPDATE`; re-checking `this.conn` after `await this.connect()` |
| Dropping `await` | Error handling, ordering, and resource lifetime change | `return await` inside `try`/`catch`/`finally` or in a block holding `using`/`await using` declarations (the resource is disposed before the promise settles); a fire-and-forget call that used to be awaited |
| Sequential awaits to concurrent (or the reverse) | Ordering, rate, and failure semantics change | `Promise.all` starts everything at once and rejects on the first failure |
| Removing `async` from a JS function | Return type changes from a promise to a value, and a throw in the body now escapes synchronously instead of rejecting | Callers using `.then`/`.catch` or `instanceof Promise` break; `const p = f(); try { await p } catch {}` and `Promise.all([f(), g()])` now see an uncaught synchronous exception. Safe only if the body cannot throw, or every caller writes `await f()` directly |
| Deleting an unused import | Importing runs the module in Python, Ruby, plain JavaScript, and TypeScript under `verbatimModuleSyntax` or `preserveValueImports`; in a package `__init__.py`, `__all__`, or index file the import is a re-export | `import myapp.signals` registers handlers; `import readline` changes `input()`; a polyfill import; Go's blank import `_ "image/png"` registers a decoder |
| Deleting a branch on a constant | The constant differs between builds, platforms, or bundler modes | `#if DEBUG`, Rust `cfg!(debug_assertions)` and `#[cfg(feature = "...")]`, `process.env.NODE_ENV`, `__DEV__`, `import.meta.env.*`, Go build tags, per-platform generated constants |
| Renaming a private field | Reflection-driven code reads names | Reflection-based JSON serializers, ORMs, template engines, Python `dataclasses.asdict` |
| Changing a default parameter | Evaluated differently or shared | Python mutable defaults are created once and shared across calls |
| Replacing a numeric idiom | Range, sign, or NaN behavior differs | JS `~~x` wraps beyond 32 bits and maps NaN to 0, `Math.trunc` does not; integer division in Python (`//`) floors toward negative infinity, in C, Java, and Go it truncates toward zero |

## Building confidence beyond the existing tests

Use these when a tier 1 edit touches code the suite barely covers, or when a
rewrite is large enough that line-by-line reasoning is unreliable.

### Characterization test

Write it after the checkpoint and before any simplification, as batch 0, so
the final diff shows it and the report can list it under "Tests added". Pin
the current behavior: call the code with representative inputs and the edge
cases from the trap table (empty, null, zero, negative, unicode, duplicates,
very large, failing dependencies) and assert whatever it returns or raises
today, even if that looks odd. Run it green against the original, stage it,
simplify, and run it again. Afterwards, ask the user whether to keep it; it
usually earns its place as documentation. (See `implementation:tdd` for
test-writing discipline.)

### Differential test against the old implementation

For a rewritten function, keep the original temporarily under another name
and let a property-testing library compare them on generated inputs. Delete
the old copy once the comparison passes.

```python
# Python, Hypothesis
from hypothesis import given, strategies as st

@given(st.lists(st.integers()), st.integers(min_value=1, max_value=50))
def test_chunk_matches_original(items, size):
    assert chunk(items, size) == _chunk_original(items, size)
```

```ts
// TypeScript, fast-check
import fc from "fast-check";
test("slug matches original", () => {
  fc.assert(fc.property(fc.string(), (s) => slug(s) === slugOriginal(s)));
});
```

```go
// Go native fuzzing: go test -run='^$' -fuzz=FuzzNormalize -fuzztime=30s ./pkg/text
func FuzzNormalize(f *testing.F) {
    f.Add("Hello, World!")
    f.Fuzz(func(t *testing.T, s string) {
        if got, want := Normalize(s), normalizeOriginal(s); got != want {
            t.Fatalf("Normalize(%q) = %q, want %q", s, got, want)
        }
    })
}
```

The same idea works with jqwik (Java), FsCheck (.NET), and proptest or
quickcheck (Rust). A failing case is a found behavior difference: either
revert, or keep the new behavior as an explicit tier 2 change.

### Mutation spot-check

To learn whether the tests would notice a mistake in a line you simplified,
break it on purpose (flip a comparison, delete the line), run the relevant
tests, and confirm something fails. Then restore it. If nothing fails, the
line is effectively untested; name it on the report's Confidence line and
lower your confidence in that edit. For critical code, mutation-testing tools automate this
(`mutmut run` for Python, `npx stryker run` for JavaScript and TypeScript,
`cargo mutants` for Rust, PIT for the JVM), but they are slow; scope them to
the touched files.

## Coverage commands

Run these for the touched files only, and look at whether the specific lines
you plan to change are executed.

| Stack | Command | Note |
|---|---|---|
| Python | `pytest --cov=<package> --cov-report=term-missing` | needs pytest-cov; lists missed line numbers |
| JS/TS (Vitest) | `npx vitest run --coverage` | needs a coverage provider package installed |
| JS/TS (Jest) | `npx jest --coverage` | |
| Go | `go test -coverprofile=cover.out ./... && go tool cover -func=cover.out` | `go tool cover -html=cover.out` for line view |
| Rust | `cargo llvm-cov` | needs cargo-llvm-cov |
| .NET | `dotnet test --collect:"XPlat Code Coverage"` | writes a Cobertura report per test project |
| JVM (Gradle + JaCoCo) | `./gradlew test jacocoTestReport` | needs the `jacoco` plugin applied |

## Checkpointing

The default in SKILL.md uses the git index as a ratchet: stage the
pre-simplification state, advance it with `git add` after each green batch,
and roll a red batch back with `git restore`. `git stash create` records a
snapshot commit of the starting point without touching the working tree, the
index, or the stash list, so `git diff <SNAP>` shows the total simplification
delta at the end.

Edge cases:

- **The index already holds deliberately staged work.** Staging the whole
  scope would merge the user's partial staging. Ask first. Good options: the
  user commits their work, or you work in a separate worktree (see
  `workflow:git-worktrees`). Avoid `git add -N` (intent-to-add) as a workaround:
  `git stash create` refuses to snapshot an index with intent-to-add entries.
- **The user wants commits.** One commit per batch, named by kind
  (`simplify: remove dead code`), gives the reviewer a per-kind history. Only
  with their go-ahead; squash later if they prefer one commit.
- **Shell state does not persist between tool calls.** Print the snapshot id
  and paste it literally into later commands instead of relying on a
  variable.
- **No version control.** Copy the scope aside before editing
  (`cp -R src /tmp/simplify-baseline-src`) and keep a second copy that you
  refresh after each green batch (`rm -rf /tmp/simplify-green-src && cp -R src /tmp/simplify-green-src`).
  Roll back a red batch by copying the affected files back from the green
  copy, and compare at the end with `diff -ru /tmp/simplify-baseline-src src`.
- **Untracked new files.** `git stash create` only snapshots tracked content.
  Staging the scope first (the default flow) makes new files tracked, which
  is why the default stages before it snapshots.
