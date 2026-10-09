# Subagent Prompt Templates

Fill these in for each task you hand off in subagent mode. The protocol (when to delegate,
the independence test, report handling, the review rubric) is in
[subagent-mode.md](subagent-mode.md).

## Contents

1. The cold-reader test
2. Implementer prompt template
3. Filled example
4. Revision prompt template
5. Reviewer prompt template (optional)

---

## 1. The cold-reader test

An implementer subagent starts with **none** of your conversation: not the plan review, not
the user's answers, not what earlier tasks discovered. Before you dispatch, re-read the
prompt as a capable engineer who has just cloned the repository. Ask yourself:

- Could they finish the task with only this text and access to the repository?
- Do they know exactly which files they may touch, and which they must not?
- Do they know which existing tests the task is expected to change, if any?
- Do they know what "done" looks like, as commands they can run?
- Do they know the names and interfaces that later tasks depend on?
- Do they know what to do when something doesn't fit (stop and report, rather than
  improvise)?

These phrases mean the prompt is not self-contained yet:

- "as discussed"
- "see the plan" (the implementer can't see the plan unless you give the path *and* the
  section)
- "the usual pattern"
- "fix the issue from before"
- "same as T3"

Paste the relevant text instead of referring to it.

---

## 2. Implementer prompt template

Replace every `{…}`. Delete optional lines that don't apply, but keep every section heading,
so that missing information stands out.

The report shape at the end is deliberately strict. A `REQUIREMENTS TRACE` gives you a list
to check in Pass 1 instead of one to rebuild. `FILES TOUCHED` lets you compare against
`git status` mechanically. A single `STOP_REASON` tells you which response to make
(subagent-mode.md section 5).

````text
You are implementing ONE task from a larger implementation plan. You have no access to the
conversation that produced this prompt; everything you need is below. If something you need
is missing or contradictory, stop and report OUTCOME: stopped rather than guessing.

## Task
ID: {T5}
Title: {short title}
Task text (verbatim from the plan):
> {paste the task exactly as written, including its verification line}

## Why this task exists
{1-3 sentences: the feature goal, and what this task contributes to it.}
Later tasks depend on these exact names/interfaces from this task:
- {e.g. function `applyDiscount(cart: Cart, coupon: Coupon): Money` exported from src/cart/pricing/index.ts}

## Where to work
Working directory: {absolute path to repo or worktree}
Branch: {branch name}
Files you may create or modify:
- {path}: {what changes}
- {path}: {what changes}
Existing tests expected to change: {path::test name: old expectation -> new expectation, and why | none}
Read these first for patterns (do not modify):
- {path}: {why it's a good example}
- {path}: {existing helper you should reuse instead of writing a new one}

## Conventions
- {error handling, e.g. "return Result types; never throw from domain code, see src/cart/errors.ts"}
- {naming / layering rule}
- {test style, e.g. "one describe per function, table-driven cases, no snapshot tests"}
- Format/lint before finishing: `{command}`

## Out of scope: do NOT do these
- {adjacent work that belongs to another task, e.g. "UI changes (T7)"}
- {tempting refactor}
- Do not modify any existing test other than those listed under "Existing tests expected to
  change", and never loosen an assertion to make it pass. Do not add or upgrade
  dependencies, change CI/build config, create local config files (such as .env), or touch
  files outside the list above. If one of these seems necessary, stop with
  STOP_REASON: scope and explain why.

## Acceptance checks (all must pass before you report done)
1. `{command}`: {expected result, e.g. "all tests pass, including the new ones"}
2. `{command}`: {expected result}
3. {behavioural criterion, e.g. "the new cap test fails ON ITS ASSERTION (not an import or
   type error) when the cap line is removed; confirm once, then restore the line"}
Report each check with its actual counts (passed / failed / skipped).

## Constraints
- Commit policy: {Do NOT commit. Leave all changes in the working tree.}
                 {OR: Commit on branch {branch} only, message "{type(scope): summary}",
                  with trailer: --trailer "Plan-Task: {T5}". Do not touch other branches.}
- Work alone: do not start subagents of your own. Their edits would land in this working
  directory without appearing in your report.
- Never push, open pull requests, delete branches, or run anything that affects systems
  outside this working directory.
- Test-first: {yes: write the failing test, run it, see it fail for the expected reason,
  then implement | no}
- Attempt budget: if the checks still fail after 3 genuinely different fix attempts, stop
  with STOP_REASON: attempt-budget, listing what you tried and what you observed.
- If the checks fail before you change anything, stop with STOP_REASON: baseline-red and
  quote the failing test names.

## Report back in exactly this shape (under 40 lines; no full logs)
OUTCOME: done | stopped
STOP_REASON: none | missing-context | needs-decision | scope | environment | baseline-red | attempt-budget
REQUIREMENTS TRACE: (one row per requirement in the task text)
- R1 {requirement, in your words}: {file:line} | not done: {why}
FILES TOUCHED:
- {path}: {created | modified | deleted} {"(NOT in allowed list)" if so}
CHECKS RUN:
- `{command}` -> {passed / failed / skipped counts}
MUTATION CHECK: {line you broke -> test that failed and its assertion message} | n/a
ASSUMPTIONS: {every choice the task text did not settle, one per line} | none
STOP DETAIL: {only when stopped: what you need, the options you see, your recommendation}
SUMMARY: {2-4 lines on what you changed and why}
````

---

## 3. Filled example

````text
You are implementing ONE task from a larger implementation plan. You have no access to the
conversation that produced this prompt; everything you need is below. If something you need
is missing or contradictory, stop and report OUTCOME: stopped rather than guessing.

## Task
ID: T3
Title: Apply percentage discounts with per-item cap
Task text (verbatim from the plan):
> T3. Add `applyDiscount(cart, coupon)` that applies a percentage coupon to eligible items,
> capping each item's discount at `coupon.maxPerItem`. Round with the existing money
> rounding helper. Verify: `npx vitest run src/cart` passes with new cases for cap, no-cap,
> and ineligible items.

## Why this task exists
Checkout is adding coupon support. T4 persists the computed discount and T5 displays it, so
both call this function.
Later tasks depend on:
- `applyDiscount(cart: Cart, coupon: Coupon): DiscountResult` exported from
  src/cart/pricing/index.ts, where `DiscountResult` = `{ lines: DiscountLine[]; total: Money }`

## Where to work
Working directory: /home/dev/shop
Branch: feat/coupons
Files you may create or modify:
- src/cart/pricing/index.ts: add and export applyDiscount and DiscountResult
- src/cart/pricing/discount.test.ts: new test file
Existing tests expected to change: none
Read these first for patterns (do not modify):
- src/cart/pricing/tax.ts: same shape of per-line calculation; mirror its structure
- src/money/round.ts: use `roundHalfEven`; do not write new rounding code

## Conventions
- Money is integer minor units (`Money` type); never use floating-point currency.
- Pricing functions take every input as a parameter (including dates); they never read the database or the current time.
- Tests: table-driven `it.each`, one describe per exported function.
- Format/lint before finishing: `npm run lint -- src/cart`

## Out of scope: do NOT do these
- Persisting the discount (T4) or any UI (T5).
- Refactoring tax.ts even if you spot duplication; mention it in SUMMARY instead.
- Do not modify any existing test other than those listed under "Existing tests expected to
  change", and never loosen an assertion to make it pass. Do not add or upgrade
  dependencies, change CI/build config, create local config files (such as .env), or touch
  files outside the list above. If one of these seems necessary, stop with
  STOP_REASON: scope and explain why.

## Acceptance checks (all must pass before you report done)
1. `npx vitest run src/cart`: all pass, including at least: cap applied, cap not reached,
   ineligible item untouched, 0% coupon.
2. `npx tsc --noEmit`: no errors.
3. The cap test fails on its assertion (not an import or type error) when the cap line is
   removed. Confirm it once, then restore the line.
Report each check with its actual counts (passed / failed / skipped).

## Constraints
- Commit policy: Do NOT commit. Leave all changes in the working tree.
- Work alone: do not start subagents of your own. Their edits would land in this working
  directory without appearing in your report.
- Never push, open pull requests, delete branches, or run anything that affects systems
  outside this working directory.
- Test-first: yes. Write the failing tests, run them, see them fail for the expected reason,
  then implement.
- Attempt budget: if the checks still fail after 3 genuinely different fix attempts, stop
  with STOP_REASON: attempt-budget, listing what you tried and what you observed.
- If the checks fail before you change anything, stop with STOP_REASON: baseline-red and
  quote the failing test names.

## Report back in exactly this shape (under 40 lines; no full logs)
OUTCOME:
STOP_REASON:
REQUIREMENTS TRACE:
FILES TOUCHED:
CHECKS RUN:
MUTATION CHECK:
ASSUMPTIONS:
STOP DETAIL:
SUMMARY:
````

A good report for this task would trace at least four requirements: percentage applied to
eligible items, per-item cap, rounding through `roundHalfEven`, and ineligible items
untouched. Each row would point to a line in `index.ts`. `ASSUMPTIONS` would name anything
the text left open, such as "a coupon with maxPerItem = 0 means no cap", and the coordinator
must settle each one before Pass 1.

---

## 4. Revision prompt template

When the harness can resume the same implementer, send only the part above the
`--- ORIGINAL TASK PROMPT ---` line; it still has the original. When you dispatch a fresh
implementer instead, append the original prompt unchanged so it has the full contract again.

````text
This is a revision of task {T5}. A previous attempt is already in the working directory
{absolute path} (branch {branch}). Do not start over; correct the specific findings below
and change nothing else.

Revision round {1|2} of 2.

Findings to fix:
1. {file:line}: {what is wrong}. Expected: {what the task requires}.
   I will check: {command / observable result}
2. {…}

Keep: {anything the reviewer confirmed is correct and must not change}

Report back in the same shape as the original prompt.

--- ORIGINAL TASK PROMPT ---
{paste the original implementer prompt unchanged}
````

---

## 5. Reviewer prompt template (optional)

Use this for a large diff or when you want independent eyes. You still re-run the checks
and make the decision yourself.

````text
You are reviewing ONE task's implementation against its specification. Do not modify any
files. Report findings only.

## Task under review
ID: {T5}
Task text (verbatim):
> {…}
Contracts later tasks rely on: {names / signatures / schemas}
Allowed files: {list}
Existing tests expected to change: {list with old -> new expectation | none}

## How to see the change
Working directory: {absolute path}
{Sequential mode: `git status --porcelain` and `git diff` (also read any untracked files listed)}
{Parallel mode: `git diff {base}...{branch}` and `git log --oneline {base}..{branch}`}
Acceptance checks: {commands}. Run them and report the actual counts.

## Review in two passes, in this order
Pass 1, spec compliance: list the task's requirements and point each one to the line that
satisfies it (or "missing"). Does the change do nothing the task doesn't ask for, touch only
allowed files, and match the contracts exactly? Do the tests exercise the real behaviour,
and would they fail on an assertion (not an import or type error) without the change?
Pass 2, code quality (only if Pass 1 has no failures): fit with surrounding patterns,
duplication of existing helpers, error handling, test quality, obvious performance traps.
Red flags to call out explicitly: existing assertions modified or deleted beyond the
expected-change list, loosened assertions, regenerated snapshots, new dependencies, broad
catches, lint/type suppressions, skip/only markers, config changes.

## Report in exactly this shape (under 40 lines)
VERDICT: accept | revise
PASS 1 (spec): pass | fail
- R1 {requirement}: {file:line} | missing
- {file:line}: {finding}: {why it violates the task}
PASS 2 (quality): pass | must-fix | follow-ups-only | not reviewed
- {file:line}: {finding}: {must-fix | follow-up}
CHECKS: `{command}` -> {result with counts}
````
