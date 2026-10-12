---
name: plan-feature
description: "Writes a reviewable implementation plan before any code: acceptance criteria, prior art, change surface, risks and scale, rollout and rollback, and small verifiable slices. Use for \"plan this feature\", \"break this ticket into PRs\", \"write a design doc\", \"write an RFC\", or \"technical spec\". Not for building it (build-feature), running a written plan (execute-plan), vague ideas (brainstorm-spec), one migration (db-migration-safety), one API's shape (api-design), or an ADR (adr-writer)."
---

# Plan a Feature Before Building It

Turn a feature request into a written plan that a reviewer can approve and an implementer (human or agent) can execute one small, safe step at a time. The plan exists to move the expensive mistakes (wrong requirement, reinvented utility, missed consumer, irreversible migration, unshippable mega-PR) to the cheapest moment to fix them: before any code exists.

Request to plan: the skill's arguments (in Claude Code, typed arguments appear after ARGUMENTS: at the end of this skill).

If none were given (as when this skill loads on its own), take the request from the conversation. Ask for a one-sentence description, plus the ticket or spec if one exists, only when neither contains a request.

## Before you start: size the change and pick the plan depth

Planning effort should track risk, not word count. Classify first, using what the request says plus a quick look at the code:

| Size | Typical signals | What to produce |
|---|---|---|
| Trivial | One obvious edit, no contract or data change, easy to undo | No plan. Say so and hand it back: the change needs no planning. |
| Small to medium | A few files in one component, no schema change, no public contract change, reversible | **Lite plan**: only the template sections tagged `[lite]`, with 1 to 3 slices. |
| Large | Several components or teams, a schema or data migration, a public API/event/file-format change, a new dependency or service, security- or money-sensitive, unclear requirements, or any step that cannot be undone | **Full plan** using every section of the template. |

When in doubt between two sizes, pick the larger one but keep each section short. A plan for a medium change that runs to ten pages is its own failure mode: nobody reads it. The same goes for scope: plan what the request needs, and put tempting extras in the non-goals instead of the slices.

## Workflow

Work through the steps in order. Steps 2 to 7 often loop: exploring the code reveals a new question, and a spike can overturn a design choice. Update the plan rather than pretending the first pass was right.

Companion skills are named as `plugin:skill` (for example `data-api:db-migration-safety`, which an agent that lists skills by bare name knows as `db-migration-safety`) and listed under Related skills. When one isn't installed, the matching section of `references/risk-checklist.md` usually has the short version.

### 1. Clarify the goal and write acceptance criteria

1. Restate the problem in two or three sentences: who needs what, and why now. If the request only describes a solution ("add a column"), work back to the problem it solves; the best plan sometimes changes the solution. If the input is a spec from `implementation:brainstorm-spec`, keep its R, SC and C ids, and give each acceptance criterion the R ids it delivers.
2. Write **acceptance criteria** as observable, testable statements, numbered `AC-1`, `AC-2`, and so on. Include negative criteria (what must *not* happen, such as "a user in another workspace cannot see the item"). Given/When/Then phrasing works well but is optional.
3. List **non-goals** explicitly. They stop scope creep during review and tell the implementer what not to build.
4. Separate questions from assumptions. A question is worth asking only when both are true:
   - the answer changes the design, the data model, or the slice order, and
   - the answer is not discoverable from the code, docs, ticket, or commit history.

   Everything else becomes a written assumption the reviewer can veto. Asking the user things the repository already answers wastes their time and signals the code was not read.
5. Batch the genuine questions into one message. For each, give a recommended default and what changes if the answer differs, so the user can reply "defaults are fine". If no one is available to answer (an unattended run), proceed on the defaults and mark them as unconfirmed assumptions in the plan.

### 2. Explore the codebase before designing anything

Search before inventing. Most features rhyme with something already in the repo, and a second implementation of an existing concept (a retry helper, a pagination scheme, a permission check) drifts from the first and doubles the bug surface.

1. **Learn the project's own commands and conventions.** Read, where present: `README*`, `CONTRIBUTING*`, `Makefile`/`justfile`/`Taskfile.yml`, `package.json` scripts, `pyproject.toml`, `go.mod`, `Cargo.toml`, `pom.xml`/`build.gradle*`, and CI config (`.github/workflows/`, `.gitlab-ci.yml`, and similar). Note how to build, test a single file, lint, and run migrations. Use these later in verification steps instead of guessing a stack's defaults.
2. **Find prior art.** Search for the domain nouns and verbs in the request, for similar features, and for the history behind them:
   ```bash
   git grep -n -i "invoice"                    # or: rg -n -i "invoice"
   rg -l -e 'class \w*Exporter' -e 'def export_'   # sibling implementations to copy
   git log --oneline -S "rate_limit"           # commits that added or removed a term
   git log --oneline --grep "soft delete"      # commits whose message mentions it
   git log --oneline --follow -- path/to/file  # how a key file evolved
   ```
3. **Look for existing decisions and plans**: an ADR directory (often `docs/adr/` or `doc/adr/`), a plans or RFC directory, and code-ownership files. A past decision that rejected your intended approach is something the plan must address, not rediscover.
4. **Record what to reuse.** Build a short table of existing helpers, base classes, middleware, components, test fixtures, and conventions (error handling, validation, logging, naming, test layout) the change should follow, each with its path. Cite `path:line` so the reviewer can check.
5. **Find every consumer of anything you might change.** Callers of a function, readers of a table, clients of an endpoint, subscribers to an event, parsers of a file format. Unseen consumers are the most common source of "it worked in the PR and broke in production".

In a large repository, run independent searches in parallel (for example with subagents, if your agent can run them, such as Claude Code's Agent tool or OpenCode's subagents) and collect their findings with file paths. Without subagents, run the same searches one after another yourself.

### 3. Map the change surface

Describe what changes, component by component. For each item, state whether it is new, modified, or removed.

- **Components and modules** touched, and who owns them.
- **Data model**: new or changed tables, columns, indexes, constraints, types, nullability, defaults, ownership, lifecycle, retention, and whether existing rows need a backfill.
- **Contracts**: HTTP/RPC endpoints, events and message schemas, CLI flags, config keys, file formats, public library APIs. For each, list its consumers (from step 2) and its compatibility strategy. Hand detailed contract design to `data-api:api-design` when the change introduces or reshapes an API.
- **Behavior paths**: UI, background jobs, scheduled tasks, caches, search indexes, notifications, analytics events.
- **Cross-cutting**: permissions, audit logging, observability (metrics, logs, traces, alerts), documentation, and translations if the product is localized.

Every file or symbol the plan names must either exist (you found it) or be explicitly marked *new*. Plans that reference plausible but non-existent helpers send implementers on a hunt.

### 4. Stress-test the design

Walk the design through each category below and write down only what applies, each with its decision or mitigation. `references/risk-checklist.md` holds the detailed prompts per category; read it for full plans, and skim for what fits rather than answering every line.

- **Edge cases**: boundaries, empty and huge inputs, duplicates, time zones, related records that are deleted or mid-transition.
- **Failure modes**: slow or failing dependencies, partial failure in multi-step writes, retries (which demand idempotency), crashes mid-job.
- **Concurrency**: two actors on one record, check-then-act races, double submits, duplicate or reordered messages. Name the mechanism that makes each safe, and check that it protects every step of a multi-step operation, not only the last one.
- **Security and privacy**: authentication and authorization on every new entry point, including object-level checks (can user A reach user B's record by changing an id?), plus data exposure, secrets, and retention and deletion of personal data. Flag anything that warrants a dedicated `review-suite:secure-code-review` pass.
- **Scale**: fill in the 10x/100x table from the template. Record today's value for each dimension that matters (measured if possible, otherwise marked as an assumption), find what breaks first, and decide "mitigate now" or "known limit, revisit at threshold X". The exercise prices the breaking point; it does not mandate building for 100x today. `data-api:query-review` goes deeper on individual queries.

Measuring production while planning must not become an incident. Use cheap aggregate queries or existing metrics, under a statement timeout, on a replica that serves no user traffic where one exists. Anything load-shaped belongs in a spike (step 7), not against a serving system.

### 5. Compare alternatives and choose

When the approach is not obvious, sketch at least two options in a few lines each (including "extend the existing X" when prior art exists) and say why the chosen one wins: fit with existing patterns, reversibility, risk, effort, and operational cost. If the decision is significant and hard to reverse (a new datastore, a new public contract, a cross-team convention), recommend recording it with `workflow:adr-writer` once approved.

### 6. Design the rollout and the way back

A change is not done when it merges; it is done when it is safely live and the scaffolding is removed. Plan for a system where old and new code run side by side, because during a rolling deploy, a canary, or a rollback, they do.

1. **Feature flags.** Decide whether the change needs one and which kind: a short-lived *release* flag to hide unfinished work, an *ops* flag (kill switch) for risky paths, an *experiment* flag for A/B tests, or a long-lived *permission* flag for entitlements. Write down the default state, who flips it, the rollout stages (internal, a small cohort, a percentage, everyone), and the slice that removes it. Flags without a removal plan become permanent branches in the code.
2. **Data and schema changes.** Use expand, migrate, contract (also called parallel change): add the new shape alongside the old, move readers and writers and backfill data, and only then remove the old shape once no running version uses it. Keep schema changes in their own slices, separate from behavior changes. Defer the mechanics (locking, online index builds, batched backfills, version-specific database behavior) to `data-api:db-migration-safety`.
3. **Deploy order.** Readers before writers: deploy the code that can *understand* a new value, shape, or event before any code *produces* it, so a rollback of the writer never leaves data the old reader cannot handle. Schema expansion goes before the code that uses it; contraction goes last.
4. **Backward compatibility.** Check slow-updating clients, queued messages and jobs, and stored or cached data in the old format. For consumers you do not deploy (mobile apps, partner integrations, customer scripts), "no running version uses it" cannot be observed directly. Announce the deprecation in advance (a changelog entry and, for HTTP APIs, the `Deprecation` (RFC 9745) and `Sunset` (RFC 8594) response headers), and gate the contract slice on telemetry showing use of the old shape at zero or below an agreed threshold, not on elapsed time.
5. **Rollback per step.** For each slice, write how to undo it: flip the flag off, revert the deploy, or forward-fix. Reverting code does not revert the world, so name the **one-way doors** explicitly: deleted or overwritten data, emails or webhooks already sent, payments made, a contract external clients have adopted. One-way doors earn extra safeguards: a dry-run mode, a backup or soft-delete window, a staged rollout, or explicit sign-off. Verify each rollback before relying on it: tests cover both flag states, and the flag-off or revert path is exercised once in staging before the production rollout.
6. **Signals.** Name the metrics, logs, or dashboards that show the rollout is healthy, and the threshold that triggers turning it off.

### 7. Identify risks and spike the unknowns first

List each risk with likelihood, impact, and mitigation. Then separate *risks* (known things that might go wrong) from *unknowns* (questions you cannot answer yet, such as "can the library stream this format?", "how slow is this query at production volume?", "what does the partner API do on duplicate requests?").

Schedule a **spike** for every unknown that could change the design. A spike is question-shaped, time-boxed, and disposable: write the question, the time box, and what answer would change the plan. Its deliverable is the answer plus evidence (a benchmark, a log, a prototype run), not production code. Put spikes first in the slice order, because an unknown discovered in slice 5 can invalidate slices 1 to 4.

Run load-shaped spikes on synthetic or anonymized data at production size, outside production. Never copy production personal data into a spike environment.

When a spike or a shipped slice disproves an assumption, update the plan and add a change-log entry, so reviewers who approved the earlier version can see what moved.

### 8. Slice the work into increments

Break the work into slices that are each:

- **Reviewable**: one purpose, small enough to review in a single sitting (as a rough guide, a few hundred changed lines excluding generated files).
- **Shippable**: merging it leaves the main branch green and deployable. Unfinished behavior stays dark behind a flag or is not yet wired up.
- **Verifiable**: it carries its own verification, meaning the tests to add and the exact command to run them, plus any manual or production check. "Add tests" as a final slice is a smell: verification belongs inside every slice.
- **Reversible**: it states its rollback.

Under each slice, list its commit-sized steps with stable ids (`T1`, `T2`, ... numbered across the whole plan), each ending in a check command. `implementation:execute-plan` uses these ids in its ledger and as `Plan-Task` commit trailers, so they must not be renumbered once the plan is approved.

Prefer **vertical** slices that deliver a thin end-to-end path early (a walking skeleton) over **horizontal** layers ("all the database work, then all the API, then all the UI"). Horizontal plans postpone integration feedback to the last slice, which is where the surprises live. Schema-expansion and shared-foundation slices are a reasonable exception when later slices genuinely depend on them.

A typical order: spikes, then expand (schema, interfaces), then behavior behind a flag, then enable progressively, then contract and cleanup (remove the flag, the old code path, the old columns). Mark slices that can proceed in parallel and the dependencies between the rest.

Write verification with the project's real commands discovered in step 2. Examples of the shape, not defaults to assume:

```bash
pytest tests/billing/test_invoice_export.py::test_large_account   # Python
go test ./internal/billing/... -run TestInvoiceExport              # Go
cargo test invoice_export                                          # Rust
./gradlew test --tests 'com.example.billing.InvoiceExportTest'     # JVM (Gradle)
npm test -- invoice-export                                         # Node: args go to the project's test script
```

Map every acceptance criterion to at least one slice's verification. An AC with no verifying slice is either unimplemented or unproven.

Implementation happens in another skill, one slice at a time: `implementation:execute-plan` runs an approved plan step by step (test-first with `implementation:tdd`, each slice checked with `implementation:verify-before-done`), and `workflow:pr-description` writes each slice's pull request.

### 9. Write the plan

Use the template in `references/plan-template.md`; read it before writing any plan. A lite plan fills only the sections tagged `[lite]`. For a calibrated sense of depth and tone, read `references/example-plan.md`, a filled-in plan for a medium-to-large change; read it once when unsure how much detail a section needs, not on every run.

Where to put it:
- If the repository already keeps plans somewhere (a `docs/plans/` directory, RFCs, a wiki link in the README), follow that convention and naming pattern.
- Otherwise present the plan in the conversation and offer to save it (for example `docs/plans/YYYY-MM-DD-short-slug.md`). Do not commit or open a pull request unless asked.

### 10. Self-review, present, and decide whether to continue

Before presenting, check the plan against this list and fix what fails:

- [ ] Every acceptance criterion maps to at least one slice's verification.
- [ ] Every changed contract lists its consumers and its compatibility strategy.
- [ ] Every slice leaves the main branch deployable and states its rollback.
- [ ] One-way doors are named, each with a safeguard.
- [ ] The riskiest unknown is spiked first, not discovered mid-build.
- [ ] Scale numbers are measured or explicitly marked as assumptions.
- [ ] Each flag introduced has a removal slice; each expand step has its contract step.
- [ ] Every referenced file, function, table, or command exists or is marked *new*.
- [ ] Questions are only the genuinely ambiguous ones; the rest are stated assumptions.
- [ ] The plan's length matches the change's risk.

Then present the plan, and let the request decide what happens next:

- **Asked to plan, design, or scope:** stop and wait for approval.
- **Asked to build:** this skill plans; it does not implement. If `implementation:build-feature` called it, return the plan to that skill. Otherwise save the plan as in step 9 and, once it is approved, offer `implementation:execute-plan` with the plan's path (or `implementation:build-feature`, which carries the plan through review and verification).
- **Unattended run** (no one available to approve): save the plan as in step 9, mark the unconfirmed assumptions, and stop. Hand the path back to whoever started the run; never begin implementing to fill the time.
- **Always:** name the slices that cross a one-way door or depend on a decision marked as needing sign-off, so whoever executes the plan stops before them.

## Special cases

### Called from another skill

When `implementation:build-feature` hands over its brief, codebase map and chosen design with its hand-off contract, those inputs are settled. Skip the questions in step 1 and the alternatives in step 5, spot-check the map instead of exploring from scratch (search only for what it lacks, above all every consumer of anything the plan changes), list the commit-sized steps under every slice, and return the plan with the report block. Do not stop for your own approval: the calling skill owns that checkpoint. Anything that blocks the plan goes under "Needs your decision" in the returned report, not into a separate question.

## Report format

End with a short message in this shape so the user can act on it quickly:

```
Plan: [title] ([lite | full]; saved to [path] or "inline above")
Approach: [one or two sentences on the chosen design and why]
Slices: [N] ([S] spikes first); first slice: [name]
Needs your decision:
  1. [question] (recommended: [default]; if not, [what changes])
Assumptions to confirm: [the two or three that matter most]
Biggest risk: [risk] (mitigation: [mitigation])
Next: [waiting for approval | returned to build-feature | approved: run implementation:execute-plan on [path]]
```

## Example: weak versus strong slicing

Request: "Let workspace admins register webhook endpoints and receive signed event deliveries, with retries."

Weak plan:
1. Add webhook tables and models. 2. Add the delivery worker. 3. Add the settings UI. 4. Add tests.

No slice is useful on its own, tests come last, nothing says what happens when a receiver is down for a day or what one busy workspace does to the shared queue, and there is no rollout or rollback.

Stronger plan:
0. Spike (2 hours): replay a synthetic burst at peak volume (events per second times endpoints per workspace) through the existing job queue on staging, with one receiver that always times out. Decides between the shared queue and a dedicated one with per-endpoint concurrency limits.
1. Schema only: endpoint and delivery-attempt tables (expand). Verified by running the migrations up and down in CI. Rollback: revert; the tables are empty.
2. Delivery worker behind a release flag (off), reusing the existing job framework and HTTP client. It signs each payload with the endpoint's secret, sends the event id so receivers can deduplicate, retries with capped exponential backoff and jitter for up to 24 hours before marking the endpoint failing, and refuses private and link-local addresses after DNS resolution (request forgery). Verified by tests against a fake receiver that fails and then succeeds, and against a hostname that resolves to a private address. Rollback: flag off; queued deliveries pause rather than disappear.
3. Endpoint management API: admin only, scoped to the caller's workspace, secret shown once. Contract tests plus a cross-workspace authorization test. Rollback: flag off.
4. Settings page and delivery log behind the same flag; component test and a manual delivery to a request-inspection endpoint on staging. Rollback: flag off.
5. Enable for internal workspaces, then 10%, then everyone, watching delivery success rate and queue lag. Rollback: flag off. Deliveries already sent are a one-way door, which is why slice 2 makes every delivery safe to repeat.
6. Remove the flag and dead code paths. Rollback: revert.

## Related skills

- `implementation:brainstorm-spec` first, when the problem itself is unsettled; its approved spec is this skill's input.
- `implementation:build-feature` when the user wants the feature built end to end; it calls this skill for its plan.
- `implementation:execute-plan` to carry out an approved plan task by task.
- `implementation:tdd` and `implementation:verify-before-done` inside each slice, once implementation starts.
- `data-api:db-migration-safety` for the mechanics of a schema or data migration, and `data-api:api-design` for a new or reshaped API contract.
- `review-suite:secure-code-review` when the change touches authentication, authorization or sensitive data.
- `workflow:adr-writer` for a significant, hard-to-reverse decision, and `workflow:pr-description` for each slice's pull request.

Skills are named here as `plugin:skill`; an agent that lists skills by bare name knows each one by the part after the colon (`review-suite:pr-review` is `pr-review`). If a skill named here isn't installed, give the short version inline and list the deeper pass as a follow-up.

## Reference files

- `references/plan-template.md`: the plan skeleton and section guidance (step 9).
- `references/risk-checklist.md`: detailed risk prompts by category (step 4).
- `references/example-plan.md`: a complete worked plan for calibration (step 9).
