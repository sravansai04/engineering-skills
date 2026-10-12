---
name: verify-before-done
description: 'Proves a code change is finished: runs the project''s own checks and reads the output, exercises the change through its real entry point, self-reviews the diff, and reports verified versus not. Use at the end of an implementation, bug fix, or refactor you did in this session, even unasked, e.g. "are we done", "did you run the tests", "make sure it builds". Not for reviewing a branch or PR (pr-review), a failing check (ci-failure-triage), or UI checks in a real browser (browser-testing).'
compatibility: Bundled scripts need git and bash with POSIX grep and awk (on Windows use Git Bash or WSL, or the manual commands in the steps); node or python3 is optional.
---

# Verify Before Done

"Done" is a claim about the world; this skill turns it into evidence. It prevents the costly failures: calling work done because the code was written, quoting a green run from before the last edit, watching a stale build behave, counting a test that never ran, and quietly skipping the step that would have caught the bug.

## Ground rules

- **Evidence over belief.** Every claim in the report cites a command you ran after your last edit and the output you read. "Should work" belongs under "Not verified".
- **The last edit resets the clock.** Any change after a green run, even a one-line lint fix, invalidates the results it could affect. Step 8 (Final gate) exists for this.
- **Never weaken a check to get green.** No skipped, deleted, or loosened tests; no inline suppressions; no `--no-verify`; no snapshots regenerated unread. Config counts too: a lint rule turned off or to warn, new ignore or exclude paths, relaxed compiler strictness, a lower coverage threshold, `--passWithNoTests`, or a non-blocking CI step (`|| true`, `continue-on-error`, `allow_failure`). Anything done deliberately goes in the report with the reason.
- **Use the project's tools; never download one ad hoc.** In a non-interactive shell, `npx <tool>` silently fetches any package with that name if the tool is not installed. Use the package script or `npx --no -- <tool>`. An undeclared tool is a check not run: record it and suggest adding it.
- **Verify locally or in a sandbox.** Do not push, publish, deploy, or migrate shared or production systems as a way of checking unless the user asks.
- **Scale effort to risk, but never skip silently.** Whatever you skip goes in the report with the reason.

## Workflow

### 1. Define "done" and the depth of verification

List the acceptance criteria from the request (and the plan, if `implementation:plan-feature` produced one), and next to each, how you will prove it: a test name, a command, a page to load. This list is the spine of the report. For a bug fix, the original reproduction is a criterion, ideally with a regression test that fails without the fix (see `implementation:tdd`). Then choose the depth:

| Change | Minimum verification |
|---|---|
| Docs or comments only | `git diff --stat` shows no code touched; render or preview the docs; check links |
| Config or env only | Config validation, if any; the app starts with it; the affected path exercised |
| Small, local code change | Format, lint, types, build, the affected module's tests, the full unit suite if it is fast, one real exercise (Step 4) |
| Public API, shared code, cross-cutting change, or dependency upgrade | Everything CI runs, including integration tests and the packages that depend on the changed one; build the distributable; exercise at least one consumer |

### 2. Discover the project's checks

Use the commands the project already defines; wrappers such as `make check` carry its configuration. Trust CI configuration first (it gates the merge), then agent and contributor docs (`AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, README), then task runners and manifests, and tool defaults last.

`${CLAUDE_SKILL_DIR}` stands for this skill's folder, the directory that contains this SKILL.md. Claude Code fills it in; in other tools, use that folder's path.

```bash
bash "${CLAUDE_SKILL_DIR}/scripts/discover-checks.sh"               # current directory
bash "${CLAUDE_SKILL_DIR}/scripts/discover-checks.sh" packages/api  # a sub-project
```

The script only reads files; it lists scripts, targets, hooks, CI steps, and the services CI starts. Manual equivalents, per-ecosystem commands, and monorepo runs are in `references/discovering-checks.md`. Before running anything, settle two more things:

- **Runtime and services.** Compare your language version with CI's (`.nvmrc`, `.python-version`, `.tool-versions`, `go.mod`, the CI matrix), and start the databases or brokers CI starts; integration tests often skip silently without them. Report any mismatch as weaker evidence.
- **The target branch.** `git fetch`, then compare with the branch you will merge into. If it has moved, bring your branch up to date before the final run (merge, or rebase if the branch is not yet shared), because PR CI usually tests the merge result; otherwise report "verified against base `<sha>`, N commits behind target".

### 3. Run the checks and read the output

Run cheap checks first: format, lint, type-check, build, unit tests, then integration and end-to-end. Iterate with the narrowest command; the full relevant set runs in the Final gate (Step 8). Use non-interactive forms (`CI=true`, `vitest run`, no watch mode), because anything that prompts or watches hangs an agent shell. Then read results with these traps in mind:

- **Pipes hide exit codes.** `npm test | tail` reports `tail`'s status. Log instead, or use `set -o pipefail`:
  ```bash
  npm test > /tmp/verify-test.log 2>&1; echo "exit=$?"; tail -n 60 /tmp/verify-test.log
  ```
- **Zero is not a pass, and exit 0 is not always one.** "No tests collected" or "0 files checked" means nothing was checked. Some tools report problems only in their output and still exit 0 (`gofmt -l`, audit tools in report mode).
- **Confirm the new tests ran**, by name in the output or the runner's list mode (`references/discovering-checks.md` §4).
- **Make the new test fail once.** Revert the key line of the fix *by hand*, watch the test fail for the right reason, restore the line by hand, and rerun. Never use `git checkout`, `git restore`, or `git stash` for this on uncommitted work: they discard or hide the whole implementation, not one line. Commit first if you want a restore point. A test that passes with and without the change proves nothing.
- **Caches, warnings, flakes.** Force a rerun if you suspect a stale cached result (flags in `references/discovering-checks.md` §5). New warnings from your change are findings. If a rerun changes the result, report the test as flaky, not green.
- **"Pre-existing" needs evidence from where your branch started**, not from the target's current tip:
  ```bash
  git fetch origin
  dir="$(mktemp -d)/verify-base"   # a fresh path, so two sessions never collide
  git worktree add --detach "$dir" "$(git merge-base origin/main HEAD)" && echo "$dir"
  # install deps and run the check in that directory, then:
  git worktree remove "$dir"
  ```
  Or point to the same failure in recent CI runs on the target (for GitHub, `gh run list --branch main --limit 5`). Failing at the merge-base but fixed on the target's tip means: update your branch.

If your change breaks a check, fix the cause and rerun the full relevant set; if the cause is unclear, switch to `implementation:debug-root-cause`. A check that cannot run here even with the project's documented setup goes under "Not verified" with the exact command. If the changed area has no tests, say so and propose one (`implementation:tdd`).

### 4. Exercise the change for real

Tests prove what they assert; users experience behavior. Drive the change through the entry point a user or caller would use:

| Change | Minimum real exercise |
|---|---|
| CLI | Realistic arguments; check stdout, stderr, and exit code; once with bad input |
| HTTP/API | Start the server; send valid, invalid, and unauthorized requests; check status, body, and server log |
| UI | Load it in a browser (automation tool if available); click through; check console and failed requests; narrow viewport; keyboard; or `frontend:browser-testing` for evidence-backed verification |
| Library | Import the public API from a scratch script, the way a consumer would |
| Job, worker, event handler | Trigger it, confirm the side effect, run it twice for idempotency |
| Schema or data | Migrate a fresh database; roll back and reapply if supported (`data-api:db-migration-safety`) |
| Config or feature flag | Start the app with the new config; exercise both flag states |

Every change gets a happy path, the edge cases that apply (empty, boundary, very large, unicode, duplicate, concurrent), and the **failure path**: what the user sees, and proof nothing is left half-written. For a bug fix, rerun the original reproduction.

- **Prove you are running the final code.** Rebuild after the last edit, restart servers that do not hot-reload, reinstall or use an editable install, rebuild container images, and hard-reload the browser with the cache disabled; confirm with a version string or startup log line where you can. Stale code is a common source of false "verified" claims.
- **Point side effects at safe targets.** Before triggering payments, email, SMS, webhooks, or writes, check where the effective config points (database URL, API base URLs, live versus test keys) and use a local service, mail catcher, test mode, or stub. If you cannot confirm the target is not production, do not trigger it; list it under "Not verified".
- **No browser, no UI claim.** A passing build is not evidence that a screen looks or works right.

Stop servers and remove temporary data you created. Recipes, readiness polling, and an edge-case catalog: `references/exercising-behavior.md`.

### 5. Review your own diff

Read the change the way a reviewer will, against the branch you will merge into (shown as `origin/main`):

```bash
git status --short                                  # untracked (??) files appear only here and in scan-diff
git diff --stat "$(git merge-base origin/main HEAD)"
git diff "$(git merge-base origin/main HEAD)"        # committed, staged and unstaged changes to tracked files
bash "${CLAUDE_SKILL_DIR}/scripts/scan-diff.sh"      # or: scan-diff.sh origin/develop
```

`git diff <merge-base>` never shows untracked files, so read `git status` too: a new file you never added passes locally and breaks in CI. `scan-diff.sh` flags leftovers in added lines and untracked files (debug code, focused or skipped tests, suppressions, TODOs, secret-like values, suspicious files) and weakened checks (edited check config, non-blocking CI steps, deleted or shrunk tests), without ever printing a secret value. Exit 0 means nothing flagged, 1 means decide each hit. Its secret rules are a fallback: if the repo configures a secret scanner or one is installed, also run it with redaction on, e.g. `gitleaks git --redact --log-opts="$(git merge-base origin/main HEAD)..HEAD" .` plus `gitleaks dir --redact <changed paths>` for uncommitted files.

The scan is a net, not the review. Read every hunk for what patterns cannot see:

- [ ] Every changed file is intended; no drive-by reformatting or refactors (revert or split them out)
- [ ] Every scan-diff hit decided: removed, or kept with a reason you can state in the report
- [ ] No secrets, personal data, or internal hostnames in code, fixtures, logs, or snapshots, including ones no pattern matches
- [ ] No weakened checks in lint, type, test, coverage, or CI config; no deleted tests or assertions
- [ ] Lockfile changes only where you changed dependencies, made with the project's package-manager version
- [ ] Generated files regenerated from source where the project commits them; snapshots read line by line
- [ ] Errors handled, not swallowed; names, comments, and docstrings match what the code now does

If a real credential was ever committed, deleting it later does not remove it from history: tell the user it needs rotating, and do not rewrite shared history without asking. Deeper passes: `review-suite:secure-code-review`, `review-suite:performance-review`.

### 6. Confirm the new code is reachable

Code can compile and pass its own tests while nothing calls it. Search for callers, including files not yet added (`git grep -n --untracked NewThing`); check the registration point your stack needs (route table, DI bindings, registries, exports, CLI entry points, navigation, permissions); check flag names and defaults. Zero references is a red flag, not proof: many frameworks discover code by file location, naming convention, decorators, or reflection. The strongest evidence is Step 4 through the real entry point. Per-framework details: `references/wiring-and-companions.md`.

### 7. Ship what must travel with the change

Following the repo's existing conventions (`references/wiring-and-companions.md` §4), check whether the change needs: tests, including a regression test for a bug fix; user or API docs (README usage, OpenAPI or schema files, docstrings on public APIs); a changelog or release-note entry; new config keys in example files and deployment config, with safe defaults; a migration for a schema change; regenerated clients, types, or protobuf and GraphQL output; compatibility notes for changed public APIs, CLI flags, or config keys; an ADR for a significant architectural decision (`workflow:adr-writer`).

### 8. Final gate

Steps 4 to 7 usually cause edits: a removed debug line, added wiring, docs, a changelog entry, regenerated files. Unless the full relevant set already passed after your very last edit:

1. Rerun the full relevant set from Step 3.
2. Rebuild, then re-exercise any behavior the edits could affect.
3. Rerun `scan-diff.sh` and `git status --short`.

Only results from this pass go in the report. If you commit, check `git status --short` afterwards: the commit must hold exactly what you verified (a new file left unstaged is the classic gap). If the task includes pushing, wait for CI (`gh pr checks <number> --watch` or the platform's equivalent) and report its result; a local pass with CI pending is "Done, with gaps".

### 9. Report honestly

- **Done**: every applicable check passed in the Final gate, the behavior was exercised, and nothing under "Not verified" bears on correctness.
- **Done, with gaps**: the work is complete, but some verification could not run here; each gap has its reason and the exact steps to close it.
- **Not done**: a check fails, a criterion is unmet, or you are blocked. Say which, and what happens next.

Report numbers, not adjectives ("212 passed, 0 failed, 3 skipped"). Use "verified" only for things you ran. List every weakened check and how you established that any failure is pre-existing. Put the status on the first line; never follow an optimistic status with a failure halfway down.

Use the template under Report format.

## Report format

```markdown
## Verification report

**Status:** Done | Done, with gaps | Not done
**Change:** one sentence on what changed and why
**Base:** target branch, when fetched, merge-base sha, commits behind its tip
**Verified state:** HEAD <sha> plus uncommitted changes (or: clean tree; commit <sha> contains exactly what was tested)
**Environment:** runtime and service versions, e.g. Node 20.11 locally (CI matrix 18, 20); Postgres 16 via docker compose

### Acceptance criteria
- [x] criterion: how it was proven (test name, command, observed result)
- [ ] criterion: not met or not verified, and why

### Checks run (Final gate, after the last edit)
| Check | Command | Result |
|---|---|---|
| Format | `...` | pass |
| Lint | `...` | pass, 0 new warnings |
| Types | `...` | pass |
| Build | `...` | pass |
| Unit tests | `...` | N passed, 0 failed, M skipped (pre-existing) |
| Integration | `...` | pass, or not run (reason) |
| CI | `gh pr checks <n>` | pass, pending, or n/a (not pushed) |

### Behavior exercised
- Fresh build: how you know the run used the final code
- Happy path: what you ran, what you observed
- Edge cases: ...
- Failure path: ...

### Diff self-review
- Files changed: N, all intended (list any non-obvious ones)
- Removed before finishing: debug log in X, stray file Y
- Secrets, generated files, lockfiles, check config: none, or explained
- Wiring: how the new code is reached (route, export, flag state)

### Not verified
- Item: why it could not be verified here, and the exact command or steps to verify it

### Notes and follow-ups
- Weakened checks with justification, pre-existing failures with evidence, risks, follow-up tickets
```

Write "n/a" for a section that truly does not apply rather than deleting it. Filled examples for each status: `references/worked-examples.md`. If the user wants a commit message or PR description next, hand this report to `workflow:commit-message` or `workflow:pr-description`.

## Related skills

- `implementation:tdd` for a regression test, `implementation:debug-root-cause` when a check fails for an unclear reason, and `implementation:plan-feature` for the acceptance criteria.
- `review-suite:pr-review` for a judgment on a branch or PR, whoever wrote it; `review-suite:secure-code-review` and `review-suite:performance-review` for deeper passes.
- `frontend:browser-testing` to verify a UI change in a real browser with evidence (console, network, screenshots at several widths).
- `workflow:ci-failure-triage` when CI goes red after you push, and `workflow:git-worktrees` for the merge-base worktree used to prove a failure pre-existing.
- `workflow:commit-message` and `workflow:pr-description` once the work is verified.

Skills are named here as `plugin:skill`; an agent that lists skills by bare name knows each one by the part after the colon (`review-suite:pr-review` is `pr-review`). If a skill named here isn't installed, give the short version inline and list the deeper pass as a follow-up.

## Reference files

Both scripts are read-only and need git plus bash with POSIX `grep` and `awk` (on Windows, Git Bash or WSL; otherwise use the manual commands above).

- `scripts/discover-checks.sh` (Step 2) and `scripts/scan-diff.sh` (Steps 5 and 8; `--help` explains the output). Both check themselves with `--selftest`.
- `references/discovering-checks.md`: unfamiliar stacks, monorepos and dependents, one test by name, caches, lockfile drift.
- `references/exercising-behavior.md`: Step 4 recipes, fresh builds and safe targets, the edge-case catalog.
- `references/wiring-and-companions.md`: Steps 6 and 7, registration by framework, companion-change conventions.
- `references/worked-examples.md`: a filled report for each status, and phrasing fixes; read before your first report.
