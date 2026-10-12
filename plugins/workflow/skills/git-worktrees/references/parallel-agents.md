# Running parallel agents in worktrees

How to fan work out to several agents (or subagents, or terminals) on one
repository so they never touch each other's files, and how to bring the results
back together.

`${CLAUDE_SKILL_DIR}` in the commands below is not a shell variable: replace it
with this skill's directory, the folder that contains SKILL.md (in Claude Code,
the path SKILL.md shows for `scripts/`).

## Contents

1. When parallel worktrees pay off
2. Partition before you fan out
3. Coordinator setup
4. Agent brief template
5. Monitoring
6. Integration
7. Cleanup
8. Failure modes
9. Concurrency notes for git itself

## 1. When parallel worktrees pay off

Good fits:

- Independent tasks that touch disjoint files or modules.
- One long-running task (a migration, a big refactor, a slow test matrix) next
  to short ones.
- Competing implementations of the same task, of which you will keep one.

Poor fits:

- Tasks that edit the same files. Run them in sequence; worktrees only postpone
  the conflict to merge time.
- Tasks with an ordering dependency (B calls an API that A creates). Either do A
  first, or agree the interface, commit it to the base, and fan out from there.
- Tiny tasks where install + baseline takes longer than the work.
- More parallel test suites or dev servers than the machine can run. Each
  worktree costs CPU, memory, and disk while it is active.

## 2. Partition before you fan out

Write an ownership map before creating anything:

| Task | Branch | Owns (may edit) | Must not edit |
|---|---|---|---|
| Retry with backoff | `agent/api-retry` | `services/api/retry/**`, `tests/api/retry/**` | lockfile, migrations |
| Banner component | `agent/ui-banner` | `web/components/banner/**` | lockfile, routes file |
| Docs | `agent/docs-retry` | `docs/retry.md` | everything else |

Find the hot spots that several tasks would naturally touch and give each exactly
one owner (often the coordinator, after the agents finish):

- Dependency lockfiles and manifests.
- Database migrations with sequential numbers or timestamps (reserve numbers in
  advance).
- Central registries: route tables, dependency-injection config, feature-flag
  lists, barrel/index files, translation catalogs.
- Changelogs, snapshot files, generated code.

Agents that need a change in a file they do not own say so in their report
instead of editing it.

## 3. Coordinator setup

Pin one base commit so every agent starts from the same code and baselines are
comparable. It must contain everything the agents depend on: `origin/main` for
independent tickets, but your current `HEAD` when earlier tasks (an interface,
a shared helper) are committed locally and not pushed. An agent based on
`origin/main` would silently lack them.

```bash
git fetch origin
BASE=$(git rev-parse origin/main)        # or: BASE=$(git rev-parse HEAD) to include local commits
ROOT="$HOME/worktrees/myrepo"            # or the project's convention
# ${CLAUDE_SKILL_DIR} is not a shell variable: substitute the absolute path of this skill's folder

slot=1
for task in api-retry ui-banner docs-retry; do
  "${CLAUDE_SKILL_DIR}/scripts/wt-create.sh" --no-fetch "$ROOT/$task" "agent/$task" "$BASE"
  # setup: dependencies, env file with this slot's port / database / project name
  # baseline: run the agreed checks and record the result
  git worktree lock --reason "agent slot $slot: $task" "$ROOT/$task"
  slot=$((slot + 1))
done
```

Locking an active worktree protects it from a cleanup script or a `prune` run
elsewhere while the agent is working.

Keep a manifest (in your notes or outside the repository), one row per agent:

```
slot  task        path                                  branch            base     port  db                 baseline
1     api-retry   /home/dev/worktrees/myrepo/api-retry  agent/api-retry   3f9c2e1  3100  myapp_test_slot1   unit 412/0, lint PASS
2     ui-banner   /home/dev/worktrees/myrepo/ui-banner  agent/ui-banner   3f9c2e1  3200  myapp_test_slot2   unit 412/0, lint PASS
```

Every worktree starts from the same commit, so the baselines should match. If one
differs, that worktree's setup is wrong; fix it before handing it to an agent.

If your agent harness creates worktrees for subagents automatically, find out
where it puts them, which base it uses, and whether it removes them and their
branches afterwards. The partition, setup, baseline, integration, and cleanup
steps are still yours.

**Example: Claude Code.** Its behavior changes between releases, so confirm the
details in its worktrees documentation (https://code.claude.com/docs/en/worktrees)
before relying on them. At the time of writing:

- A custom subagent runs in its own worktree when its definition's frontmatter
  says `isolation: worktree`; `claude --worktree <name>` does the same for a
  whole session.
- Those worktrees live inside the repository under `.claude/worktrees/`, so the
  in-repo rule applies: check `git check-ignore -q .claude/worktrees/probe` and
  ignore the folder if needed (it also belongs in `.dockerignore`).
- They branch from the remote's default branch, not from your `HEAD`, unless the
  settings set `"worktree": {"baseRef": "head"}`. Agents that must build on
  unpushed commits need that setting, or worktrees you create yourself with the
  loop above; either way, check `git -C <wt> log --oneline -3` before dispatching.
- Ignored files such as `.env` are copied only when listed in a `.worktreeinclude`
  file at the repository root (gitignore syntax, ignored files only). List the
  specific files there rather than copying by hand. Dependencies are still not
  installed for you, and filter drivers defined only in the repository's own
  config are skipped, so with `git lfs install --local` large files arrive as
  pointer files (`git -C <wt> lfs pull`).
- A subagent's worktree is locked while the agent runs, so a locked entry in
  `wt-overview.sh` may be a running agent: do not unlock it. It is removed
  automatically when the agent made no changes; one with changes stays on disk
  until you clean it up. Run `wt-preflight.sh` on it like any other.

## 4. Agent brief template

Give every agent the same structure, filled in:

```
You are working alone in an isolated git worktree.

Worktree (absolute path): /home/dev/worktrees/myrepo/api-retry
Branch: agent/api-retry, created from 3f9c2e1 (origin/main)
You own: services/api/retry/**, tests/api/retry/**
Do not edit: package-lock.json, db/migrations/** (request changes in your report)
Resources: PORT=3100, DATABASE=myapp_test_slot1 (already set in this worktree's .env)
Baseline before your work: `npm test` 412 passed, 0 failed; `npm run lint` PASS
Done means: `npm test` and `npm run lint` pass, plus new tests for the retry logic

Rules:
- Use this worktree as the working directory for every command, or pass
  `git -C <worktree>`; use absolute paths for file edits.
- Commit only to agent/api-retry. Commit often; do not leave work uncommitted.
- Do not switch branches, push, rebase onto other branches, or run
  `git worktree`, `git stash`, `git gc`, or `git branch -D`.
- If a check fails outside the paths you own, stop and report it; do not fix
  other areas.

Report: commit list (short SHA + subject), files changed, check results compared
with the baseline, requested changes to files you do not own, open questions.
```

## 5. Monitoring

```bash
"${CLAUDE_SKILL_DIR}/scripts/wt-overview.sh"             # dirty counts, flags, age per worktree
git log --oneline "$BASE"..agent/api-retry               # what an agent has committed
git diff --stat "$BASE"...agent/api-retry                # size of its change
git -C "$MAIN" status --short                            # must stay empty

# Edits outside the ownership map
git diff --name-only "$BASE"...agent/api-retry |
  grep -Ev '^(services/api/retry|tests/api/retry)/' || echo "within bounds"
```

Unexpected changes in the main checkout almost always mean an agent used a
relative path or the wrong working directory.

## 6. Integration

Review each branch on its own first (`git diff "$BASE"...agent/<task>`;
`review-suite:pr-review` covers how). Then choose one strategy:

**Separate pull requests.** Rebase each branch onto the current base, push, and
open one PR per branch. Land them in dependency order, rebasing the remaining
ones after each merge.

**Local integration branch** in its own worktree, merging one branch at a time
and checking after each, so a failure points at the branch that caused it:

```bash
"${CLAUDE_SKILL_DIR}/scripts/wt-create.sh" --no-fetch ../myrepo-integrate integrate/retry-batch "$BASE"
cd ../myrepo-integrate
for b in agent/api-retry agent/ui-banner agent/docs-retry; do
  git merge --no-ff --no-edit "$b" || { echo "conflict merging $b"; break; }
  npm test && npm run lint     || { echo "checks fail after $b"; break; }
done
```

Merge the most foundational or smallest branch first. On a conflict, either
resolve it in the integration worktree (you know both intents from the reports)
or send it back: the owning agent rebases its branch onto the integration tip and
re-runs its checks. Apply the hot-file changes the agents requested last, in one
commit. Run the full verification at the end (`implementation:verify-before-done`).

**Competing implementations.** Compare the candidates by diff, test results, and
the criteria agreed up front; keep one. Discarding the others is a deliberate
decision: confirm it with the user before deleting branches with `-D`.

## 7. Cleanup

For each agent worktree, after its work has landed or been explicitly discarded:

```bash
git worktree unlock "$ROOT/api-retry"
"${CLAUDE_SKILL_DIR}/scripts/wt-preflight.sh" --fetch "$ROOT/api-retry"    # act on the verdict
git worktree remove "$ROOT/api-retry"
git branch -d agent/api-retry      # only once landed (preflight or host); -D if it refuses; or an explicit discard
```

`git branch -d` is not the landing check: if the agent's branch was pushed with
an upstream, `-d` compares it with that pushed copy and deletes it even when it
was never merged. Decide from the preflight's integration line or the merged
PR, then delete.

Then `git worktree prune -v`, confirm `git -C "$MAIN" status --short` is empty,
drop per-worktree databases and container projects, and report a table: task,
outcome (merged / PR open / discarded), worktree removed, branch deleted.
Run the cleanup serially; branch deletions rewrite shared ref storage.

## 8. Failure modes

| Symptom | Likely cause | Prevention or fix |
|---|---|---|
| Changes appear in the main checkout | Agent used a relative path or the wrong directory | Absolute paths in the brief; watch `git -C "$MAIN" status` |
| Commits land on the wrong branch | Agent ran `git switch` / `git checkout` | Rule in the brief; agent checks `git branch --show-current` before committing |
| Stash entries appear or vanish | The stash is shared by all worktrees | Forbid `git stash`; WIP commits instead |
| Port already in use, tests interfere | Shared port, database, or container project | Per-slot resources written into each worktree's env file |
| Two migrations with the same number | Hot file without a single owner | Reserve numbers, or the coordinator writes migrations |
| Agent "fixes" tests unrelated to its task | It did not know they failed before | Put the baseline in the brief |
| `Unable to create '.../index.lock': File exists` | Another git process in the same worktree (editor, second agent), or a crashed one | Wait. If no git process is running there, delete the file at `git -C <wt> rev-parse --path-format=absolute --git-path index.lock` |
| Worktree disappears mid-run | A cleanup script or `prune` ran | Lock active worktrees |
| Lockfile conflicts at integration | Several agents added dependencies | One owner for dependency changes |
| Agent cannot push or pull | New branch accidentally tracks `origin/main` | Create with `--no-track`; `git branch --unset-upstream` to repair |

## 9. Concurrency notes for git itself

- Each worktree has its own index and index lock, so commits in different
  worktrees run concurrently without interfering.
- No two worktrees can have the same branch checked out, so two agents never
  advance the same branch ref.
- Several agents fetching at once can fail to lock the same remote-tracking refs.
  Let the coordinator fetch; agents seldom need to.
- An automatic `git gc` may start after commits in any worktree. It guards itself
  with a lock and is normally harmless; if it slows a large parallel run, run
  `git maintenance run` (or `git gc`) once the agents are done instead of
  changing shared config mid-run.
