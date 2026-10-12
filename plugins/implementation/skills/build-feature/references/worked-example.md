# Worked example: one complete run

Read this once before your first use, or whenever a phase feels abstract. It
follows a medium-sized feature through all eight phases. The repository,
paths, and commands are illustrative (a TypeScript service with a React front
end); the notes at the end map the same run onto other stacks.

Contents: the request · step 0, route and size · Phase 1, discover · Phase 2,
explore · Phase 3, clarify (G2) · Phases 4 and 5, design and plan (G3) ·
Phase 6, implement · Phase 7, review · Phase 8, verify and final report · the
same run on other stacks.

---

## The request

> "Can you add CSV export to the orders page? The ops team keeps asking."

## Step 0: route and size

A new capability, not a defect or a refactor, so this skill applies. Sizing:
a new endpoint plus a button, an existing permission model, and a possibly
large data set. No schema change, no public contract. **Size M.**

## Phase 1: Discover

```text
Feature brief: orders CSV export                       size: M
Goal:          Ops users can download the orders they are looking at as CSV.
In scope:      export button on the orders list; server endpoint; CSV format
Out of scope:  scheduled exports, other formats, other list pages
Acceptance criteria (draft):
  AC1  Given a filtered orders list, when the user exports, then the file
       contains exactly the rows matching the active filter
  AC2  Given a user without access to orders, when they call the export
       endpoint, then they get 403 and no data
  AC3  Given more rows than the limit, when the user exports, then <unknown>
Unknowns:      which columns -> user; row limit -> user + code;
               date time zone -> user; how existing exports work -> code
Base:          (filled at Phase 6 set-up)
```

The unknowns split cleanly: three for the user, one for the code. Nothing is
too unclear to explore, so there is no early G1; the questions wait for G2.

## Phase 2: Explore

One message, three `Explore` subagent calls (Claude Code's read-only type), each
with the shared preamble and return contract from `explorer-briefs.md`:

- **A, closest analog:** "...find the existing feature most similar to a
  filtered list CSV export and trace it end to end..."
- **B, integration surface:** "...identify where an orders export endpoint and
  a list-page button would plug in, including filter parsing and permission
  checks..."
- **C, verification and conventions:** "...how are list endpoints and
  downloads tested here; exact commands for one test, the suite, lint, and
  types; installed versions of the HTTP and CSV libraries..."

Condensed returns, after checking each claim the design depends on:

- A: invoices already export CSV through a streaming writer at
  `src/invoices/export.ts:12`, using a shared `writeCsv()` helper
  (`src/shared/csv.ts:5`). **Read it: confirmed.**
- B: the orders list parses filters server-side into an `OrderQuery`
  (`src/orders/routes.ts:88`) behind the `orders.view` permission check at
  `src/orders/routes.ts:61`. B labeled the server-side parsing an INFERENCE.
  **Read `routes.ts`: confirmed, promoted to fact.**
- C: route tests use a request helper (`test/support/http.ts`); single test is
  `npx vitest run src/orders/routes.test.ts`; lint `npm run lint`; types
  `npx tsc --noEmit` (all from `package.json` scripts and the CI workflow).
  No CSV library: `writeCsv()` is hand-written, so no third-party API to check.
- Conflict: A said exports load all rows into memory; B said the query layer
  caps pages at 500 rows. Reading `src/orders/query.ts:140` shows both are
  true: invoices are small, and orders have a `forEachBatch()` cursor helper for
  large reads. The map records `forEachBatch()` as the pattern to use.

## Phase 3: Clarify (G2)

```markdown
[build-feature · Phase 3/8 Clarify · size M]

**Decision needed:** answers to 4 questions below (or "defaults are fine").

**Goal:** ops users download the orders they're viewing as CSV.
**Acceptance criteria (draft):**
- AC1 Given a filtered orders list, when the user exports, then the file
  contains exactly the rows matching the active filter.
- AC2 Given a user without access to orders, when they call the export
  endpoint, then they get 403 and no data.
- AC3 Given more rows than the limit, when the user exports, then (depends on
  question 2).
**Out of scope:** scheduled exports, formats other than CSV, other list pages.

**What the code tells us**
- Closest analog: invoice export (`src/invoices/export.ts:12`); I'll mirror it
  and reuse the shared `writeCsv()` helper (`src/shared/csv.ts:5`).
- Plugs in at: `src/orders/routes.ts:88` (filter parsing), `routes.ts:61`
  (permission check).
- Tests: route tests via `test/support/http.ts`; single test runs with
  `npx vitest run src/orders/routes.test.ts`.
- Constraint worth knowing: orders reads must page through `forEachBatch()`
  (`src/orders/query.ts:140`); the plain query caps at 500 rows.

**Questions** (most consequential first)
1. Permission: reuse `orders.view`, or add `orders.export` so bulk download
   can be granted separately? *Default: reuse `orders.view`; it matches
   invoices.*
2. Size: the largest account has ~2M orders. Cap synchronous export at 50k
   rows with a clear message, or build a background job now (~2 extra days)?
   *Default: cap at 50k for v1.*
3. Columns: the columns visible on screen, or every order field? *Default:
   visible columns, so the file matches what the user sees.*
4. Dates: the viewer's time zone (as on screen) or UTC? *Default: viewer's
   time zone, with the offset in the header.*

Reply with answers or "defaults are fine". I won't design anything until then.
```

The user replies: "Defaults are fine, but use UTC for dates; finance imports
these." AC3 becomes "export over 50k rows returns a clear message and no
partial file"; AC4 is added: "timestamps are ISO 8601 UTC". The brief now
reads AC1-AC4, all four confirmed by the user.

## Phases 4 and 5: Design and plan (G3, one approval for both)

- **Option A (recommended):** a synchronous streaming endpoint
  `GET /orders/export.csv` that reuses `OrderQuery` parsing and `forEachBatch()`,
  writes through `writeCsv()`, and stops with a message above 50k rows. About
  five files; mirrors invoices.
- **Option B:** a background job that writes the file to storage and notifies
  the user. Handles 2M rows, but adds a job, storage cleanup, and a
  notification: about nine files.
- A client-side option that builds the CSV in the browser was considered and
  rejected: the browser holds only the current page, so it cannot satisfy AC1.

Recommendation A; choose B instead if exports over 50k rows must work this
release.

`implementation:plan-feature` then ran with the hand-off text from
`delegation.md` §2: brief, map, and design "A, recommended, approval pending"
as settled inputs; no questions, no alternatives, a spot-check of the map's
files plus a search for other consumers of `writeCsv()` (it found only
invoices). It returned a lite plan with two slices:

- **Slice 1, export endpoint** (five steps, five commits): walking skeleton
  (endpoint returns a header-only CSV, test green); filtering (AC1);
  permission (AC2); the 50k cap (AC3); UTC timestamps (AC4).
- **Slice 2, toolbar button** (two steps): the button builds the export URL
  from the active filter; the over-limit message shows in the UI (AC3).

The G3 message carried the comparison, this plan marked "for A; I'll re-plan
if you pick B", and the delivery question: "Two slices, about 250 changed
lines together. Recommended: one combined PR, since each half is small." The
user replies "A, go. One PR."

## Phase 6: Implement

- `git status --short` is clean. `git fetch`, then
  `git switch --no-track -c feat/orders-csv-export origin/main`; base
  `origin/main@4e1f9a2` recorded in the brief.
- Baseline: `npx vitest run src/orders` shows **one pre-existing failure** in
  `list.test.ts` (a date-dependent assertion). Not a tripwire: reported to the
  user in one line, recorded in the brief, and left alone; it became a
  follow-up instead of a silent fix.
- Each step: failing test, code, narrow run, `npm run lint` and
  `npx tsc --noEmit`, then `git add --` the step's own files and commit.
  Seven commits, each green.
- Deviation, internal: `forEachBatch()` passes batches, not rows, so the export
  needed a small adapter, kept in `src/orders/export.ts`. It changes no agreed
  behavior, so it was logged and the work continued.

## Phase 7: Review

1. **Self-review** against the brief found a leftover `console.log`; removed.
2. The diff was already plain; `implementation:simplify-code` was not needed.
3. **Independent review:** a fresh `general-purpose` subagent with the
   `delegation.md` §4 brief (AC1-AC4, non-goals, the user's decisions as
   constraints, range `4e1f9a2...HEAD`, the test and lint commands), told to
   apply `review-suite:pr-review`; a second one with the security lens,
   because the feature bulk-exports customer data.

The security reviewer found that text cells could run as formulas when a
spreadsheet opens the file (CSV injection). The fix belongs in `writeCsv()`,
which invoices also use, so applying it would change invoice files: another
feature's output. That makes it a deviation stop:

```markdown
[build-feature · Phase 7/8 Review · paused]

**Decision needed:** where to put the CSV-injection fix.

What we agreed: orders export reuses the shared `writeCsv()`; invoices
unchanged.
What I found: the security reviewer showed that `writeCsv()`
(`src/shared/csv.ts:5`) writes text cells as-is, so an order note such as
`=HYPERLINK(...)` runs as a formula when ops opens the file. Invoice exports
have the same hole today.
Why it matters: exported files reach finance's spreadsheets.

Options:
1. Escape in `writeCsv()`, which changes invoice files too, and add an
   invoice test. *Recommended: both exports need it, and one place to fix
   means one place to keep right.*
2. Escape in orders-only code; file the invoice hole as a follow-up.

Committed so far: all seven steps (green). Nothing from this fix is committed.
```

The user picks option 1. Triage of every finding:

- **Fix:** in `writeCsv()`, a text cell whose first character is `=`, `+`,
  `-`, `@`, tab, carriage return, or line feed (or a full-width `＝`, `＋`,
  `－`, `＠`) gets a leading single quote, and every field is wrapped in double
  quotes with embedded quotes doubled, following OWASP's CSV Injection
  guidance. Values the writer receives as numbers are written as numbers and
  never prefixed, so a refund amount of `-12.50` stays numeric for finance's
  import. Tests written first: a formula-looking note comes out escaped; the
  `-12.50` amount comes out as `-12.50`; an invoice export test shows the
  same escaping.
- **Dispute:** "should be a background job." The user chose the 50k cap at
  G3; cited the decision log.
- **Defer:** "record an audit event for exports." Reasonable but not in scope;
  added to follow-ups.

## Phase 8: Verify and final report

`git fetch`, then `git log --oneline HEAD..origin/main` listed three new
commits, one touching `src/orders/query.ts`. The contributing guide asks for
rebase and the branch had not been pushed, so it was rebased onto
`origin/main@9c03b71`. Then `implementation:verify-before-done`: reran
`npx vitest run src/orders src/invoices src/shared` (all new tests pass; the
same one pre-existing failure), lint and types clean, and downloaded an
export from the running app with a filter applied, opening it to check rows,
timestamps, and a formula-looking note.

```markdown
## Built: Orders CSV export

**Outcome:** Users with order access can download the filtered orders list
as CSV, up to 50k rows, timestamps in UTC, with spreadsheet formulas
neutralized (in invoice exports too).

### Assumptions and open questions
- none: the four G2 questions and the CSV-injection placement were the
  user's decisions.

### Acceptance criteria
| AC | Evidence | Status |
|----|----------|--------|
| AC1 filter respected | `routes.test.ts > export applies status filter`, passing; manual export of "status: shipped" matched the on-screen count (312) | verified |
| AC2 403 without access | `routes.test.ts > export requires orders.view`, passing | verified |
| AC3 cap at 50k | `routes.test.ts > export over limit returns message`, passing; `OrdersToolbar.test.tsx > shows over-limit message`, passing | verified |
| AC4 UTC ISO 8601 | `csv.test.ts > formats timestamps as UTC`, passing | verified |

### Decisions
- Synchronous streaming export with a 50k cap: matches invoices; a background
  job was rejected for v1 (user decision at G3).
- UTC timestamps: finance imports the files (user answer at G2).
- Formula escaping in the shared `writeCsv()`, so invoices change too (user
  decision at the Phase 7 stop).

### Changes
- Orders API: `src/orders/routes.ts` (route), `src/orders/export.ts` (new
  endpoint and batch adapter)
- Shared CSV: `src/shared/csv.ts` (formula escaping, affects invoice exports)
- UI: `web/orders/OrdersToolbar.tsx` (export button, over-limit message)

### Verification run (this session)
- Base: `origin/main@9c03b71` (rebased from `4e1f9a2`)
- `npx vitest run src/orders src/invoices src/shared`: 58 passed, 1 failed
  (pre-existing `list.test.ts`, unchanged)
- `npm run lint`: clean. `npx tsc --noEmit`: clean.

### Review
- Self-review: fixed 1 (leftover log)
- Independent review (fresh subagents: `review-suite:pr-review`, plus a security lens):
  fixed 1 (CSV injection), disputed 1 (background job, decided at G3),
  deferred 1 (audit event)

### Delivery
- Slice 1 export endpoint (5 commits) and slice 2 toolbar button (2 commits),
  plus 1 fix commit, on `feat/orders-csv-export`; one combined PR (user
  choice at G3); not pushed yet
- Done inline because a sibling skill was missing: none

### Follow-ups and risks
- Audit event for exports (from review).
- Pre-existing failure in `list.test.ts` is date-dependent; needs its own fix.
- Accounts above 50k orders will hit the cap; revisit with the job design.

### Next step
Push `feat/orders-csv-export` and open a PR with a generated description?
```

If the PR's CI later goes red, the next move is `workflow:ci-failure-triage`;
reviewer comments go to `workflow:respond-to-review`.

## The same run on other stacks

The phases do not change; only the names and commands do.

- **Python web service:** the analog might be a view using the standard
  library's `csv.writer` over a streaming response; tests with
  `pytest tests/orders -k export -x`.
- **Go service:** a handler writing through `encoding/csv` to the
  `http.ResponseWriter`; tests with `go test ./internal/orders/... -run Export`.
- **JVM service:** a controller streaming the response; tests with
  `./gradlew test --tests '*OrderExport*'`.

In every case the explorer for verification and conventions finds the real
commands. Never assume them from this table.
