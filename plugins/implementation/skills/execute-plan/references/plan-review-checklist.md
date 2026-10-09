# Plan Review Checklist

Use this before writing any code. The goal is to find out, cheaply, whether the plan can be
executed as written against the codebase as it is **today**.

## Contents

1. How to run the review
2. The checklist (nine areas)
3. Severity guide
4. Worked example

---

## 1. How to run the review

1. **Read the whole plan without stopping to act.** Note every file, symbol, command,
   dependency and external system it names.
2. **Read the inputs the plan cites**: the spec, ADRs, linked issues. A plan can be
   consistent with itself and still drift from the spec it implements.
3. **Open the code each task touches.** Spend about as long on this as one task will take to
   implement. A 20-task plan deserves a real look; a 3-task plan needs only a quick
   confirmation.
4. **Check claims mechanically wherever you can.** Search the code and run `--help`. Look in
   the lockfile. Don't rely on what the plan says or what you remember.
5. **Write findings as you go**, with evidence, then classify them (section 3).

Useful mechanical checks:

```bash
git ls-files | grep -i discount          # does the file the plan names exist (or did it move)?
grep -rn "applyDiscount" src/            # does the symbol exist, and with what signature?
git log --oneline -5 -- src/cart/        # has this area changed since the plan was written?
```

`rg -n "applyDiscount" src/` is a faster equivalent of the grep if ripgrep is installed.
To check that a command exists, look at the project's scripts (`package.json` "scripts",
Makefile targets, `pyproject.toml` tool config, CI workflow steps) or run it with `--help`.

---

## 2. The checklist

### A. Structure: can each task be executed at all?

- [ ] Each task has a stable identifier (number or id) you can carry into commits and reports.
- [ ] Each task names **what** changes and **where** (files or modules).
- [ ] Each task has a **verification**: a command, a test, or an observable result.
- [ ] Each task has a clear **done** state. "Improve error handling" is not one; "invalid
      coupon returns 422 with code `COUPON_INVALID`" is.
- [ ] Tasks are small enough to verify and commit independently. If one task touches ten
      files across three layers, propose splitting it.

### B. Reality: does the codebase match what the plan assumes?

- [ ] Named files and directories exist at the stated paths.
- [ ] Named functions, classes, endpoints, tables, config keys and environment variables
      exist, with the signatures and shapes the plan assumes.
- [ ] Named dependencies are installed, and at a version that has the API the plan uses.
- [ ] Commands the plan runs exist and work in this repo.
- [ ] The plan's base matches what is checked out. If the plan cites a commit, compare it
      with `git log` for the touched paths.

### C. Order and intermediate states

- [ ] No task uses something a later task creates.
- [ ] If the plan commits after each task, each intermediate commit builds and passes its
      tests. A plan that "temporarily breaks the build until task 5" needs those tasks
      merged, or a different order.
- [ ] Tasks that change a shared interface come before the tasks that consume it, or the
      plan says how callers stay compatible in between.

### D. Consistency

- [ ] Tasks don't contradict each other (task 2 says "store in cents", task 6 says "store as
      decimal").
- [ ] The plan agrees with its spec and ADRs. Every spec requirement maps to at least one
      task, and nothing in the plan goes beyond the spec without saying why.
- [ ] The plan follows the codebase's conventions for error handling, naming, layering,
      test style and configuration. If it departs from them, it does so on purpose and says
      so.

### E. Hidden decisions

- [ ] User-visible behaviour is specified: messages, status codes, defaults, empty states,
      ordering, rounding.
- [ ] Data shape decisions are specified: nullability, units, precision, time zones,
      identifiers, retention.
- [ ] Failure behaviour is specified: what happens on timeout, partial failure, retry,
      duplicate submission.

Unspecified items are **Decision needed** when the user would care about the answer. When a
codebase convention already answers them, they are **Notes**.

### F. Risk and authorization

These steps need explicit authorization, either in the plan or from the user, before you
run them:

- [ ] Schema or data migrations, especially destructive ones (drop, rename, backfill).
- [ ] Deleting code, files, data, branches or feature flags that someone may depend on.
- [ ] Public API, event, file-format or contract changes seen by other teams or clients.
- [ ] Dependency additions or major-version upgrades.
- [ ] Anything that acts outside the repository: shared or production environments,
      publishing packages, sending email or messages, calling paid APIs, changing secrets or
      access.

For data and migration steps, use `data-api:db-migration-safety` if it is installed.

### G. Verification quality

- [ ] Each check **can fail**. A test that already passes before the change does not prove
      the change.
- [ ] Each check is **specific**. "Run the app and make sure it works" is not a check. "POST
      /cart/coupons with an expired code returns 422" is.
- [ ] Checks don't depend on manual steps you cannot perform. If one does, plan to report
      it as a human verification step.
- [ ] Existing tests that assert behaviour the plan changes are accounted for. Search for
      the old value or behaviour in the test tree. Raise each one the plan doesn't mention:
      as a **Note** when it is an internal test the task plainly supersedes (you will update
      it within that task), and as **Decision needed** when it guards a published contract
      such as a public API, file format or partner integration.
- [ ] The plan has top-level acceptance criteria for the whole change, not only per task.

### H. Scope

- [ ] Nothing in the spec is missing from the plan.
- [ ] Nothing in the plan is speculative ("also add caching in case it's slow").
- [ ] Docs, migrations, configuration and feature-flag tasks are included where the change
      needs them.

### I. Environment prerequisites

- [ ] Required services (database, queue, emulator), credentials, fixtures and seed data
      are available to you, or the plan says how to obtain them.
- [ ] Network or platform requirements are achievable from where you are running.

---

## 3. Severity guide

| Severity | Meaning | Examples | What you do |
|---|---|---|---|
| **Blocker** | Executing as written builds the wrong thing or cannot work | Core API doesn't exist; two tasks contradict on data shape; spec requirement missing with no workaround | Don't start. Report with options |
| **Decision needed** | A choice the user owns; work not depending on it can proceed | Unspecified rounding rule; error message wording; whether to keep a deprecated endpoint | Ask, with a recommendation. Proceed on independent tasks only if the user agrees |
| **Note** | You can resolve it without changing what ships | File moved; helper renamed; missing verification you can add; stale line numbers | Fix as you go and log it |

When unsure between Note and Decision needed, ask yourself whether the reviewer would want a
say. If they would, it's a Decision needed.

---

## 4. Worked example

Plan excerpt:

> T2. Add `applyDiscount(cart, coupon)` in `src/cart/pricing.ts`; verify with
> `npm test -- pricing`.
> T3. Persist `discount_total` on orders (migration `0042_add_discount_total`).
> T4. Show the discount on the order summary page.

Findings after review:

```text
Plan review: docs/plans/coupons.md (T1-T6) at a1b2c3d

Blocker
  none

Decision needed
  D1 (T2, T3) Rounding for percentage discounts is unspecified. Order totals use
     banker's rounding (src/money/round.ts:14). Recommend the same for discounts.
  D2 (T3) Migration 0042 is already taken (migrations/0042_add_gift_cards.sql,
     merged last week). Recommend renumbering to the next free number. Data
     impact: none (new nullable column).

Notes (will handle and log)
  N1 (T2) pricing.ts was split; the pricing functions now live in
     src/cart/pricing/index.ts. Will add applyDiscount there.
  N2 (T4) No verification given. Will add a component test asserting the
     discount line renders, plus the empty case.

Baseline (full)
  npm test: 412 passed, 2 failed (pre-existing, src/search/*; unrelated to this plan;
    both failed again on re-run, so broken rather than flaky)
  npx tsc --noEmit: clean

Ledger: docs/plans/coupons.md, "Execution notes > Progress"
T1 does not depend on D1 or D2. Reply "start T1" if you want it done while you decide;
otherwise I'm waiting on D1 and D2 before starting anything.
```

The review is short, every claim carries evidence, and each question comes with a
recommended answer.
