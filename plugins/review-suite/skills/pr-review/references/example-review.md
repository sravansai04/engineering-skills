# Worked example and phrasing guide

This file has two parts. The first is a complete review of a small PR,
showing how intent, reading callers, the verification gate, and the severity
rubric fit together. The second gives the rules for wording findings and then
shows weak and strong versions side by side in several languages.

## Contents

1. Worked example: "Paginate the orders CSV export"
2. Comment rules and phrasing: weak vs strong

---

## 1. Worked example: "Paginate the orders CSV export"

### Input

PR 482. **Description:** "Large customers time out on the orders export. Add
`page` and `page_size` so the export is fetched in pages of 500. Closes 470."

```diff
--- a/src/orders/export.py
+++ b/src/orders/export.py
@@ -8,7 +8,10 @@ from orders.serializers import serialize_order
 
 
-def export_orders(db, customer_id):
-    rows = db.fetch_all(
-        "SELECT * FROM orders WHERE customer_id = %s", (customer_id,)
-    )
+def export_orders(db, customer_id, page=1, page_size=500):
+    offset = page * page_size
+    rows = db.fetch_all(
+        "SELECT * FROM orders WHERE customer_id = %s "
+        "ORDER BY created_at LIMIT %s OFFSET %s",
+        (customer_id, page_size, offset),
+    )
     return [serialize_order(r) for r in rows]
--- a/src/api/orders.py
+++ b/src/api/orders.py
@@ -41,3 +41,5 @@ def orders_export(request, customer_id):
     authorize(request.user, "orders:export", customer_id)
-    return csv_response(export_orders(db, customer_id))
+    page = int(request.args.get("page", 1))
+    page_size = int(request.args.get("page_size", 500))
+    return csv_response(export_orders(db, customer_id, page, page_size))
 
--- /dev/null
+++ b/tests/orders/test_export.py
@@ -0,0 +1,7 @@
+from orders.export import export_orders
+
+
+def test_export_orders_paginates(db, make_orders):
+    make_orders(customer_id=7, count=3)
+    rows = export_orders(db, 7, page=0, page_size=2)
+    assert len(rows) <= 2
```

### What the reviewer did

- **Intent.** "Bound the memory and time of one export request by paging
  through a customer's orders, 500 at a time." The issue also asks that "the
  nightly export keeps working".
- **Callers.** Searching for `export_orders` at the PR head and at the base tip
  found the HTTP handler in the diff, and also `jobs/nightly_export.py:22`,
  which isn't in the diff. That job calls
  `export_orders(db, customer_id)` once per customer and uploads the result.
- **Callees.** `db.fetch_all` (`db/client.py:31`) passes the parameter tuple to
  the driver as bound parameters.
- **Data.** `orders/importer.py:57` stamps every row of a bulk import with the
  same `created_at`.
- **Error handling.** `api/errors.py` has no handler for `ValueError`, so an
  uncaught one becomes a 500.
- **Ran.** The author is a member of the repo's organization and the branch
  isn't from a fork, so running its code passed the trust gate. In a scratch
  worktree at the PR head, a throwaway test:
  `make_orders(customer_id=7, count=3)` followed by `export_orders(db, 7)`
  returned `[]`.
- **Test revert check.** With the production files restored to the merge base,
  the new test fails with `TypeError: export_orders() got an unexpected keyword argument 'page'`. That
  is a signature failure, not a behavior failure, so it proves nothing about
  paging.
- **CI.** `gh pr checks 482`: all green.

### Candidates dropped during verification

These are not part of the report. They show the verification gate at work.

- **"SQL injection through `page_size`?"** Dropped. The values are bound
  parameters (`export.py:15`, `db/client.py:31`). Nothing is put into the SQL
  string.
- **"Can the paging parameters bypass authorization?"** Dropped. The
  `authorize(...)` call is unchanged, runs first, and checks `customer_id`.
- **"Maybe use keyset pagination instead of OFFSET."** This is a design
  preference and not a defect at 500-row pages. It is mentioned once under
  follow-ups instead.

### Output

```markdown
## Review: Paginate the orders CSV export (482)

**Verdict:** Fix before merge
**Intent:** Page the orders export to bound request time and memory. Not achieved yet: the first page is skipped, and the nightly job silently truncates.
**Scope:** 3 files, +17/-5 at head 3f9c2e1; read jobs/nightly_export.py, db/client.py, orders/importer.py, api/errors.py; ran a throwaway export test in a scratch worktree
**CI:** passing

### Findings
1. [high] First page is never returned - `src/orders/export.py:11` (Confirmed)
   - **Scenario:** the handler defaults `page` to 1 (`src/api/orders.py:42`), so the first request runs `OFFSET 500`. A customer with 500 or fewer orders gets an empty CSV, and everyone else loses their first 500 rows.
   - **Evidence:** `export_orders(db, 7)` with 3 seeded orders returned `[]` in a scratch worktree.
   - **Fix:** `offset = (page - 1) * page_size`, and reject `page < 1` in the handler with a 400.
   - **Verify:** the rewritten test in #4, which asserts the ids on page 1.

2. [high] Nightly export now uploads at most one page - `jobs/nightly_export.py:22` (Confirmed)
   - **Scenario:** the job still calls `export_orders(db, customer_id)` with no paging. It now receives a single page of up to 500 rows (and, with #1, the wrong 500), and uploads that as the complete file. Issue 470 requires the nightly export to keep working.
   - **Evidence:** traced from the job to `export_orders`; the job is not in the diff.
   - **Fix:** loop pages in the job until a short page comes back, or keep an unpaged internal function for the job and page only the HTTP path.
   - **Verify:** a job test that seeds 1,200 orders and asserts all 1,200 reach the uploaded file.

3. [medium] Rows can repeat or vanish between pages - `src/orders/export.py:14` (Likely)
   - **Scenario:** bulk imports give a whole batch the same `created_at` (`orders/importer.py:57`). With `ORDER BY created_at` alone, the database may order tied rows differently on each query, so a row can appear on page 1 and page 2, or on neither.
   - **Evidence:** read the importer; not reproduced, because the order of ties depends on the plan the database picks.
   - **Fix:** add a unique tiebreaker: `ORDER BY created_at, id`.
   - **Verify:** seed rows with one shared `created_at` and assert pages 1 and 2 are disjoint and complete.

4. [medium] The new test can't fail for these bugs - `tests/orders/test_export.py:7` (Confirmed)
   - **Scenario:** `assert len(rows) <= 2` also passes when zero rows come back, and `page=0` exercises a convention the handler never uses. That is why #1 got through.
   - **Evidence:** the revert check failed only on the signature, and the assertion holds for the empty result in #1's reproduction.
   - **Fix:** seed 3 orders, request pages 1 and 2 with `page_size=2` through the handler's 1-based convention, and assert the exact order ids on each page. Add a test for the nightly job's output.
   - **Verify:** the new test fails at the PR head and passes once #1 is fixed.

5. [low] Non-numeric or huge paging params - `src/api/orders.py:42-43` (Likely)
   - **Scenario:** `?page=abc` raises `ValueError`, which becomes a 500 (`api/errors.py` has no handler for it). `?page_size=10000000` brings back the unbounded load this PR set out to remove.
   - **Evidence:** read `api/errors.py`; not executed.
   - **Fix:** parse with validation, return 400 on bad input, and cap `page_size` (for example at 1000).
   - **Verify:** handler tests for `?page=abc` and an oversized `page_size` expecting 400.

### What's good
- The authorization check still runs before the new parameters are read, and the paging values are bound parameters, not string-formatted.

### Not reviewed / follow-ups
- If exports keep growing, keyset pagination (`WHERE (created_at, id) > (...)`) avoids deep-OFFSET scans. A follow-up for `review-suite:performance-review`; it doesn't block this PR.
```

---

## 2. Comment rules and phrasing: weak vs strong

These rules apply to the report and to anything posted on the PR.

- **Lead with the problem and its scenario, then the fix.** Authors fix what
  they understand. A bare "this is wrong" starts an argument.
- **Suggest code when the fix is small.** On GitHub, a `suggestion` block lets
  the author apply it in one click.
- **Ask real questions when you are unsure.** Don't phrase demands as
  questions, or questions as demands.
- **Talk about the code, not the person.** "This returns null when..." rather
  than "you forgot...".
- **One issue per comment.** If a pattern repeats, comment once and list the
  other locations.
- **Cap the nits.** Batch them into one comment. If a formatter could fix them,
  suggest configuring the formatter instead.
- **Put a severity label on every comment,** so the author knows what blocks
  the merge and what doesn't.
- **Praise rarely and specifically.** Reflexive praise makes all of it worth
  less.
- **Don't reopen settled decisions** from the thread or a linked design doc
  unless you have new evidence.

A strong finding names the location, gives the scenario and the consequence,
and offers a fix. A weak one leaves the author to rediscover all of that, or to
argue.

**TypeScript, high**

- Weak: "This async stuff looks wrong."
- Strong: "**high:** `notifyAll` (`src/notify.ts:18`) runs
  `users.forEach(async (u) => await send(u))`. `forEach` doesn't wait for the
  returned promises, so `notifyAll` resolves before any email is sent, and a
  rejected `send` becomes an unhandled rejection. The job runner then marks the
  job done even when every send failed. Suggest
  `await Promise.all(users.map(send))`, or a `for...of` loop if the sends must
  happen in sequence."

**Go, critical**

- Weak: "Possible nil problem here."
- Strong: "**critical:** `Tally` (`internal/report/tally.go:52`) writes to
  `counts`, which is declared `var counts map[string]int` at line 40 and never
  `make`d. The first write panics with `assignment to entry in nil map`, so
  every request to the report handler (`api/report.go:30`) fails. Initialize
  it at line 40: `counts := make(map[string]int)`."

**Java, high**

- Weak: "Use equals."
- Strong: "**high:** `order.getStatus() == "SHIPPED"`
  (`OrderService.java:112`) compares references. The status comes from the
  JSON deserializer as a new `String`, so the check is false even for shipped
  orders, and no customer ever gets a tracking email.
  `"SHIPPED".equals(order.getStatus())` also handles null."

**Question (any language)**

- Weak: "Did you even think about retries?"
- Strong: "**question:** If the payment provider times out after charging,
  the queue redelivers this message (at-least-once, per `config/queue.yml`). I
  couldn't find an idempotency key on `charge()` (`billing/client.py:40`). Is
  there deduplication somewhere I missed?"

**Nit**

- Weak: five separate comments about variable names.
- Strong: one comment: "nits, none blocking: `tmp2` would read better as
  `pendingInvoices` (line 30); `data` would read better as `rows` (line 44); the
  docstring on line 12 still mentions the removed `force` flag."

**Praise**

- Weak: "Great job!!"
- Strong: "Nice: the table-driven test covers the empty, maximum-length, and
  invalid-UTF-8 inputs, which is exactly where this parser broke last time."
