# Finding schema (the persona output contract)

Return your review in exactly this shape. A program-like aggregator merges every reviewer's output, so a missing field or a different shape can cause your findings to be dropped.

## Return format

Return one JSON object and nothing else: no prose before it and no prose after it. A fenced `json` block is acceptable.

```json
{
  "persona": "security",
  "coverage": "Traced the 3 new endpoints from routing to data access; read auth middleware and the upload handler. Did not run anything. Did not review the admin UI templates.",
  "findings": [
    {
      "id": "SEC-1",
      "severity": "high",
      "location": "src/orders/handlers.py:88-97",
      "also_at": ["src/orders/handlers.py:131"],
      "title": "Order lookup trusts the order id from the URL without an ownership check",
      "failure_scenario": "A signed-in user sends GET /orders/1042, where 1042 belongs to another customer, and receives that customer's order, address, and payment summary.",
      "evidence": "handlers.py:88 loads Order.get(id=request.path_params['id']) and returns it at :97. There is no filter on request.user. The route decorator at :80 only checks that the user is authenticated. Compare handlers.py:40, where list_orders filters by user_id.",
      "suggested_fix": "Scope the query to the caller (Order.get(id=..., customer_id=request.user.customer_id)) and return 404 on a miss. Add a test that requests another user's order.",
      "confidence": "high"
    }
  ],
  "hardening": [
    "src/orders/handlers.py:12: session cookie lacks SameSite; no exploit path today because every state change also checks a CSRF token"
  ]
}
```

An empty `findings` array is a valid, useful result. Never pad it to look productive. `hardening` is optional; leave it out or empty when there is nothing to add.

## Field rules

| Field | Rule |
|---|---|
| `persona` | The persona slug from the brief. |
| `coverage` | 1–3 sentences: what you examined, what you could not examine, and any assumption the whole review depends on. If you could not view the change at all (a command was denied or failed, files were missing), make that the first sentence. The final report's coverage section is built from this. |
| `id` | Persona prefix plus a sequence number: `COR`, `SEC`, `PERF`, `DATA`, `ARCH`, `TEST`, `API`, `REL`, `UX`. Example: `PERF-3`. |
| `severity` | `critical`, `high`, `medium`, or `low`, using the severity levels below. |
| `location` | `path:line` or `path:start-end`. Paths are relative to the repository root, and line numbers refer to the pinned head revision named in the brief. Point at the line that has to change, not at the first line of the file. |
| `also_at` | Optional. Other locations that have the same root cause. Use this field for them; do not file a separate finding for each one. |
| `title` | One sentence, at most about 100 characters, naming the defect. "Missing ownership check on order lookup" is a title. "Security issue" is not. |
| `failure_scenario` | Concrete input or state, then the wrong outcome. Name who triggers it, how they trigger it, and what happens. If you cannot write a concrete scenario, you do not have a finding. |
| `evidence` | Why this is true, with `file:line` citations. Quote the code, describe the path through callers, or cite command output. If you inferred something without reading it, label it as an inference. Never quote a secret value (key, token, password, connection string): show at most its first four characters followed by "…", plus `file:line`. |
| `suggested_fix` | The smallest change that removes the failure. Sketch it in prose or a few lines of code, and mention the test that would catch a regression. |
| `confidence` | `high`, `medium`, or `low`, using the rubric below. Severity and confidence are independent. A critical finding can have low confidence. |
| `hardening` | Optional top-level list of short strings, `path:line: what is weak, and why it matters later`. Use it for a weakness with no failure or exploit path today. These get no severity and no verification, and appear in the report's Hardening list. |

## Severity levels

The levels, verdict ladder, and finding format below are shared word for word with the other review skills. As a persona, use only the four levels `critical`, `high`, `medium`, and `low` in `severity` (never `nit`), and put hardening in `hardening`, not in `findings`. The verdict and the written finding format are applied later, by whoever writes the final report.

<!-- shared:severity v1 -->
**Severity.** Rate impact times likelihood on a path that is actually reachable, not how hard the fix is. A problem nothing can reach is never above `low`. Don't inflate a finding to get attention or soften one to be polite.

| Level | Meaning | Merge effect |
|---|---|---|
| `critical` | Realistic use or attack causes data loss or corruption, a security breach, an outage, or money moved or charged wrongly, or existing clients break with no migration path. | Block |
| `high` | Wrong behavior on a common path, or a serious failure that is plausible under normal conditions: ordinary concurrency, a rollback, a large table, near-term growth. | Fix before merge |
| `medium` | Wrong behavior on an edge path, a gap that makes a defect likely soon, or a cost that bites only at much larger scale. | Fix before merge, or a tracked follow-up the reviewer agrees to |
| `low` | Real, but low impact. | Author's call |
| `nit` | Taste or polish with no effect on behavior. Only reports that have a Nits section use it. | Author's call |

**Verdict.** Take the first line that applies, so the same findings always get the same verdict:

1. **Block**: any `critical`.
2. **Fix before merge**: any `high`.
3. **Merge with follow-ups**: `medium` findings only, each fixed or tracked.
4. **Merge**: only `low` or `nit` findings, or none.

A skill may add one qualifier of its own in parentheses, for example `Fix before merge (needs measurement)`. When nothing is pending to merge, as in a review of a path or module, read the four levels as fix now, fix soon, schedule, and healthy.

**Outside the verdict.** Pre-existing problems (already present at the merge base) and hardening notes (no failure or exploit path today) each get their own section. A pre-existing problem keeps its severity, because an old `critical` still matters, but neither kind counts toward the verdict.

**Finding format.** Number findings across the whole report so they can be cited as "#3". Each starts with a title line, as a list item or a heading:

`N. [<level>] <title> - path:line (Confirmed | Likely)`

**Confirmed** means reproduced, or traced end to end in the code. **Likely** means traced, with one link unverified; name it. Then:

- **Scenario:** the input or state, what the code does, and what should happen instead.
- **Evidence:** the path you traced, the command you ran, or the output you read.
- **Fix:** the smallest change that removes the problem.
- **Verify:** the regression test or measurement that fails before the fix and passes after.

A skill may add fields after these. A short review may use a table with the same level column instead.
<!-- /shared:severity v1 -->

Leave out formatting, naming preferences, and anything a linter, formatter, type checker, or compiler in the project's CI would catch. Those are not findings.

## Confidence rubric

| Confidence | Meaning |
|---|---|
| `high` | You traced the path and confirmed it: you read the callers, checked upstream guards, and found nothing that prevents the failure. |
| `medium` | The code reads as broken, but one assumption is unverified. Name that assumption in `evidence`, for example "assumes no middleware re-validates this; did not find one in app/middleware/". |
| `low` | The failure is plausible, but you could not confirm the path, or the outcome depends on runtime configuration you cannot see. |

## Scope rules for findings

- **Introduced versus pre-existing.** When the target is a diff, report issues the change introduces, makes worse, or newly exposes. For a pre-existing issue that the change does not touch, begin the title with `[pre-existing]`, and report it only if it is high or critical. When the target is a whole module or path, everything in it is in scope.
- **One root cause, one finding.** When the same mistake appears in several places, file one finding and list the other places in `also_at`.
- **Stay in your lane.** Hunt only for your persona's concerns. If you happen to see a serious issue in another area, you may report it, but do not go looking.
- **Cap.** Report at most the number of findings the brief allows, keeping the most severe. Note in `coverage` if you stopped because you hit the cap.
