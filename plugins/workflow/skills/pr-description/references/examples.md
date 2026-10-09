# Worked Examples

Use these to calibrate length and tone. Each one fits its change size. Copy the shape, not the wording. The specifics (commands, numbers, file names) stand in for whatever the real branch's evidence says.

Contents:
1. Backend bug fix: a bad description rewritten
2. UI change with screenshots
3. Large API change behind a flag
4. Pure refactor
5. Trivial fix

---

## 1. Backend bug fix: a bad description rewritten (Python)

**Before** (what not to write):

```markdown
Title: Fix bug

Fixed the issue with invoices. Updated invoice.py, tasks.py and tests. Tested locally.
```

This doesn't say which bug, why it happened, or what was tested and how. It lists files the reviewer can already see. There is no risk statement for a change that touches money, which the risk table rates High.

**After:**

```markdown
Title: Prevent duplicate invoices when the billing job retries

## Summary
When the nightly billing job timed out partway through, the scheduler retried it and every
customer billed before the timeout received a second invoice (14 support tickets in March, #482).
Invoice creation is now idempotent per customer and billing period, so a retry finds the existing
invoice instead of creating another. An idempotency key was chosen over a job-level lock because
the lock would not survive a worker crash.

## Reviewer guide
Most scrutiny: the key derivation in `create_invoice()` and the duplicate pre-check in migration
`0042`. The rest is tests and one log line.

## Key changes
- `create_invoice()` derives a key from `(customer_id, period_start)` and returns the existing
  invoice when one already exists.
- New unique constraint on `invoices (customer_id, period_start)`. The migration checks for
  existing duplicates first and aborts with a report instead of deleting anything.
- The billing job logs `invoice.duplicate_skipped` with the customer id, so retries are visible.

## How it was tested
- `pytest tests/billing -q` → 58 passed (3 new: retry after partial run, two workers racing,
  same customer in different periods).
- Ran the migration against last night's staging snapshot: 0 duplicate rows, finished in 1.8 s.
- Not tested: the real scheduler's retry path end to end. The race test simulates it.

## Risk & rollout
**Risk: High**, because it changes how invoices are created on the billing path. The duplicate pre-check
and the safer failure mode below keep the blast radius small.
- Migration runs before the code deploy; the old code is compatible with the constraint.
- Rollback: revert the code. If the constraint stays, old code raises on a retry instead of
  double-billing, which is the safer failure. The down-migration for `0042` drops it if needed.
- Watch: `invoice.duplicate_skipped` count after the next nightly run; non-zero is expected only
  when the job retried.

Closes #482
```

---

## 2. UI change with screenshots (TypeScript / React)

```markdown
Title: Show inline validation errors on the signup form

## Summary
Signup errors appeared only as a toast after submit, which disappeared before users could read
which field was wrong; 9% of signup attempts fail validation at least once. Each field now shows
its own error as soon as it loses focus, and the submit button reports how many fields need
attention.

## Key changes
- Field-level validation on blur, reusing the existing schema in `signupSchema.ts`.
- Errors render under each input and are linked with `aria-describedby`, so screen readers
  announce them.
- The toast on submit is removed. The summary next to the button replaces it.

## How it was tested
- `npm test -- SignupForm` → 21 passed (6 new).
- Manual, Chrome and Safari on desktop, plus the iOS simulator at 375 px: empty submit,
  invalid email, mismatched passwords, server-side "email taken".
- VoiceOver on macOS reads the error after leaving an invalid field.
- Not checked: Firefox, Android.

## Screenshots
| Before | After |
|---|---|
| (drag before image here) | (drag after image here) |

Mobile, 375 px: (drag image here)

## Risk & rollout
**Risk: Low.** Client-side only; server validation is unchanged and still authoritative.

Closes #1207
```

In the report back to the user, list the three screenshot placeholders under "Needs your input". gh can't attach them.

---

## 3. Large API change behind a flag (Go)

```markdown
Title: Add cursor pagination to GET /v1/orders behind orders_cursor_pagination

## Summary
Offset pagination on `/v1/orders` slows down linearly with page depth (p95 2.4 s at page 400
for our largest accounts) and skips or repeats rows when orders arrive mid-scroll. This adds an
opaque `cursor` parameter ordered by `(created_at, id)`. The existing `page` parameter keeps
working, so no client has to change yet.

## Reviewer guide
1. `internal/orders/cursor.go`: encoding and the ordering guarantee. This needs the most
   scrutiny; the `id` tie-breaker is what makes it correct when timestamps collide.
2. `internal/orders/handler.go`: parameter parsing and the flag check.
3. `migrations/0091_orders_created_at_id_idx.sql`: the supporting index.
4. Skim: `internal/mocks/` is generated, and `go.sum` changed only for the new base64url helper.

## Key changes
- New optional `cursor` query parameter and `next_cursor` response field (additive).
- Composite index on `orders (account_id, created_at, id)`, built concurrently.
- `page` is marked deprecated in the OpenAPI spec. Its behavior is unchanged.

## How it was tested
- `go test ./internal/orders/...` → ok (47 tests, 19 new, including the duplicate-timestamp and
  concurrent-insert cases).
- Against a staging copy of the largest account, page-400-equivalent depth: p95 2.4 s → 38 ms.
- Not tested: clients other than the web app. The mobile app does not paginate orders yet.

## Risk & rollout
**Risk: Medium**, because of a new index on a large table and an additive public parameter (no existing
behavior changes while the flag is off).
- Flag `orders_cursor_pagination`: off everywhere. Enable for internal accounts first, then 10%.
- Migration: the index builds concurrently (about 6 minutes on the staging copy) and must finish
  before the flag is enabled. The code ignores the cursor path while the flag is off.
- Rollback: turn the flag off. Reverting the code is safe, and the index can stay.
- Watch: p95 latency and 4xx rate on `/v1/orders`, split by the presence of `cursor`.

## Breaking changes
None. `page` is deprecated but still supported. Removal is tracked in #913 and needs a
version bump.

## Follow-ups / out of scope
- Cursor pagination for `/v1/invoices` (#915).
- Remove the flag after two weeks at 100% (#914).

Closes #877
```

---

## 4. Pure refactor (Java)

```markdown
Title: Extract PriceCalculator from OrderService (no behavior change)

## Summary
`OrderService` had grown to 1,900 lines, and pricing rules were tangled with persistence, which
made the upcoming regional tax work (#640) hard to test. This moves pricing into a
`PriceCalculator` with no change in behavior.

## Reviewer guide
The commits are meant to be reviewed one at a time:
1. Move the methods verbatim (large, purely mechanical: skim).
2. Rename the private helpers.
3. Introduce constructor injection (small: read carefully).

## Key changes
- Pricing methods moved verbatim into `PriceCalculator`. `OrderService` now delegates to it.
- `PriceCalculator` takes its dependencies through the constructor. No static state.
- No public API, schema, or configuration changes.

## How it was tested
- `./mvnw -pl orders test` → 312 passed. The existing tests are unchanged, which is the main
  evidence of no behavior change.
- Added a characterization test that prices 500 recorded production carts (anonymized) and
  compares the totals with the pre-refactor output: all identical.

## Risk & rollout
**Risk: Low.** Mechanical move with characterization coverage. Revert is safe.

Part of #640
```

---

## 5. Trivial fix

```markdown
Title: Correct the default timeout in the CLI help text

The help text said 30 s; the actual default in `config.rs` is 60 s. The text now matches the code.

Testing: `cargo run -- --help` shows "default: 60s".
```

There's no risk section, no key changes and no reviewer guide here. Adding them would only cost reviewer attention.
