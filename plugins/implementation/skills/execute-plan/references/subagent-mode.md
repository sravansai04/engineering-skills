# Subagent Mode: Coordinator Protocol

Read this before your first dispatch. The prompt templates are in
[subagent-task-prompt.md](subagent-task-prompt.md).

## Contents

1. Inline or subagent?
2. The independence test
3. Sequential dispatch (one working tree)
4. Parallel dispatch (one worktree per implementer)
5. Handling implementer reports
6. Review rubric
7. Revision loop
8. Optional reviewer subagent
9. Keeping the coordinator's context lean

---

## 1. Inline or subagent?

| Signal | Lean toward |
|---|---|
| Each task builds on the internals of the one before | Inline |
| Many (roughly 8+) tasks, mostly independent leaves | Subagent |
| Tasks need judgment calls the plan doesn't settle | Inline |
| Long plan, and your context is already heavy | Subagent |
| Tasks are tiny (a few lines each) | Inline: writing the prompt costs more than the work |
| You want an implementation free of your own assumptions | Subagent |
| No subagent tool in this harness | Inline |

You can mix the two. Implement the tightly coupled core inline, then hand the leaf tasks to
subagents.

**Pick a fresh agent type.** The point of an implementer is that it starts from the prompt
alone, so ask for a general-purpose or custom agent type. Avoid any mode that copies your
conversation into the subagent: Claude Code's `fork` type does exactly that, and with it come
your assumptions and the plan-review debate. That defeats the cold-reader prompt design.

---

## 2. The independence test

Two tasks may run **at the same time** only if all four of these are true.

**1. Disjoint write sets.** List the files each task will create or modify. If you can't
predict a task's write set from the plan and a quick look at the code, treat it as **not**
independent.

**2. No shared aggregate or generated files.** These are the usual hidden collisions:

| Ecosystem | Files that quietly couple "independent" tasks |
|---|---|
| JS / TS | `package.json`, `package-lock.json` / `pnpm-lock.yaml` / `yarn.lock`, barrel `index.ts` re-exports, `__snapshots__/`, generated API clients, i18n catalogs |
| Python | `pyproject.toml`, `poetry.lock` / `uv.lock` / `requirements*.txt`, package `__init__.py` exports, migration chains (Alembic and Django migrations name their parent, so two parallel migrations create two heads) |
| Go | `go.mod`, `go.sum`, generated code (`*_gen.go`, protobuf output), DI provider sets |
| Rust | `Cargo.toml`, `Cargo.lock`, `mod.rs` / `lib.rs` module declarations |
| JVM / .NET | `build.gradle(.kts)` / `pom.xml` / `*.csproj`, DI registration modules, central config classes |
| Anywhere | Route tables, DI containers, feature-flag registries, OpenAPI/GraphQL schema files, migration sequence numbers, schema dumps, CHANGELOG, docs indexes |

**3. No ordering dependency.** Neither task calls, imports or reads anything the other
creates, and neither's tests rely on the other's behaviour.

**4. No shared runtime resources during checks.** Two test runs against the same local
database, port, fixture directory or emulator can make each other flaky. Give each worktree
its own resource (separate DB name, random port), or run their checks one after another.

If the only overlap is a shared aggregate file, you have two options. Run those tasks one
after another, or tell both implementers to leave that file alone and make the shared edit
yourself after merging (for example, registering both new routes).

---

## 3. Sequential dispatch (one working tree)

This is the default. One implementer at a time works in your working tree.

1. Start from a clean tree: `git status --porcelain` prints nothing.
2. Tell the implementer **not to commit**. You decide what enters history, and a rejection
   leaves no commit to unwind.
3. **Wait for it to return.** Subagents may run in the background. By default, Claude Code's
   interactive sessions run every subagent in the background, and Claude cannot ask for the
   foreground.
   Until the implementer has returned, leave the working tree alone: no edits (the plan file
   and ledger included), no test runs, no next dispatch. Drafting the next prompt in the
   meantime is fine. Two writers in one tree corrupt each other's work and your review.
4. When it returns, find **everything** that changed:

   ```bash
   git status --porcelain     # includes untracked files, which plain `git diff` does not show
   git diff                   # tracked changes
   git add -N path/new_file   # optional: mark new files intent-to-add so `git diff` shows them too
   ```

5. Handle the report (section 5), review it (section 6), and re-run the acceptance checks
   yourself.
6. Accept by staging explicit paths (plus the plan file's ledger update) and committing with
   the `Plan-Task:` trailer.
7. To reject, prefer a revision (section 7) to discarding the work. If you must set the
   changes aside, do it non-destructively, only for the paths the implementer touched, and
   confirm something was actually saved:

   ```bash
   before=$(git rev-parse -q --verify refs/stash)
   git stash push --include-untracked -m "T5 attempt 1" -- src/cart/ test/cart/
   after=$(git rev-parse -q --verify refs/stash)
   [ "$before" != "$after" ] && echo "saved as stash@{0}" || echo "NOTHING was stashed"
   ```

   A `stash push` whose paths match no changes prints "No local changes to save" and exits
   0. To get an attempt back later, find it by message in `git stash list` and apply it by
   explicit ref (`git stash apply stash@{2}`). Never run a bare `git stash pop`: it applies
   and **drops** whatever entry is on top, which may be a different attempt.

---

## 4. Parallel dispatch (one worktree per implementer)

1. **Create one branch and worktree per task yourself, based on your current HEAD**, so each
   implementer sees the tasks you have already accepted. Put the worktrees somewhere the
   implementers are allowed to write:

   ```bash
   root=$(git rev-parse --show-toplevel)
   git check-ignore -q "$root/.worktrees/probe" ||
     echo "/.worktrees/" >> "$(git rev-parse --git-path info/exclude)"   # local ignore, no commit
   git worktree add -b plan/T5 "$root/.worktrees/T5" HEAD
   git worktree add -b plan/T6 "$root/.worktrees/T6" HEAD
   ```

   Why inside the repository: harnesses often restrict or prompt for edits outside the
   session's working directory. Claude Code, for one, asks permission for paths outside the
   working directory and its added directories. A background implementer then stalls on the
   prompt, and a non-interactive run fails. A sibling folder (`../shop-T5`) works too, if you
   grant that directory before dispatching. Use `workflow:git-worktrees` for naming, setup
   and cleanup conventions.

2. **Base-branch trap.** A harness's built-in worktree isolation may branch from the
   repository's default branch rather than your current HEAD. Claude Code's default
   (`"fresh"`) works this way, so a task that builds on commits you accepted earlier in this
   run would silently lack them. Either create the worktrees yourself as above, or set this
   in Claude Code settings so harness-created worktrees branch from your current HEAD:

   ```json
   { "worktree": { "baseRef": "head" } }
   ```

   Either way, confirm before dispatching: `git -C "$root/.worktrees/T5" log --oneline -3`
   must show your latest accepted commit.
3. Put the worktree's **absolute path** in the prompt. Tell the implementer to work only
   there and to commit on its branch with the trailer. Dispatch fresh, non-fork agents
   (section 1).
4. **Expect per-worktree setup.** A new worktree holds tracked files only:
   - Installed dependencies (`node_modules`, virtualenvs) are absent; allow time for an
     install.
   - Gitignored files such as `.env` or local config are absent too. Copy just the ones the
     acceptance checks need. For worktrees Claude Code itself creates, list them in a
     `.worktreeinclude` file at the repository root and they are copied automatically. That
     file is not read for worktrees you make with `git worktree add`.
   - Without these files, checks fail and the implementer comes back stopped for
     `environment`, or improvises a config of its own. Check for that in Pass 1.
5. Wait until each implementer has returned before reviewing its branch:

   ```bash
   git log --oneline HEAD..plan/T5       # commits the implementer made
   git diff --stat HEAD...plan/T5        # what changed since the branch forked
   git diff HEAD...plan/T5               # the full diff to review
   ```

6. Integrate **one branch at a time**, and run the checks after each merge. Use
   `git merge --no-ff plan/T5`, or `git cherry-pick` if the project wants linear history.
   A conflict means your independence prediction was wrong. Resolve it yourself and log it as
   a note.
7. After the last merge, run the batch's verification on the combined tree.
8. **Clean up only what you created during this run, using the safe forms:**

   ```bash
   git worktree remove "$root/.worktrees/T5"   # refuses if dirty or locked: stop and report
   git branch -d plan/T5                       # succeeds after a merge
   ```

   After cherry-pick integration, `-d` refuses, because cherry-picked commits get new ids.
   Prove every commit landed first: `git cherry HEAD plan/T5` must print only lines starting
   with `-`. Then `git branch -D plan/T5` loses nothing. A `+` line means a commit is missing
   from HEAD, so stop. Never add `--force` to `worktree remove`, and never delete a branch or
   worktree that existed before this run, without the user's authorization. Claude Code
   removes the worktrees it created for subagents on its own when they hold no changes. It
   keeps them locked while the agent runs, so remove yours only after the agent returns.

---

## 5. Handling implementer reports

The report format in [subagent-task-prompt.md](subagent-task-prompt.md) has two outcomes.
`done` means the implementer claims the task is finished. `stopped` means it halted, and it
names exactly one `STOP_REASON`. Key your response to that reason:

| Report | Your response |
|---|---|
| `done`, `ASSUMPTIONS: none` | Review it anyway (section 6). The claim is a hypothesis |
| `done`, with assumptions listed | Settle every assumption **before** Pass 1; they often point straight at the defect. If the plan or spec answers one, check the code matches that answer. If the user owns it, it is a Decision needed, and the task is not accepted yet |
| `stopped: missing-context` | Your prompt lacked something the plan or repo answers. Supply it and continue the same implementer (section 7), then add it to the prompt for the remaining tasks |
| `stopped: needs-decision` | If the plan or spec answers it, answer, log a decision, and continue the implementer. If the user owns it, report it as Decision needed |
| `stopped: scope` | The task can't be done within its allowed files or constraints. If the allowed list was simply incomplete (a mechanical miss), widen it, log a note, and continue. Otherwise it is a material deviation: report it |
| `stopped: environment` | A missing install, service, credential or gitignored file. Fix the environment, then continue. Re-sending the unchanged prompt into the same broken environment wastes a round |
| `stopped: baseline-red` | Compare with your baseline. If the failures are pre-existing and unrelated, tell the implementer which ones to ignore. If they are new, something changed under it: investigate before continuing |
| `stopped: attempt-budget` | Read what was tried. Take the task inline with `implementation:debug-root-cause`, or treat it as a deviation if the plan's approach looks wrong. Don't re-dispatch it unchanged |

Treat the work as **not complete** in any of these cases:

- The report has no `OUTCOME`.
- `REQUIREMENTS TRACE` is missing, or cites lines that don't contain the change.
- `FILES TOUCHED` disagrees with `git status`.
- The report contradicts the diff (it says tests were added, but the diff has none).

---

## 6. Review rubric

Always run Pass 1 before Pass 2. Quality feedback on code that misses the task wastes a
revision round, and polishing can hide a missing requirement.

### Pass 1: spec compliance (any failure means revise)

- [ ] **Assumptions settled** (section 5) before anything else.
- [ ] **Requirement trace.** Check the implementer's `REQUIREMENTS TRACE` against the task
      text. Did it list every requirement? Open each cited `file:line` and confirm the code
      there does what the row claims. Then re-read the task text for requirements the trace
      left out. The trace saves you re-deriving the list; it does not replace checking it.
- [ ] **No extras.** No unrequested features, refactors, renames, or formatting churn in
      lines the task didn't need to touch.
- [ ] **Allowed files only.** Compare `git diff --name-status` (or `--name-only`) and the
      untracked files with the prompt's allowed list and the report's `FILES TOUCHED`.
- [ ] **Exact contracts.** Names, signatures, routes, payloads and schemas match the plan
      exactly, because later tasks depend on them.
- [ ] **Checks pass when you run them**, with the counts you expect (not zero tests, not
      skipped).
- [ ] **Tests can fail.** For behaviour-critical tasks, prove the new test depends on the
      change with a targeted mutation, even if the report includes a `MUTATION CHECK`.
      Break the one line that implements the required behaviour: invert the condition,
      delete the cap, or return the input unchanged. Run the new test and confirm it fails
      **on an assertion**, not on an import, compile or type error. An import failure only
      proves the test imports the symbol; `expect(result).toBeDefined()` would survive it.
      Then restore the file and prove the restore:

      ```bash
      f=src/cart/pricing/index.ts
      keep="${TMPDIR:-/tmp}/T5-reviewed"
      cp "$f" "$keep"                 # the version you reviewed
      # edit $f: delete the cap line
      npx vitest run src/cart         # expect: FAIL on the cap assertion
      cp "$keep" "$f" && cmp "$f" "$keep" && echo restored
      ```

      Don't use `git stash` for this. A stash push whose path matches nothing (for example,
      because the logic lives in a new, untracked file) saves nothing. The pop that follows
      then applies and drops an older stash, such as a rejected attempt.

      In parallel mode, mutate inside the implementer's worktree. Its work is committed, so
      `git -C <wt> restore -- <file>` puts back the reviewed version, and
      `git -C <wt> status --porcelain` must print nothing afterwards.

### Pass 2: code quality (sort findings into must-fix and follow-up)

- Fits the codebase's patterns for errors, logging, naming, layering and configuration.
- Doesn't duplicate an existing helper. Search for similar functions before accepting a new
  one.
- Errors are handled the way the codebase handles them. Nothing is swallowed, and inputs are
  validated at the boundary.
- No hard-coded secrets, environment-specific values or debug leftovers.
- Tests assert behaviour, not implementation details. They don't use sleeps or real clocks,
  and they don't depend on order.
- No obvious performance trap, such as per-item queries inside a loop over unbounded data.
- Comments explain *why*, not *what*.

**Must-fix** covers correctness, security, data safety and clear convention violations.
**Follow-up** covers taste and minor improvements. Log those; don't spend a revision round on
them.

### Red flags: reject unless the task explicitly calls for them

- Existing tests or assertions modified or deleted, unless the change is listed under
  "Existing tests expected to change" in the prompt and matches the stated new expectation.
  A loosened assertion is never acceptable.
- Snapshot files regenerated wholesale.
- A new dependency, or a changed lockfile.
- Broad exception catches, disabled lint rules, or type-check suppressions.
- Focus or skip markers left in tests (`.only`, `.skip`, `@pytest.mark.skip`, `t.Skip`).
- A TODO standing in for required behaviour.
- CI, build or tooling config changed, or a local config file (`.env`) the implementer
  invented to get its checks running.

---

## 7. Revision loop

Write findings an implementer can act on without guessing:

```text
Revision request for T5 (round 1 of 2)
1. src/cart/pricing/index.ts:42 - percentage is applied before the per-item cap;
   the task requires the cap first. Check: `npx vitest run src/cart` must include a test
   "caps item discount before order percentage" that passes.
2. test/cart/pricing.test.ts - the new test mocks applyDiscount itself, so it tests the
   mock. Exercise the real function.
Leave everything else as it is.
```

- **Prefer continuing the same implementer** when the harness can resume a finished
  subagent. It keeps its full history, so it doesn't relearn the code. In Claude Code, send
  the revision with `SendMessage` to the agent's id or name. (The built-in one-shot agent
  types cannot be resumed, which is another reason to dispatch a general-purpose or custom
  type.)
- Otherwise dispatch a fresh implementer with the revision template, the findings, and the
  original prompt appended. The current changes are already in the tree or branch.
- Cap it at **two rounds**. After that, finish the task yourself or report it. Repeated
  misses usually mean the original prompt was ambiguous, so fix the template for the
  remaining tasks.

---

## 8. Optional reviewer subagent

For a large diff, or when you want a second opinion, dispatch a separate reviewer with:

- the task text and acceptance criteria
- the branch or diff command
- the Pass 1 and Pass 2 rubric from this file

Ask for a verdict with `file:line` locations (template in
[subagent-task-prompt.md](subagent-task-prompt.md)). Treat its verdict as input. You still
re-run the checks and make the decision. Never let an implementer's review of its own work
be the only review.

---

## 9. Keeping the coordinator's context lean

- Ask implementers for short, structured reports. No full logs; quote only the lines that
  matter.
- Keep the one-row-per-task ledger (id, status, note) where SKILL.md step 4 puts it: in the
  plan's Execution notes, or in each progress report. Mirror it to a task-tracking tool if
  the session has one.
- Don't paste whole diffs into progress reports. Give commit ids and a summary, and quote a
  hunk only when it needs the user's attention.
