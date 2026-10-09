# Reviewer checklist

Sections 1 to 11 are questions to ask in step 6 of the review, grouped in the
same order of priority; step 8 uses section 8. Section 12 covers PRs that need
a different first move (re-reviews, refactors, reverts, dependency bumps,
self-reviews). Section 13 adds UI and accessibility questions for any change
that touches what users see. You don't need to answer
every line for every PR. Pick the sections that match the files in the diff.
A "yes" to a red-flag question is only a candidate: it still has to pass the
verification gate in SKILL.md before it goes into the report.

## Contents

1. Correctness and logic
2. Security (generalist level)
3. Data integrity and migrations
4. Concurrency and async
5. Error handling and resilience
6. Performance (generalist level)
7. API and compatibility
8. Tests
9. Maintainability and readability
10. Operational readiness
11. Language and runtime gotchas
12. Special kinds of PR
13. UI and accessibility (generalist level)

---

## 1. Correctness and logic

- [ ] Does the code do what the PR description and linked issue say, for every
      case they mention?
- [ ] Boundaries: first and last element, zero, one, many, maximum size,
      negative numbers, the end of a page, the end of a month or year.
- [ ] Empty, null, missing, or default values: empty collection, empty string,
      absent optional field, zero-value struct.
- [ ] Conditions: inverted checks, `and`/`or` mix-ups, missing `else`, a
      fall-through in a `switch`, short-circuit evaluation that skips a side
      effect.
- [ ] The wrong variable or field (a copy-paste from a neighboring block), the
      wrong units (ms vs s, cents vs dollars, bytes vs KiB).
- [ ] State machines: can the new code reach a state that was impossible
      before? Are all transitions guarded?
- [ ] Time: time zones, DST, local vs UTC, inclusive vs exclusive end dates,
      clock skew between machines.
- [ ] Numbers: integer overflow, division by zero, float equality, rounding
      direction, money stored as floating point.
- [ ] Text: encoding, normalization, case-insensitive comparisons, locale-
      dependent formatting or parsing.
- [ ] Ordering: does the code assume an order that isn't guaranteed (map or set
      iteration, query results without `ORDER BY`, ties in a sort key)?
- [ ] Idempotency: if this runs twice (retry, redelivery, double-click), is the
      result still correct?
- [ ] Feature flags and config: is the old path still correct while the flag is
      off, and the new path when it is on?

## 2. Security (generalist level)

Go deeper with `review-suite:secure-code-review` whenever any of these applies.

- [ ] Does every new endpoint, handler, job, or command check that this caller
      is allowed to act on this specific resource (authorization), not just
      that they are logged in?
- [ ] Does untrusted input reach a query, shell command, file path, URL fetch,
      template, regex, or deserializer without parameterization, validation, or
      an allow-list?
- [ ] Are secrets, tokens, or credentials hard-coded, logged, returned in
      errors, or committed in fixtures?
- [ ] Is personal or sensitive data written to logs, analytics, error trackers,
      or caches that live longer than it should?
- [ ] Do new dependencies come from expected sources, and are they maintained,
      pinned, and actually needed?
- [ ] Did security-relevant defaults change (CORS, cookie flags, TLS
      verification, CSRF protection, rate limits)?
- [ ] Did CI workflows, build scripts, or ownership files (`CODEOWNERS`)
      change? Look for jobs that run PR code with secrets in reach (for
      example a `pull_request_target` workflow that checks out the PR head),
      widened token permissions, unpinned third-party actions, and review
      rules quietly loosened.

## 3. Data integrity and migrations

Go deeper with `data-api:db-migration-safety` (schema and data changes) and
`data-api:query-review` (query shape and indexes).

- [ ] Will the code that is still running mid-deploy (the old version) work
      against the new schema, and the new code against the old one?
- [ ] Does a migration lock a large table, rewrite it, or backfill it in one
      transaction?
- [ ] Are new columns nullable or defaulted in a way that matches existing
      rows? Is a `NOT NULL` or unique constraint added before the data
      satisfies it?
- [ ] Are related writes in one transaction, or can a failure halfway through
      leave the data inconsistent?
- [ ] Are deletes and overwrites reversible, or is there a backup or soft-delete
      path?
- [ ] Do constraints in the database (foreign keys, uniqueness, checks) back up
      the rules the application assumes?
- [ ] Is cached or denormalized data invalidated or updated when its source
      changes?

## 4. Concurrency and async

- [ ] Check-then-act: is there a read, a decision, then a write, with no lock,
      transaction, or atomic operation covering the gap?
- [ ] Is shared mutable state (globals, singletons, class-level caches, module
      state in long-lived workers) touched by requests or threads at the same
      time?
- [ ] Is every async call awaited or deliberately detached with its errors
      handled?
- [ ] Are locks always taken in the same order? Are they released on every
      path, including errors?
- [ ] Do retries, queues, or webhooks assume exactly-once delivery when the
      system only guarantees at-least-once?
- [ ] Are timeouts set on network calls and lock waits?
- [ ] Do the tests depend on timing (`sleep`, wall-clock time) in a way that
      will be flaky?

## 5. Error handling and resilience

- [ ] Are errors swallowed (an empty catch, a log-and-continue that hides a
      real failure) or caught too broadly?
- [ ] When an error is rethrown or wrapped, does it keep the original cause and
      enough context to debug?
- [ ] Are resources released on failure paths (`finally`, `defer`, `with`,
      `using`, RAII)?
- [ ] After a partial failure, is the state consistent, or is it clear what
      cleans it up?
- [ ] Do user-facing error messages leak internals (stack traces, SQL, file
      paths)?
- [ ] Is a fallback or default value hiding a failure that should be loud?
- [ ] Do retries use backoff, a cap, and only retry errors that can actually
      succeed on retry?

## 6. Performance (generalist level)

Go deeper with `review-suite:performance-review`.

- [ ] Is there a query or remote call inside a loop (N+1)?
- [ ] Does anything load an unbounded result set or file into memory? Is
      pagination or streaming needed?
- [ ] Is there nested iteration over inputs that grow with customer data?
- [ ] Is there blocking I/O on a request path or event loop that used to be
      fast?
- [ ] Do new queries have supporting indexes, or will they scan?
- [ ] Do caches have bounded size, a TTL, and a correct key (including every
      input that affects the value)?

## 7. API and compatibility

Go deeper with `data-api:api-design` for new or reshaped public contracts.

- [ ] Did a public function signature, return type, thrown error, or default
      value change? Who calls it outside this repo?
- [ ] Did a wire format change: a renamed or removed field, a type change,
      required vs optional, an enum gaining values that strict clients reject?
- [ ] Did HTTP status codes, error shapes, or pagination semantics change?
- [ ] Were config keys, environment variables, CLI flags, or file paths
      renamed? Are deploy configs and docs updated to match?
- [ ] Do producer and consumer deploy together? If not, is the change backward
      and forward compatible for the rollout window?
- [ ] Is a breaking change versioned, announced, or noted in the changelog?

## 8. Tests

- [ ] Is there a test for each new behavior and for the exact bug being fixed?
- [ ] Does the test run the changed branch, not a sibling path?
- [ ] Are the assertions specific (exact values, exact errors), not just "no
      exception", "not null", or a re-recorded snapshot?
- [ ] Does the test mock the unit under test, or mock so much that it only
      tests the mocks?
- [ ] Are edge cases and error paths covered, not only the happy path?
- [ ] Would the test fail if the production change were reverted? (SKILL.md,
      step 8, shows how to check.)
- [ ] Is it deterministic: no real network, no wall clock, no dependence on
      test order, no shared global state?
- [ ] Were existing tests weakened, skipped, or deleted? If so, is the reason
      stated?
- [ ] Do test names describe the behavior, so a failure explains itself?

## 9. Maintainability and readability

- [ ] Do names say what things are and do? Does a name still match the
      behavior after the change?
- [ ] Is logic duplicated somewhere it will drift out of sync?
- [ ] Is the abstraction the right size: no speculative generality, no
      thousand-line function?
- [ ] Do comments explain *why* rather than restate *what*? Are any comments
      now wrong?
- [ ] Is there dead code, commented-out code, or debug output left behind?
- [ ] Does each TODO have an owner or a linked issue?
- [ ] Does the change follow the patterns the surrounding code already uses?

## 10. Operational readiness

- [ ] Can a new failure mode be seen in production (logs at the right level,
      metrics, alerts)?
- [ ] Can the change be rolled back safely, or turned off with a flag?
- [ ] Are new config values and secrets provisioned in every environment?
- [ ] Are docs, runbooks, the changelog, and API references updated where users
      or operators depend on them?

## 11. Language and runtime gotchas

Short patterns that commonly hide bugs. Check the ones for the languages in the
diff. Each is a reason to look closer, not an automatic finding.

| Stack | Pattern | Why it bites |
|---|---|---|
| Python | Mutable default argument: `def add(item, items=[])` | The default is created once and shared across calls. |
| Python | `except:` or `except Exception: pass` | Hides failures. A bare `except` also catches `KeyboardInterrupt` and `SystemExit`. |
| Python | `is` to compare strings or numbers | Compares identity, not equality. It only works by accident for small cached values. |
| JavaScript / TypeScript | `items.forEach(async (x) => { await save(x) })` | `forEach` ignores the returned promises. The caller doesn't wait, and rejections go unhandled. Use `for...of` or `Promise.all`. |
| JavaScript / TypeScript | `[10, 9, 1].sort()` | The default sort compares values as strings, giving `[1, 10, 9]`. Pass a comparator. |
| TypeScript | `as SomeType` or `value!` on external data | Silences the compiler without any check at runtime. |
| Go | Writing to a nil map | Panics at runtime. |
| Go | `v, err := f()` inside an inner block when `err` is declared outside | Shadows the outer `err`, so the outer check sees `nil`. |
| Go | Closures or goroutines capturing a loop variable when the module's `go` directive is below 1.22 | All iterations share one variable. From 1.22 each iteration gets its own. |
| Go | `defer` inside a loop | Runs at function return, not per iteration, so file handles or locks pile up. |
| Java | `==` on `String` or boxed `Integer` | Compares references. Boxed integers compare equal only for cached small values (-128 to 127 by default). |
| Java / Kotlin | `equals` overridden without `hashCode` | Breaks hash-based collections. |
| C# | `async void` outside event handlers | The caller can't await it or catch its exceptions. |
| C# | `.Result` or `.Wait()` on a `Task` | Blocks a thread, and can deadlock under a synchronization context. |
| Rust | `.unwrap()` or `.expect()` on fallible input outside tests | Panics instead of returning an error the caller can handle. |
| SQL | `WHERE col = NULL`, or `NOT IN (subquery)` where the subquery can return NULL | `= NULL` is never true. `NOT IN` with a NULL in the list matches no rows. |
| SQL | `LIMIT ... OFFSET` paging ordered by a non-unique column | Rows that tie can repeat or vanish between pages. Add a unique tiebreaker. |
| Shell | Unquoted `$var` | Word splitting and globbing break on spaces and wildcards. |
| Any | Floating point for money | Rounding errors build up. Use integer minor units or a decimal type. |
| Any | Naive or local datetimes stored or compared | DST and server time zone bugs. |

## 12. Special kinds of PR

- **Re-review rounds.** Focus on the commits since your last review. Each
  review records the commit it was made against, so
  `gh api "repos/{owner}/{repo}/pulls/123/reviews" --paginate --jq '.[] | {user: .user.login, state, commit_id}'`
  tells you where to start. List the earlier inline comments (they don't
  appear in `gh pr view --comments`):
  `gh api "repos/{owner}/{repo}/pulls/123/comments" --paginate --jq '.[] | {id, path, line, user: .user.login, in_reply_to_id, body}'`.
  The REST API doesn't say which threads are resolved or outdated; GraphQL
  does:

  ```bash
  gh api graphql -F owner=OWNER -F repo=REPO -F pr=123 -f query='
    query($owner: String!, $repo: String!, $pr: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $pr) {
          reviewThreads(first: 100) {
            nodes { isResolved isOutdated path line
                    comments(first: 10) { nodes { author { login } body } } }
          }
        }
      }
    }'
  ```

  Check that each earlier comment was actually fixed in the code, not just
  marked resolved. After a force-push, this shows what really changed:
  `git range-diff OLD_BASE..OLD_HEAD NEW_BASE..NEW_HEAD`.
- **"Pure refactor" PRs.** Check that behavior is unchanged: defaults,
  evaluation order, exception types, iteration order. Tests edited in a pure
  refactor are a red flag. (`implementation:refactor-safely` covers how to do one.)
- **Reverts.** Compare against the original commit (`git show`). Make sure the
  revert is complete, and that data the reverted code already wrote is still
  handled.
- **Dependency bumps.** Read the changelog for breaking changes between the two
  versions. Check for new transitive packages, and that every new or changed
  license is compatible with the project's policy. Send supply-chain concerns
  to `review-suite:secure-code-review`.
- **Self-review before opening a PR.** Same process. Fetch the default
  branch first, diff from the merge base so uncommitted edits to tracked files
  are included, and remember that `git diff` never shows untracked files. List
  them with `git status --porcelain` or
  `git ls-files --others --exclude-standard` and read each new file in full
  (`git diff --no-index /dev/null path`). Don't run `git add -N`, which
  changes the user's index. The user's own code passes the trust gate, so
  running its tests is fine.

## 13. UI and accessibility (generalist level)

Ask these for any change to templates, components, styles, or user-facing
copy. A failure on a primary flow that breaks a WCAG 2.2 level A or AA
criterion is at least `high`; route a full audit to
`frontend:accessibility-review`.

- [ ] Can every new interactive element be reached and operated with the
  keyboard alone, in a sensible order, with no keyboard trap? Native
  `button`, `a`, and form controls get this for free; a clickable `div` does
  not.
- [ ] Does every input have a programmatic label (`<label for>`,
  `aria-label`, or `aria-labelledby`), not only placeholder text?
- [ ] Is focus visible, and is it managed: moved into a dialog when it opens,
  returned to the trigger when it closes, and placed sensibly after a route
  change or a deleted row?
- [ ] Do meaningful images have alt text that says what they convey, and do
  decorative ones have `alt=""`?
- [ ] Is state (error, selected, required, status) shown by more than color,
  and does text meet contrast (4.5:1 for body text, 3:1 for large text and
  UI parts)?
- [ ] Are error messages tied to their fields (`aria-describedby`), announced
  when they appear, and specific about how to fix the input?
