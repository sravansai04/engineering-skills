# PR Body Template and Section Guide

Use this when the repository has no PR template of its own, or to check what a section should contain. If the repository does have a template, its structure wins. Use this file only to decide what to put under its headings.

Contents:
1. Default skeleton
2. Section guide
3. Risk levels
4. Rollback: when "just revert" is true
5. Variants: trivial, stacked, large

## 1. Default skeleton

Delete any section that doesn't apply, except where the size table in SKILL.md says to keep it. Remove all guidance comments and unused placeholders before posting; if the repository squash-merges with the PR body as the commit message, they would otherwise become permanent history.

```markdown
## Summary

<!-- Problem → change → why this approach. 2–4 sentences, for a reviewer new to this area. -->

## Reviewer guide

<!-- Large or risky PRs only; delete otherwise. Start here → most scrutiny here (why) → skimmable parts. -->

## Key changes

<!-- 3–7 bullets grouped by behavior/concern. What changed + its effect. Not a file list. -->
-
-

## How it was tested

<!-- Exact commands and observed results; manual steps with environment; what was NOT tested and why. -->
- `command` → result
- Manual: steps → what you saw
- Not tested: what, and why

## Risk & rollout

**Risk: Low / Medium / High**, because ...

- Feature flag: `flag_name`, default off in all environments; who enables it
- Migrations: what runs, in which order relative to the deploy, and whether old code works with the new schema
- Backward compatibility: clients, stored data, messages, config
- Rollback: revert is safe / steps if not
- Watch after deploy: metric, log line, or dashboard and what "bad" looks like

## Screenshots

| Before | After |
|---|---|
| (drag image here) | (drag image here) |

## Breaking changes

<!-- Only if any. Who is affected, what they must do, deprecation path. -->

## Follow-ups / out of scope

-

Closes #
```

## 2. Section guide

**Summary**
- Open with the problem as the user or system experiences it, not with the code. "Customers billed before a timeout got a second invoice" beats "Added idempotency to `create_invoice`".
- Then say what the PR does about it, and why this approach was chosen over the obvious alternative if a reviewer would wonder.
- Mention scale or evidence when you have it, such as an incident count, an issue, or a metric.

**Reviewer guide** (large or risky PRs; directly under the summary)
- Give the reading order: "Start with `pagination.go` (the cursor contract), then the handler, then tests."
- Say where scrutiny is needed and why: "The tie-breaker in the ORDER BY decides correctness under duplicate timestamps."
- Say what is skimmable: generated mocks, lockfile, mechanical renames (and in which commit).
- Say whether the commits are curated for commit-by-commit review.

**Key changes**
- Group the bullets by behavior: "Retry policy", "Persistence", "Observability", not "`retry.go`", "`store.go`".
- Lead each bullet with the effect: "Deliveries that receive a 5xx are retried up to 5 times with jittered backoff."
- Name what was removed or renamed explicitly. Deletions are easy to miss in review.
- For a refactor, state "No behavior change" and what backs that claim: unchanged tests passing, a characterization test, identical output on a sample.

**How it was tested**
- Use exact commands, copied from what was run: `npm test -- src/checkout`, `pytest -k invoice`, `go test ./internal/...`, `mvn -pl billing test`.
- Report results as observed: pass counts, timing, before and after numbers.
- For manual testing, give the environment (local, staging, browser and device), the steps, and the outcome.
- Name the gaps. "Not tested: concurrent writers on a real database; covered only by a unit test with a fake clock" tells reviewers where to look.
- Leave out anything you only intend to do.

**Risk & rollout**
- Give one line of risk with a reason on every non-trivial PR, even when the risk is low, for example: "Low: internal refactor, existing tests unchanged".
- For feature flags, give the name, the default in each environment, and the plan and issue for removing it.
- For migrations, state the deploy order, whether the migration locks or rewrites large tables, whether it is reversible, and whether there is a backfill.
- For compatibility, say what happens to in-flight requests, queued messages, cached data and older clients during a rolling deploy.
- For monitoring, name the specific signal and threshold, not "monitor errors".

**Screenshots / recordings**
- Show before and after side by side, at the same viewport and with the same data.
- Cover the states the change touches: empty, loading, error, overflowing or long text, small screen, dark theme, keyboard focus.
- Use a short recording (GIF or video) for interactions, animations and multi-step flows.
- Crop or redact personal data in screenshots.

**Breaking changes**
- Write one entry per break, in the form "X now does Y; callers that relied on Z must ...".
- Give the migration path, any deprecation window, and the version or date of removal.
- Use `references/risk-signals.md` to decide whether something counts as a break.

**Follow-ups / out of scope**
- List known limitations, deliberately deferred work with issue links, and cleanup such as removing a flag or deleting a deprecated path.
- Don't list vague intentions ("could be optimized later") without an issue.

**Links**
- `Closes #123` only when the issue is fully resolved by merging this PR. A closing keyword on partial work still closes the issue when the PR merges.
- `Refs #123` or `Part of #123` for partial work.
- `Depends on #640` or "Stacked on #640" when another PR must merge first.
- Design docs, ADRs, incident reports, and related PRs in other repositories.

GitHub's closing-keyword rules:
- The keywords are `close`, `closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`, `resolves` and `resolved`.
- Write one keyword per issue: `Closes #12, closes #15`. For another repository: `Fixes owner/repo#100`.
- Keywords take effect only when the PR targets the repository's default branch. A PR into a feature branch (a stacked PR) closes nothing, so put the `Closes` line on the PR that will merge into the default branch, or say which PR will close the issue.
- GitLab's keywords and rules differ; see `gitlab.md`.

## 3. Risk levels

| Level | Typical changes |
|---|---|
| Low | Docs, tests, copy, internal refactor with good coverage, isolated change that is trivially revertible, no data or contract change |
| Medium | User-visible behavior change; a new code path behind a flag; minor or patch dependency upgrades; an additive public API parameter or field; an additive column, constraint or index (built without long locks, with a pre-check for existing violations); a performance change on a hot path |
| High | Data migration or backfill; destructive schema change; changes to auth, permissions, crypto, or how money is calculated or moved; a breaking public API or event contract change; infrastructure or config affecting all traffic; anything irreversible or with external side effects (emails, charges, third-party writes) |

State the level and the single biggest reason. Say what would raise or lower it, if you know.

## 4. Rollback: when "just revert" is true

"Revert the PR" is a complete rollback plan only if all of these hold:

- There is no migration, or the old code runs correctly against the new schema.
- The new code writes no data in a shape the old code can't read: new enum values, new serialization formats, new required fields.
- There are no external side effects to undo: messages already sent, payments captured, third-party state changed.
- No other service or client has started depending on the new behavior.

If any of these fails, describe the real path, such as rolling forward with a fix, turning off the flag, running the down-migration (and what it loses), or a manual cleanup step.

## 5. Variants

**Trivial** (typo, docs, one-line config):

```markdown
Fix the broken link to the install guide in the README.

Testing: checked the rendered README; the link resolves.
```

**Stacked PR** (base is another feature branch). Put this before the summary:

```markdown
> Stacked on #640 (`feature/token-store`). Review that first; this diff contains only the refresh endpoint.
> Closing keywords in this PR fire only if it merges into the default branch. GitHub retargets it there
> automatically when #640 merges and its branch is deleted. If the stack merges into `feature/token-store`
> instead, the `Closes` line belongs on the PR that targets the default branch.
```

**Large PR** reviewer guide (it sits directly under the Summary, as in the skeleton):

```markdown
## Reviewer guide
1. `internal/orders/cursor.go`: the cursor encoding and its ordering guarantee (needs the most scrutiny).
2. `internal/orders/handler.go`: request parsing and the flag check.
3. Skim: `internal/mocks/` is generated; `go.sum` changed only from the new dependency.
Commits are curated: review them one at a time.
```
