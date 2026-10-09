# Report Templates

Five messages come up while you execute a plan. Use these shapes so the user can read any of
them in seconds and knows exactly where things stand.

## Contents

1. Writing principles
2. Plan review message
3. Batch progress report
4. Decision record entry
5. Stop / escalation message
6. Final report

---

## 1. Writing principles

- **Evidence, not narration.** Give the command and its result, a commit id, or `file:line`.
  "I carefully implemented…" tells the reader nothing they can check.
- **Numbers, not adjectives.** "18 passed, 0 failed, 0 skipped" rather than "tests look good".
- **Compare with the baseline.** "2 failures, both pre-existing (same as baseline)" is a very
  different message from "2 failures".
- **Name anything unverified.** If a check could not run, or needs a human (a visual check,
  a real device, production data), say so plainly. Never let silence imply it passed.
- **Put what you need from the user first** when you need something, and number it so they
  can answer "1: A, 2: yes".
- **Keep it short.** Leave out full logs and full diffs. Quote only the lines that matter.

---

## 2. Plan review message

Send this once, before any code. A filled example is in
[plan-review-checklist.md](plan-review-checklist.md) (section 4).

```text
Plan review: {plan path or title} ({task range}) at {base commit short sha}

Blockers
  {B1 (Tn): finding. Evidence: file:line / command output. Options: A … / B … Recommend: …}
  {or "none"}

Decision needed
  {D1 (Tn): question. Evidence: … Recommend: …}
  {or "none"}

Notes (will handle and log)
  {N1 (Tn): finding and how you will handle it}

Baseline ({full | scoped to <areas>; full suite deferred to checkpoints because <reason>})
  {test command}: {passed/failed/skipped}; pre-existing failures: {list or "none"}
  Flaky (failed, then passed on re-run): {test names or "none"}
  Not run here: {check: why, e.g. "integration suite: needs a message broker" or "none"}
  {lint/type/build}: {result}

Plan: {n} batches: {B1: T1-T3, B2: T4 (migration, checkpoint after), B3: T5-T7}
Ledger: {plan path, "Execution notes > Progress" | carried in each report}
Next: {what you will start, and whether you are waiting for answers}
```

---

## 3. Batch progress report

Send this at the end of every batch, whether or not you are stopping.

```text
Progress: {plan title}, batch {n} of {N} ({task ids}): {on track | needs input | stopped}

Done
  {T3}  {title}                    {sha}  {check: result with counts}
  {T4}  {title}                    {sha}  {check: result with counts}
Not done
  {T5}  {title}                    {blocked | deferred | in progress}: {one-line reason}

Deviations and decisions this batch
  {D3 (T4): one line; mechanical | material (approved by …)}   {or "none"}

Needs you
  1. {question}: options {A/B}; recommend {A} because {reason}   {or "nothing"}

Overall
  {k}/{total} tasks done. {Full suite | Batch's scoped checks: <commands>} vs baseline:
  {e.g. "same 2 pre-existing failures, no new ones"}

Ledger   (only when the plan lives outside the repository)
  {T1 done | T2 done | T3 done | T4 done | T5 todo | T6 todo | T7 todo}

Next
  {Batch n+1: T6-T7, one-line description}. {Continuing unless you say stop. | Paused at the
  plan's checkpoint; reply to continue.}
```

Example:

```text
Progress: Coupons, batch 2 of 3 (T3-T4): on track

Done
  T3  Apply percentage discounts with cap   9f2c1ab  vitest src/cart: 18 passed; tsc clean
  T4  Persist discount_total (0043)         4be77d0  migration up+down OK; full suite 430 passed
Not done
  none

Deviations and decisions this batch
  D2 (T4): migration renumbered 0042 -> 0043 (approved in plan review)
  N3 (T3): tests placed in src/cart/pricing/ to match neighbours (plan said test/cart/); mechanical

Needs you
  nothing

Overall
  4/7 tasks done. Full suite vs baseline: same 2 pre-existing failures (src/search), no new ones.
  (Ledger is in docs/plans/coupons.md, so no Ledger block here.)

Next
  Batch 3: T5-T7 (order summary UI, email receipt line, docs). Continuing unless you say stop.
```

---

## 4. Decision record entry

Write one entry per decision, whether you made it or the user did. Append the entries to the
plan file under `## Execution notes` when the plan lives in the repository. Otherwise, include
them in the reports.

Commit each entry with the task it concerns by adding the plan path to that task's explicit
`git add`. Commit a decision made at a checkpoint on its own, as `docs(plan): record D2`,
before the next batch starts. Plan edits never stay uncommitted across a checkpoint.

The top of the Execution notes section holds the ledger:

```markdown
## Execution notes

### Progress
| Task | Status | Note |
|---|---|---|
| T1 | done | |
| T2 | done | N1: pricing lives in src/cart/pricing/index.ts |
| T3 | in progress | |
| T4 | todo | checkpoint after |
```

Commit hashes are not stored here, because a commit cannot contain its own hash. The
`Plan-Task:` trailer links each commit to its row.

```markdown
### D2: T4: migration number
- Plan said: create migration `0042_add_discount_total`.
- Found: `0042` is already used by `0042_add_gift_cards` (in the base branch history).
- Decision: use `0043_add_discount_total`; no other change.
- Decided by: user, in reply to plan review    <!-- or: executor (mechanical) -->
- Consequence: file name only; T5's reference to the migration updated.
```

Keep mechanical notes to one line (`N3 (T3): tests live in src/cart/pricing/, not test/cart/`).
A material decision gets the full entry. If it changes what later tasks do, update the plan's
task text as well, but only for a decision the user approved (or delegated by saying "proceed
without check-ins"). Cite the id beside the edit, for example "(per D2)".

---

## 5. Stop / escalation message

```text
Stopped at {Tn}: {one-line reason}

What happened
  {2-4 lines of facts}
Evidence
  {command} -> {the relevant output lines}
  {file:line}: {what it shows}
Options
  A. {option}: {effect on the plan, risk, extra work}
  B. {option}: {…}
Recommendation
  {A}, because {reason}.
Meanwhile
  {Safe to continue with T7 and T8 (independent of Tn). | Nothing else is safe to start.}
State
  Last commit {sha} ({Tm}). Working tree: {clean | uncommitted changes in <paths>, unverified}.
```

---

## 6. Final report

The same template appears in SKILL.md under "Report format". It is Markdown with an H2
title, because it is the run's closing report rather than a status line.

```markdown
## Plan complete: {plan title} ({k}/{N} tasks done, {d} deferred)

**Branch:** {name}, {c} commits on {base sha}
**Verification vs baseline at {base sha}:**
- Tests: {result with counts; pre-existing failures named}
- Lint/type: {result}
- Build: {result}

**Plan acceptance criteria:**
- [x] {criterion}: {evidence}
- [ ] {criterion}: not verified, needs {a human / a device / production data} because {reason}

**Deviations and decisions:** {count}, recorded in {plan path, "Execution notes" | the reports}
**Deferred:** {Tn: reason, agreed by …} | none
**Follow-ups noticed, not done:** {list} | none
**Not done on purpose:** no push, PR, merge or deploy.
**Next:** {e.g. review the branch, then I can draft the PR description}
```
