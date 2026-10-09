# Equivalence Traps

Edits that look behavior-preserving but aren't. Skim this once per refactor. Re-check it for any step that moves code across a function, thread, transaction or module boundary, or that touches anything serialized or published.

Each row gives a trap, a typical way it bites, and how to catch it.

## Contents

1. Evaluation order and side effects
2. Values, identity and data shape
3. Control flow and errors
4. Concurrency, resources and context
5. Types, dispatch and modules
6. Compatibility surfaces
7. Non-functional behavior

---

## 1. Evaluation order and side effects

| Trap | How it bites | Catch it by |
|---|---|---|
| Hoisting out of a short-circuit | Extract Variable pulls `expensive()` or `user.profile.name` out from behind `&&`, `?.` or an `if`. It now runs, and maybe throws, when the condition is false | Check every operand of `&&` `\|\|` `?:` `??` and `if` guards before extracting |
| Duplicated evaluation | Inline Variable or Replace Temp with Query calls an impure or expensive expression twice: `now()`, random, I/O, an iterator `next()` | Only inline or query pure, cheap expressions |
| Argument evaluation order | Inline Function substitutes arguments into the body in a different order, or skips one, so side effects in arguments change | Bind side-effecting arguments to locals first |
| Lazy versus eager | Loop to pipeline, generator or stream defers work, so side effects, exceptions and timing move. Re-enumerating a lazy query (deferred LINQ, ORM query sets) can run it twice | Materialize explicitly when the old code was eager; check single-use iterators |
| Time of evaluation | Moving a `now()` or config read earlier or later changes its value | Capture it once and pass it in |

## 2. Values, identity and data shape

| Trap | How it bites | Catch it by |
|---|---|---|
| Truthiness and null checks | `if (x)` versus `x != null`, `\|\|` versus `??`, Python `if x:` versus `if x is not None:`. These differ for `0`, `""`, `[]` and `false` | Keep the exact predicate; add tests for falsy-but-valid values |
| Floating-point reassociation | Reordering a sum or factoring an expression changes the result in the last bits, and rounding then differs | Keep the operation order, or compare with a tolerance and confirm that's acceptable |
| Integer widths and division | A changed type changes overflow, truncation or division semantics | Keep the types; test the boundaries |
| Equality and hashing | Adding or moving fields changes `equals`/`hashCode`, so set and map membership changes. Kotlin data classes only use primary-constructor properties. Value versus reference semantics change identity checks | Test equality and collection membership explicitly |
| Field order as an API | Reordering dataclass or record fields changes positional constructors. Unkeyed struct literals in Go silently swap same-typed fields. `order=True` comparisons follow field order | Search for positional construction before reordering |
| Aliasing and mutability | A parameter object or encapsulated collection is now shared and mutated by several callees. Python's mutable default arguments | Make new value types immutable; return copies or read-only views |
| Iteration order | Swapping a list for a set or map, or Go map iteration, changes output order, then reports, snapshots and "first match" logic | Sort explicitly where order matters |
| Serialized shape | A renamed or moved field changes the JSON or column name; an unexported Go field stops being marshaled | Golden-master the serialized output; pin external names explicitly |

## 3. Control flow and errors

| Trap | How it bites | Catch it by |
|---|---|---|
| Early exits inside extracted blocks | `return`, `break` or `continue` inside an extracted block now exits the helper, not the caller | Extract only single-exit blocks, or return a signal value |
| Exception type, timing or message | Validation moves, so a different error surfaces first. A wrapper catches more broadly. Clients parse the error message or code | Pin error type and message in characterization tests |
| Cleanup skipped by guard clauses | Logging or cleanup at the old single exit no longer runs on early returns | Use `finally`, `defer` or `using`, or keep one exit |
| Default branches | Polymorphism or a lookup table drops the old `default` or `else` behavior for unknown values | Test an unknown key or variant explicitly |
| Assertions | A newly introduced assertion fires in production | Decide whether it's debug-only, or prove the invariant holds for real data |

## 4. Concurrency, resources and context

| Trap | How it bites | Catch it by |
|---|---|---|
| Lock or atomicity boundary | Code moved outside a lock or synchronized block. One read-modify-write split into two calls. Separate Query from Modifier breaks an atomic check-and-act | Keep the critical section intact; review every moved line that touches shared state |
| Transaction boundary | A write moved outside the transaction, or a read moved inside it (different isolation, longer locks) | Map the transaction scope before and after |
| Framework proxies | In proxy-based frameworks, an extracted method with a transactional, cached, async or security annotation called from the same class bypasses the proxy, so the annotation does nothing. Moving it to another component suddenly activates it | Know whether your framework uses proxies; test the annotated behavior itself |
| Thread or task context | Moving work to another thread, executor or async task loses thread-local context: request scope, logging context, security principal, locale | Propagate context explicitly; test from the new execution context |
| Missing `await` | An extracted async function is called without awaiting. The work becomes fire-and-forget, and a pending promise is truthy in conditions | Lint for floating promises or unawaited coroutines |
| Closures capturing loop variables | Late binding in Python lambdas; `var` in older JS. Go changed loop-variable scoping in 1.22, and the semantics follow the `go` version in `go.mod`, so moving loop code between modules on different versions changes it | Bind the value explicitly |
| Resource lifetime | Code using a resource moved out of a `with`, `using`, try-with-resources or `defer` scope (use after close), or a connection held longer (pool exhaustion) | Keep resource use inside its scope |

## 5. Types, dispatch and modules

| Trap | How it bites | Catch it by |
|---|---|---|
| Lost `this` / `self` | Extracting a method reference (`const f = obj.method`) or passing it as a callback unbinds `this` in JS | Bind explicitly or use arrow functions |
| Overload resolution | Moving, renaming or adding an overload changes which one is chosen (`remove(int)` versus `remove(Object)`) | Run the tests that cover each overload; prefer distinct names |
| Silent override loss | Renaming a base method or changing its signature means subclass methods stop overriding it | Require `override` keywords or annotations (compiler-enforced) |
| Implicit interface satisfaction | A Go type stops satisfying an interface after a method rename, and that's only visible at a runtime type assertion | Add compile-time assertions such as `var _ Iface = (*T)(nil)` |
| Convention-named hooks | Frameworks call methods by naming convention (test setup methods, lifecycle hooks, validation hooks), so a rename silently disables them | Check framework docs before renaming conventional names |
| Decorator or annotation metadata | Wrapping or moving a function drops metadata: Python's `functools.wraps`, `Function.name` in JS used by DI or logging, annotations not carried over | Verify metadata-dependent behavior (routing, DI, logging) |
| Import cycles and init order | Moving code between modules creates a cycle (`ImportError` on a partially initialized module in Python, undefined bindings or TDZ errors in JS) or changes import-time side effects | Import the module in isolation in a test; watch for module-level side effects |

## 6. Compatibility surfaces

| Trap | How it bites | Catch it by |
|---|---|---|
| Parameter names are API | Renaming a parameter breaks callers that pass it by name (Python, Kotlin, C#, Swift) | Treat parameter names of public functions as published |
| Source- versus binary-compatibility | Adding an optional or default parameter changes the compiled signature, and default values get baked into the caller in C#. Changing a return type, even to a subtype, changes the JVM method descriptor. Adding an abstract interface method breaks implementers | For published libraries, use overloads or default methods, and run an API-diff tool against the last release (below) |
| Visibility widening | Making something public to test it, or to move it, widens the attack surface and the API you now have to support | Test through the public surface; keep internals internal |
| Moving checks across trust boundaries | An extracted helper is called from a path that skipped the authorization check, or validation now runs after the data is used | Re-verify where authz and validation happen after moving code; see `review-suite:secure-code-review` |

**API-diff tools.** For a published package, an API diff against the last release is the strongest mechanical evidence that a refactor changed nothing public. A refactor should show zero non-additive changes; anything else is a breaking change and needs the deprecation path in `large-refactors.md`.

| Stack | Tool |
|---|---|
| Java / JVM | japicmp or Revapi (Maven and Gradle plugins), comparing against the previous release artifact |
| Rust | `cargo semver-checks` (cargo-semver-checks) |
| TypeScript | API Extractor: commit its `.api.md` report and review the diff |
| Go | `gorelease` (compares with the previous tagged version) or `apidiff` |
| .NET | Package validation: `<EnablePackageValidation>true</EnablePackageValidation>` plus `<PackageValidationBaselineVersion>` set to the last release, checked on `dotnet pack` |
| Python | `griffe check yourpackage --against <last-release-tag>` |

## 7. Non-functional behavior

| Trap | How it bites | Catch it by |
|---|---|---|
| Performance | Replace Temp with Query recomputes in a loop; a pipeline allocates intermediates; a moved DB call lands inside a loop (N+1); inlining bloats a hot path | Benchmark hot paths before and after; see `review-suite:performance-review` |
| Logging volume and text | Log lines moved into or out of loops; message text changed that alerts or parsers match on | Search alerting and log-parsing config for the message text |
| Metrics and traces | Renamed spans or metrics break dashboards and SLO alerts; moved instrumentation changes what's measured | Treat telemetry names as published |
| Stack traces | Error grouping in error trackers changes when frames change, which resets triage history | Usually acceptable; mention it in the PR |
