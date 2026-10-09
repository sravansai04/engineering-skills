# Large, Cross-Cutting, and Published Refactors

Read this when a refactor won't land as one reviewable PR, spans repositories or independently deployed services, or changes something other people call. Every technique here rests on one principle: **keep the system shippable after every commit.** Old and new coexist for a while, and you move traffic or callers across in small, reversible steps.

## Contents

1. Choosing a strategy
2. Parallel change (expand, migrate, contract)
3. Branch by abstraction
4. Strangler fig
5. Parallel run (shadow and compare)
6. Feature flags for the switch
7. Codemods at scale
8. Deprecate before delete
9. Stopping old usages from creeping back
10. Finishing the migration

---

## 1. Choosing a strategy

| Strategy | Fits when | Main cost |
|---|---|---|
| In-place small steps | Every caller is in this repo and the change fits in one reviewable PR | None beyond normal review |
| Parallel change | You're changing the shape of a function, type, field, endpoint or config key that has many callers or external callers | Temporary duplication; you have to finish the contract step |
| Branch by abstraction | You're replacing an internal component or library that's used throughout the codebase | Introducing a seam, sometimes one you'd otherwise not want |
| Strangler fig | You're replacing a subsystem or service that sits behind a natural boundary (HTTP routes, a facade, an event stream) | Running two systems, and keeping data consistent between them |
| Parallel run | A rewritten computation must give identical results, and tests can't enumerate the input space | Running both paths, and the comparison infrastructure |

The strategies combine. A strangler fig migration usually uses parallel runs for each slice, and branch by abstraction often ends with a parallel change to delete the seam.

**Even in a monorepo, an atomic commit is not an atomic deploy.** Services, workers, mobile apps and caches update at different times, so anything that crosses a process boundary needs the expand-contract shape.

## 2. Parallel change (expand, migrate, contract)

1. **Expand.** Add the new form next to the old one. Make the old form delegate to the new one, so there is only one implementation, and mark it deprecated. In a build that treats warnings as errors, that marker breaks every caller not yet migrated; see the sequencing note in section 8. For a symbol with only internal callers, a deprecation marker is optional: migrating every caller and deleting the old form may be enough.
2. **Migrate.** Move callers over in batches (per directory, per team, or per service), with one PR per batch. Re-run tests each time.
3. **Contract.** Once no callers remain and any external deprecation window has passed, delete the old form.

```typescript
// Expand: the new name holds the implementation; the old name forwards to it.
export function findCustomer(id: CustomerId): Promise<Customer> {
  /* implementation moved here */
}

/** @deprecated Use findCustomer(). Scheduled for removal in v5. */
export function getCustomer(id: CustomerId): Promise<Customer> {
  return findCustomer(id);
}
```

```bash
# Track remaining migration work: one total that should fall with every batch.
# (rg -c prints a count per file, not a total.)
rg -o -w 'getCustomer' --glob '!**/customers/index.ts' | wc -l
```

For data that crosses a process boundary (JSON fields, message schemas, config keys):

- **Read side:** accept both the old and the new name. Prefer the new one when both are present.
- **Write side:** keep emitting the old name, or both names, until every reader has been upgraded. Then emit only the new name.
- **Contract:** stop accepting the old name only after old producers and stored or in-flight data have drained or been migrated.

Database tables and columns follow the same pattern but add backfills and deploy ordering. Use `data-api:db-migration-safety` for them. If it isn't installed: add the new column, write to both, backfill, switch reads, then drop the old column in a later release.

## 3. Branch by abstraction

Use this to replace an implementation (an ORM, an HTTP client, a payment gateway adapter, an in-house module) without a long-lived branch.

1. **Introduce an abstraction**, an interface shaped by what the callers need rather than what the old library offers.
2. **Move callers onto the abstraction**, with the old implementation behind it. These commits are pure refactors.
3. **Build the new implementation behind the same abstraction**, incrementally, merged to trunk but not yet selected.
4. **Switch.** Select the new implementation by configuration or flag, per call site or all at once, and keep the old one available for rollback.
5. **Remove the old implementation.** Then decide whether the abstraction still earns its keep; if not, inline it.

Trunk stays releasable throughout, and nobody has to merge a months-old branch.

## 4. Strangler fig

Use this to replace a legacy system or subsystem gradually instead of with a big-bang rewrite.

1. **Find the interception point.** That could be a reverse proxy or API gateway route, a facade in code, the event stream the legacy system emits or consumes, or UI composition.
2. **Choose a thin first slice.** Low risk and high learning: one endpoint, one report, one region or one customer cohort.
3. **Decide data ownership for the slice.** At any moment, exactly one system should be the writer for a given entity. Dual writes without reconciliation drift apart. When both systems need the data, sync it from the owner by events or change data capture, and reconcile.
4. **Route the slice to the new system**, verified by a parallel run or a canary percentage, with fast rollback by routing.
5. **Repeat**, slice by slice.
6. **Delete each legacy piece as soon as nothing routes to it.** The classic failure is a strangler that never finishes, which leaves you running two systems forever. Agree on retirement criteria and a timeline up front.

## 5. Parallel run (shadow and compare)

Run the old path and the new path on the same input, return the **old** result, and record any mismatch along with the input that caused it. GitHub's Scientist library (Ruby) popularized this pattern, and it has been ported to many languages; a hand-rolled version is a few dozen lines.

- **Run the new path only where it's side-effect-free**, or point its side effects at a sandbox. Shadowing a path that charges cards or sends email duplicates those actions.
- **Normalize before comparing**: ordering, floating-point tolerance, timestamps, generated IDs.
- **Sample** a fraction of traffic to control cost, and put a timeout and an error budget on the new path, so it can't slow or break the old one.
- **Treat mismatch records as sensitive.** Real inputs carry personal data, credentials and payment details. Redact or hash those fields, or write full inputs only to an access-controlled store with a retention limit. Never write them to general application logs.
- **Switch only when the mismatch rate is near zero and every remaining mismatch class is understood.** Some mismatches turn out to be bugs in the old path. Decide each one explicitly, as a separate behavior change.
- **Remove the experiment and the old path after the switch.**

## 6. Feature flags for the switch

- Use a short-lived release toggle that defaults to the old behavior, and test both states in CI.
- Give the flag an owner and a removal date, and file the cleanup ticket when you create the flag.
- Removing the flag and the losing branch of code is part of the contract step, not optional polish.

## 7. Codemods at scale

When dozens or hundreds of call sites follow a regular pattern, write a transformation rather than editing by hand. It's faster, consistent, and reviewers can re-run it.

| Scope | Tools |
|---|---|
| Multi-language structural search and replace | ast-grep, Comby, Semgrep autofix |
| JavaScript / TypeScript | jscodeshift, ts-morph |
| Python | LibCST codemods, Rope |
| Java / Kotlin | OpenRewrite recipes; IDE structural search and replace |
| Go | `gofmt -r`, gopls rename, `//go:fix inline` directives applied by `go fix` (Go 1.26+) |
| Rust | rust-analyzer structural search and replace (SSR) |
| C# / .NET | Roslyn analyzers with code fixes |
| PHP | Rector |

```bash
# ast-grep: preview the matches and rewrites, then add -U to apply them all
ast-grep run -l ts -p 'getCustomer($ID)' -r 'findCustomer($ID)'
ast-grep run -l ts -p 'getCustomer($ID)' -r 'findCustomer($ID)' -U

# gofmt: single-character lowercase identifiers (a, b) are wildcards; -w writes files
gofmt -r 'strings.Index(a, b) != -1 -> strings.Contains(a, b)' -w ./internal/
```

Workflow:

1. Write the codemod and run it on a handful of files. Review the output by hand and refine it until it's clean.
2. Run it across the codebase in a **dedicated commit with no hand edits**. If the repo squash-merges, commits inside a PR collapse into one, so make it a dedicated PR instead.
3. Put the exact command, or the codemod source, in the commit message or PR description, so reviewers can reproduce the diff instead of reading every line, and so owners of other open branches can re-run it rather than hand-resolve conflicts.
4. Make manual fix-ups for the cases the codemod couldn't handle in a **separate commit** (a separate, stacked PR under squash merge), which reviewers read carefully.
5. Run the full suite, typecheck and build.
6. After it merges, add the mechanical commit's SHA **as it exists on the default branch** to `.git-blame-ignore-revs`. A squash or rebase rewrites the SHA, so one copied from the PR branch points at nothing. GitHub's blame view reads the file automatically; local `git blame` only does after `git config blame.ignoreRevsFile .git-blame-ignore-revs`.

## 8. Deprecate before delete

For anything with consumers you don't control (a library API, SDK, HTTP endpoint, CLI flag, config key, event schema):

1. **Mark it deprecated**, naming the replacement and the planned removal version or date.
2. **Document it** in the changelog, and write a migration guide with before and after examples.
3. **Warn at runtime** where the platform supports it: once per process or call site, not on every call.
4. **Measure remaining use.** Put a counter or log line on the deprecated path, check package dependents, and ask known consumers.
5. **Remove it in a major version.** Semantic Versioning's guidance is to ship the deprecation in a minor release, and remove it only in a later major release.

Deprecation markers by stack:

| Stack | Marker | Notes |
|---|---|---|
| Java | `@Deprecated(since = "4.2", forRemoval = true)` plus a Javadoc `@deprecated` tag naming the replacement | The `since` and `forRemoval` elements exist since Java 9 |
| Kotlin | `@Deprecated("Use findCustomer", ReplaceWith("findCustomer(id)"))` | IDEs can apply `ReplaceWith` automatically; raise `level` to `DeprecationLevel.ERROR` before removal |
| C# | `[Obsolete("Use FindCustomer")]` | `[Obsolete("...", true)]` turns use into a compile error |
| TypeScript / JavaScript | `/** @deprecated Use findCustomer() */` | Editors strike it through; enforce with `@typescript-eslint/no-deprecated` |
| Python | `@warnings.deprecated("Use find_customer()")` (3.13+), or `typing_extensions.deprecated` on older versions; or `warnings.warn(msg, DeprecationWarning, stacklevel=2)` | `DeprecationWarning` is hidden by default outside `__main__`. Make tests fail on internal use with `pytest -W error::DeprecationWarning` |
| Go | A doc-comment paragraph starting `Deprecated: ` | staticcheck flags uses (SA1019); add `//go:fix inline` to a forwarding wrapper so `go fix` migrates callers |
| Rust | `#[deprecated(since = "2.3.0", note = "use find_customer")]` | |
| Swift | `@available(*, deprecated, renamed: "findCustomer(id:)")` | |
| HTTP API | `Deprecation: @1767225599` (RFC 9745, a structured-field date in Unix seconds), `Sunset: Thu, 31 Dec 2026 23:59:59 GMT` (RFC 8594, an HTTP-date), `Link: <https://example.com/docs/migrate>; rel="deprecation"` | The Sunset time must not be earlier than the Deprecation time. Versioning policy belongs to `data-api:api-design` |
| CLI flag / config key | Keep the old name as a hidden alias that prints a warning naming the new one | When both are set, prefer the new one and warn |

**Sequence deprecation warnings against warnings-as-errors.** Many builds turn warnings into failures: `-Werror`, .NET `TreatWarningsAsErrors` (which makes CS0618 an error), a deprecation lint rule set to error in CI, `pytest -W error::DeprecationWarning`. In such a build the expand commit fails at every caller you haven't migrated yet. Keep un-migrated internal call sites building while you migrate: suppress or baseline them, or scope the error filter to packages already migrated. Escalate deprecated use to an error repo-wide only once internal callers are gone, which is also what keeps them from coming back (section 9).

## 9. Stopping old usages from creeping back

During a long migration, new code keeps reaching for the old API. Ban it in lint, so the remaining-usage count can only go down:

| Stack | Mechanism |
|---|---|
| JS / TS | ESLint core rules `no-restricted-imports`, `no-restricted-properties`, `no-restricted-syntax` |
| Python | Ruff `TID251` (banned-api; enable it, then list entries under `[tool.ruff.lint.flake8-tidy-imports.banned-api]`, e.g. `"billing.legacy.get_customer".msg = "Use billing.customers.find_customer"`) |
| Go | golangci-lint `forbidigo` (identifiers), `depguard` (imports) |
| Rust | Clippy `disallowed_methods` / `disallowed_types`, configured in `clippy.toml` |
| JVM | ArchUnit tests, Error Prone, or Checkstyle `IllegalImport` |
| .NET | `Microsoft.CodeAnalysis.BannedApiAnalyzers` with a `BannedSymbols.txt` |

Exempt the existing call sites through the linter's own suppression or baseline mechanism, and remove each exemption as its batch migrates.

## 10. Finishing the migration

- Open one tracking issue listing every batch and the contract step, and link each PR to it.
- Record the remaining-usage count each time a batch lands. A count that stops falling means the migration has stalled.
- Define done as: the old path, the alias, the flag, the shadow experiment and (if it's no longer useful) the abstraction are all deleted, the lint ban is removed or kept as a permanent guard, and the docs are updated.
- If the migration stalls for good, either finish it or roll back to one implementation. Two half-adopted implementations are worse than either one alone.
