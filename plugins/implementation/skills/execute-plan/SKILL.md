---
name: execute-plan
description: >-
  Carries out a written implementation plan task by task: reviews it against
  the code, keeps a durable ledger, commits each task only after its check
  passes, and stops on deviations rather than improvising. Use for "execute the
  plan", "implement docs/plans/search.md", "do tasks 3-6", "resume the plan",
  or "use subagents to implement this plan". Not for writing or critiquing a
  plan (plan-feature), criteria-only tickets (build-feature), or fuzzy ideas
  (brainstorm-spec).
allowed-tools: Bash(git status:*), Bash(git log:*), Bash(git diff:*), Bash(git show:*), Bash(git rev-parse:*), Bash(git ls-files:*), Bash(git cherry:*), Bash(git stash list:*), Bash(git worktree list:*), Bash(git check-ignore:*), Bash(gh issue view:*), Read, Grep, Glob
compatibility: Needs git. Subagent mode needs an agent that can run subagents (such as Claude Code's Agent tool or OpenCode's subagents); without them every task runs inline, one after another in one session, which is the default mode anyway.
---

# Execute Plan

Someone has already done the thinking and written it down. Your job is to turn that plan
into working, verified, committed code **faithfully**, and to make every disagreement
between the plan and reality visible. This skill exists to prevent two failures:

- **Drift**: the code quietly stops matching the plan, so the person who approved the plan
  is no longer approving what actually ships.
- **Optimistic completion**: tasks marked done because the code "should work", not because
  a check ran and passed.

Every step below catches problems at the cheapest point: before starting (plan review),
inside each task (verification), between batches (checkpoints), and at the end
(whole-change verification).

Plan to execute: the skill's arguments
(in Claude Code, typed arguments appear after ARGUMENTS: at the end of this skill).

If none were given, take the plan (a plan file, a spec's task list, an issue whose body
lists ordered implementation steps, or numbered steps pasted in chat) and the task range from
the conversation.

## Scope

| Use this skill | Use something else |
|---|---|
| A plan exists and the user wants it carried out | No plan yet: `implementation:plan-feature`, or `implementation:build-feature` for request-to-code |
| Resuming a partly executed plan | Requirements still fuzzy: `implementation:brainstorm-spec` |
| Delegating plan tasks to subagents | A single small change: just make it, then `implementation:verify-before-done` |
| | An ops runbook, deploy or rollout procedure run against live systems: this skill is built for code changes in a repository |

A checklist that says **what** must be true (acceptance criteria) goes to
`implementation:build-feature`. A checklist that says **how**, step by step, naming files or
modules, is a plan: use this skill.

## Workflow

### 1. Settle five things before the first edit

1. **Which plan, which tasks.** Get the path or source and the range (whole plan, or
   "tasks 3-6"). If several plans could match "the plan", ask which one.
2. **Execution mode.** Inline (you implement each task) is the default. Use subagent mode
   (step 8) when the user asks for it, or when the plan has many independent,
   well-specified tasks, and only if your agent can run subagents (such as Claude Code's
   Agent tool or OpenCode's subagents).
3. **Checkpoint cadence.** Do what the plan or user specifies ("pause after each phase",
   "check in after task 4"). If neither says, send a short report after every batch and
   keep going. Stop only when a stop condition fires.
4. **Where the work happens.** Never on the default branch, and never in a tree holding
   someone else's uncommitted changes. Create a feature branch, or use an isolated worktree
   (`workflow:git-worktrees`) if the main checkout must stay usable.
5. **Baseline.** Before the first edit, record `git rev-parse HEAD` and run the project's
   test, lint/typecheck and build commands once. Note what passed and what already failed.
   Without a baseline you cannot tell a regression you caused from one you inherited. You
   will waste time "fixing" old failures, or blame the plan for them. If the baseline is red
   in an area the plan touches, report it before starting.
   - **Slow suite:** if the full suite is too slow to run up front, baseline the scoped
     suites for every area the plan touches plus lint/typecheck/build, say so in the review
     message, and run the full suite at checkpoints (when affordable) and at the finish.
   - **Flaky tests:** re-run each baseline failure once. One that passes on the re-run is
     recorded as flaky, by test name, not as broken.
   - **Checks that cannot run here** (a missing service or credentials) are recorded as
     "not run", never as passing.

Take commands from the project itself (package scripts, Makefile/justfile/taskfile, CI
workflow, CONTRIBUTING) rather than guessing generic ones.

### 2. Rebuild state from durable evidence when resuming

Skip this step on a fresh start. When picking up a partly executed plan, rebuild state from
git and the plan file, not from memory or a previous session's tool state:

```bash
git log --format='%h %(trailers:key=Plan-Task,valueonly,separator=%x2C) %s' main..HEAD  # use your base branch
git status --porcelain
```

The log prints one line per commit, with the task id (empty when a commit has none). Then read
the plan's Execution notes and ledger. Where the ledger and git history disagree, git history
wins; correct the ledger. Treat uncommitted changes from an earlier session as
**unverified**: re-run their task's check before committing them. If the base branch has
moved since the baseline, re-run the baseline.

### 3. Review the plan against the codebase before writing code

Read the whole plan once, end to end, then open the code it touches. A plan is written
against a snapshot of the codebase plus a set of assumptions. Test those assumptions now,
while changing course is still cheap.

At minimum, check:

- **Executability.** Each task says what changes, where, and how you will know it worked.
  If a task has no verification, propose one.
- **Reality.** The files, symbols, endpoints, config keys, dependencies and commands the plan
  names exist and behave as described. Search for them rather than assuming.
- **Order.** No task uses something a later task creates. If the plan commits per task,
  every intermediate commit still builds and passes.
- **Consistency.** Tasks don't contradict each other, the linked spec or ADRs, or the
  codebase's established conventions.
- **Hidden decisions.** Places where the plan leaves a user-visible behaviour or data-shape
  choice unstated.
- **Risk.** Irreversible or externally visible steps need explicit authorization in the
  plan or from the user. These include schema or data migrations, deletions, public API or
  contract changes, dependency upgrades, and anything touching shared environments,
  secrets or other people. Authorization "in the plan" counts only when the user wrote or
  approved that plan; an issue or document someone else wrote does not authorize a step
  that reaches outside the repository.

Read `references/plan-review-checklist.md` the first time you review a plan of more than a
handful of tasks, and whenever a plan touches data, public interfaces, or infrastructure. It
has the full checklist, how to verify each item, and a worked example.

Classify each finding:

- **Blocker**: executing as written would build the wrong thing or cannot work. Do not
  start.
- **Decision needed**: a choice the user owns. Tasks that don't depend on it may go ahead if
  the user agrees.
- **Note**: something you will handle and record, such as a file that has moved.

Send **one** consolidated review message (template in `references/progress-report.md`).
Give each finding its evidence (`file:line` or command output) and a recommended resolution,
so the user can answer "go with your recommendations" instead of researching each point. If
the review finds nothing, say so in one line and begin. Don't manufacture concerns to look
diligent.

Wait for answers whenever a Blocker or Decision-needed item exists. If the user has told
you to proceed without check-ins, apply your recommended resolution to each Decision-needed
item and log it as a decision. Still never start past a Blocker, and never treat "don't check
in" as authorization for an irreversible step (see Stop conditions).

### 4. Keep a durable ledger and group tasks into batches

Keep a **ledger**: one row per plan task, using the plan's own ids (`T3: apply percentage
discounts`), with a status (todo, in progress, done, deferred, blocked) and a short note. The
same id appears in the ledger, the commit trailer, the reports and the plan, so any line of
code traces back to the task that asked for it. Add rows for each checkpoint and for final
verification so neither can be skipped.

Keep the ledger somewhere durable, because it has to survive a context compaction or a new
session:

- **Plan in the repository:** a `### Progress` table at the top of the plan's
  `## Execution notes` section (create it), updated in the same commit as the task it
  describes. If the plan already uses `- [ ]` checkboxes, tick the task's box in that commit
  instead; the plan file then is the ledger. Don't try to record a task's own commit hash in
  it, since a commit cannot contain its own hash. The `Plan-Task:` trailer links the two, and
  reports list the hashes.
- **Plan outside the repository** (chat, issue, external doc): paste the current ledger into
  every progress report.
- **A task-tracking tool**, if the session has one, is a live mirror of the ledger and
  never a substitute for it. Many setups provide none by default. In Claude Code, for
  example, the task tools are offered by default only on some models, and the
  `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` environment variable opts in on others.

Ledger rules:

- Exactly one task in progress at a time in inline mode.
- **Done means verified and committed**, not "code written".
- A deferred or blocked task stays visible with its reason. Never quietly drop one.

Group tasks into **batches**:

- Make a batch 2-4 consecutive tasks that together produce something checkable.
- Put a risky task (migration, public interface change, deletion, dependency upgrade) in
  a batch of its own, followed by a checkpoint.
- End a batch at every checkpoint the plan declares.
- Make batches smaller when the plan is thin on detail or the code is unfamiliar.

### 5. Execute each task: test, implement, verify, commit

For every task:

1. **Re-read the task text in the plan**, not your memory of it, then read the files it
   touches. Plans are dense, and detail lost from memory between tasks is the most common
   cause of drift.
2. **Write the test first** where the task changes behaviour. Watch it fail for the
   expected reason (`implementation:tdd`).
3. **Implement the smallest change that satisfies the task.** Where the codebase's existing
   pattern differs cosmetically from the plan's sketch, follow the codebase. Where it differs
   materially, handle it as a deviation (step 6). Out-of-scope improvements you notice go on
   a follow-ups list, not into this diff.
4. **Verify.** Run the task's check exactly as the plan states it, then a scoped regression
   check: tests, lint and typecheck for what you touched. **Read the output, not just the
   exit code.** "0 tests collected" and "3 skipped" both exit 0. Compare the result with the
   baseline.
5. **Update the ledger, then stage and review exactly what will be committed.** Only now
   that the check has passed, set the task's row to done and add any note or decision, so the
   commit that lands the task also carries its ledger row. Plain `git diff` hides untracked
   files, so a brand-new file would never be reviewed:

   ```bash
   git status --porcelain     # every modified AND untracked file
   git add src/cart/discount.ts test/cart/discount.test.ts docs/plans/coupons.md
   git diff --cached          # review what is staged
   git diff --cached --check  # whitespace errors and conflict markers
   ```

   Stage this task's paths explicitly, including the plan file when its ledger or Execution
   notes changed. A blanket add sweeps in unrelated files, local config or someone else's
   work. Every staged hunk should trace to this task. Leave unstaged anything you didn't
   create, and delete stray files you did create (debug output, scratch scripts).
6. **Commit** once per task unless the plan says otherwise, with the task id as a trailer so
   resuming is mechanical:
   `git commit -m "feat(cart): apply percentage discounts" --trailer "Plan-Task: T3"`.
   `--trailer` needs Git 2.32 or later. On older Git, make `Plan-Task: T3` the last
   paragraph of the message body (`-m "feat(cart): …" -m "Plan-Task: T3"`); git reads it as
   the same trailer. For message conventions, use `workflow:commit-message`.

**When verification fails**, find the cause before trying variations
(`implementation:debug-root-cause`). Stop and report after three distinct failed fix
attempts, or straight away if the fix lies outside this task's scope. Never skip, delete or
loosen a test or the plan's acceptance check to get green, and never mark a task complete
while its check is red. A red check you report is useful information. A green check you
manufactured is a defect you shipped.

An existing test that encodes behaviour **the task deliberately changes** may be updated to
the new expectation when the task text or the approved plan review covers it. Name the change
in the commit message and the report. If neither covers it, or the test guards a published
contract (a public API, a file format, another team's integration), it is a material
deviation: stop and ask.

Task-scoped verification examples (prefer the project's own scripts when they exist):

| Stack | Scoped tests | Static check |
|---|---|---|
| JS / TS | `npx vitest run src/cart` | `npx tsc --noEmit` |
| Python | `pytest -x tests/test_cart.py` | `ruff check src/cart` |
| Go | `go test ./internal/cart/...` | `go vet ./internal/cart/...` |
| Rust | `cargo test cart::` | `cargo clippy --all-targets` |
| JVM (Gradle) | `./gradlew test --tests 'com.acme.cart.*'` | the project's lint task |
| .NET | `dotnet test --filter "FullyQualifiedName~Cart"` | `dotnet format --verify-no-changes` |

### 6. Classify and record every deviation from the plan

The plan is the agreement the user reviewed. When the codebase disagrees with it, the worst
outcome is a quiet workaround: the code ships something nobody approved, and the plan becomes
fiction. Classify each deviation:

| Kind | Examples | Action |
|---|---|---|
| **Mechanical** | A file has moved; a helper was renamed; the plan's line numbers are stale; an equivalent import path; tests live in a different folder | Adapt, add a one-line note, continue |
| **Material** | A different interface, data shape, dependency or user-visible behaviour is needed; an existing test or published contract the task doesn't mention must change; a task turns out unnecessary, or a missing one is needed; scope grows; the order must change in a way that alters what an intermediate commit ships | Stop this task. Report options with a recommendation. Continue only with independent tasks the user approves |
| **Plan-breaking** | A premise is false: the API doesn't exist, the approach can't meet the requirement, or the check cannot pass by design | Stop the batch and report |

Quick test: **would the person who approved the plan be surprised by this diff?** If yes,
the deviation is material.

Record every decision, whether yours or the user's, as a numbered entry. Each entry gives the
task, what the plan said, what you found, what was decided and by whom (format in
`references/progress-report.md`). When the plan lives in the repository, append the entries
under `## Execution notes` and commit them with the task they concern. Otherwise, carry them
in the progress reports. Edit the plan's task text only to apply a decision the user approved
(or delegated by telling you to proceed without check-ins), and cite the decision id beside
the edit (`(per D3)`). Later tasks then run against the current version, and a reader can
see why the plan changed.

### 7. Report at every checkpoint

At the end of every batch, run the full suite if it is cheap, otherwise the union of the
batch's scoped checks. Then send a short progress report using the template in
`references/progress-report.md`, stating which of the two it shows. It covers the tasks done
with their commit ids, the verification evidence, any deviations or decisions, what comes
next, and anything that needs the user. The reader should know within ten seconds whether to
step in.

Then:

- **Continue** to the next batch if no stop condition fired and no checkpoint is due.
- **Stop and wait** if the plan or user asked for a check-in here, or if the next batch
  contains an irreversible step that hasn't been explicitly authorized.

After feedback, apply it before starting the next batch. Feedback on batch 2 often changes
how batch 3 should be done. Record decisions made at a checkpoint in their own commit
(`docs(plan): record D3`) before the next batch starts. Never carry uncommitted plan edits
across a checkpoint.

### 8. Delegate to subagents when it pays (optional)

You act as **coordinator**: fresh implementer subagents write the code, and you keep
everything that decides what ships (plan review, prompts, review, acceptance, commits, the
ledger, reports). **Never delegate the judgment of whether a task is done.** Use it for many
independent, well-specified tasks, or a long plan that would crowd your context. Stay inline
for coupled, exploratory or tiny tasks.

This needs an agent that can run subagents, such as Claude Code's Agent tool or OpenCode's
subagents. Without one, run the same tasks inline, one after another in this session, and
say in every report that they ran sequentially rather than delegated.

Read `references/subagent-mode.md` before the first dispatch. It has the mechanics, git
commands, report handling and review rubric. The rules you cannot skip:

- **Self-contained prompts**, built from `references/subagent-task-prompt.md`. The
  implementer has seen none of this conversation.
- **Fresh, non-fork implementers.** Use a general-purpose or custom agent type, never a mode
  that copies your conversation into the subagent (such as Claude Code's `fork` type).
- **One at a time by default, and wait for the return.** Subagents may run in the
  background. Until the current implementer returns, don't edit, test, or dispatch anything
  into the same working tree.
- **Parallel only** when write sets are disjoint (no shared lockfile, registry, migration
  sequence, snapshot or barrel file), and each implementer has its own worktree based on
  your current HEAD.
- **Review before accepting.** Read the real diff, re-run the checks, and settle the
  implementer's stated assumptions. Then run Pass 1, spec compliance: every requirement is
  traced to code, nothing extra, allowed files only, exact contracts, and tests that fail
  without the change. Run Pass 2, code quality, only after Pass 1 is clean. Allow at most two
  revision rounds, then finish the task yourself or escalate.
- **Verify the combined tree** after integrating parallel work.

### 9. Finish with a whole-change review and final verification

1. Every task is completed, or deferred with a reason the user has acknowledged.
2. Review the whole change as one unit: `git diff --stat main...HEAD`, then read the diff.
   Look for what per-task review misses: naming that drifted between tasks, two helpers that
   do the same job, TODOs left for "a later task" that never came, and acceptance criteria
   that span several tasks.
3. Run `implementation:verify-before-done`: the full test suite, lint/typecheck, the build,
   and the plan's top-level acceptance criteria, compared against the baseline.
4. Send the final report (Report format, below).
5. Don't push, open a PR, merge or deploy unless asked. When the user is ready, offer
   `workflow:pr-description`.

## Stop conditions

Stop, report, and wait when any of these hold. Being told to proceed without check-ins
removes the checkpoint pauses, not this list.

- Plan review found a Blocker, or a decision the user owns is unresolved.
- A material or plan-breaking deviation came up.
- A task's check still fails after three distinct attempts, or the fix lies outside the task.
- The next step is irreversible or reaches beyond the repository and the plan or user hasn't
  explicitly authorized it. Examples: data changes in a shared environment, deleting
  branches or data that existed before this run, force-pushing, publishing, sending
  messages, spending money. Removing the scratch worktrees and branches you created during
  this run follows the safe-cleanup rules in `references/subagent-mode.md` section 4.
- Files change that neither you nor an implementer you dispatched touched, or an implementer
  touched files outside its allowed list. Changes your own implementer made inside its
  allowed list are expected; review them under Pass 1.
- A checkpoint set by the plan or the user is reached.

A stop message states what stopped you, the evidence, the options, your recommendation, and
what is still safe to do in the meantime (template in `references/progress-report.md`).

## Report format

Every message during a run leads with evidence (commands with their counts, commit ids,
`file:line`), compares results with the baseline, and names anything that was not verified.
The plan review (step 3), batch progress report (step 7), decision entry (step 6) and stop
message have templates in `references/progress-report.md`. The run ends with this report:

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

## Common mistakes

- **Coding before reading the whole plan**, then finding at task 7 that task 2 rested on a
  false premise.
- **Treating the plan as a suggestion.** "Improving" the design mid-execution without
  surfacing it.
- **Treating the plan as infallible.** Following a step you can see is wrong because "the
  plan said so". Surface it instead.
- **Working from memory of a task** instead of re-reading it, especially deep into a long
  plan.
- **Marking a task complete because the code is written**, not because its check passed.
- **Trusting exit codes** without reading the output (zero tests collected, skipped
  suites).
- **One commit for many tasks** ("implement tasks 3-7"). You lose per-task bisect, revert
  and review.
- **Blanket staging**, which sweeps unrelated files, local config or another agent's work
  into the commit.
- **Skipping the baseline**, then "fixing" pre-existing failures nobody asked about, or
  blaming them on your change.
- **Weakening a test or acceptance check** to get green.
- **Keeping progress only in a session tool** that disappears with the session, or that the
  harness never provided.
- **Reading "don't check in with me" as permission** to apply a migration or run a backfill
  against a shared database, or anything else that reaches a shared system.
- **Subagent mode mistakes:**
  - a prompt that says "see the plan", when the subagent can't see your context
  - dispatching a fork that inherits your conversation, or touching the tree before a
    background implementer has returned
  - accepting a report without reading the diff and re-running the checks
  - parallel implementers sharing one working tree
  - reviewing code quality before confirming the task was actually satisfied
- **Reports that narrate effort instead of showing evidence** (commands run, results,
  commit ids).

## Related skills

- `implementation:plan-feature` to write the plan, or to critique one before anyone executes
  it; `implementation:build-feature` when there are acceptance criteria but no step-by-step
  plan; `implementation:brainstorm-spec` when the requirements are still fuzzy.
- `implementation:tdd` for the test-first loop inside each task, and
  `implementation:debug-root-cause` when a task's check fails for a reason you can't see.
- `workflow:git-worktrees` for isolated checkouts and parallel implementer worktrees.
- `data-api:db-migration-safety` before running a schema or data migration task.
- `workflow:commit-message` for per-task commit wording.
- `implementation:verify-before-done` for the final whole-change verification,
  `review-suite:pr-review` for an independent review of the finished branch, and
  `workflow:pr-description` once the user is ready to open a PR.

Skills are named here as `plugin:skill`; an agent that lists skills by bare name knows each
one by the part after the colon (`review-suite:pr-review` is `pr-review`). If a skill named
here isn't installed, give the short version inline and list the deeper pass as a follow-up.

## Reference files

- `references/plan-review-checklist.md`: the nine-area plan review checklist, how to verify
  each item mechanically, the Blocker / Decision / Note severity guide, and a worked review.
  Read it in step 3 for any plan beyond a handful of tasks, or one that touches data, public
  interfaces, or infrastructure.
- `references/progress-report.md`: templates for the plan review message, batch progress
  report, decision record entry and Execution notes ledger, stop message, and final report.
  Read it before sending the first message of a run.
- `references/subagent-mode.md`: the coordinator protocol (inline-or-subagent signals, the
  independence test, sequential and parallel dispatch, report handling, the two-pass review
  rubric, revisions, cleanup). Read it before the first dispatch in step 8.
- `references/subagent-task-prompt.md`: the cold-reader test plus implementer, revision and
  reviewer prompt templates with a filled example. Read it whenever you write a subagent
  prompt.
