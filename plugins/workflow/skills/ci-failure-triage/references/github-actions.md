# GitHub Actions

Commands and platform behavior for each step of the triage. Replace `1234` (PR number), `<run-id>` and `<job-id>` with real values. Commands marked "ask first" are visible to others or spend shared CI minutes; get the user's go-ahead before running them.

## Contents

1. Find what failed (step 2)
2. Read the logs, including when they come back empty
3. Is main red? Compare the failure sets (step 4)
4. Re-run once (step 4)
5. Get the exact code CI tested (steps 4 and 6)
6. Timeouts, cancellation and signals
7. Caches
8. Triggers, required checks and false greens (step 8)
9. Secrets on fork and bot PRs
10. Shells and exit codes
11. Debug logging and running jobs locally

## 1. Find what failed

```bash
gh pr checks 1234                      # every check: pass / fail / pending / skipping / cancel
gh pr checks 1234 --required           # only the checks that gate merging
gh pr view 1234 --json headRefOid,mergeable,mergeStateStatus
gh run list --branch my-branch --limit 10
gh run view <run-id> --json headSha,attempt,status,conclusion,jobs --jq '{
  headSha, attempt, status, conclusion,
  notOk: [.jobs[] | select(.conclusion != "success" and .conclusion != "skipped")
          | {name, databaseId, conclusion, startedAt, completedAt}]}'
```

The filter keeps cancelled jobs on purpose. Compare each cancelled job's `startedAt`/`completedAt` span with its `timeout-minutes` (section 6) before calling it collateral.

## 2. Read the logs

```bash
gh run view <run-id> --log-failed > /tmp/ci-<run-id>.log          # failed steps only
gh run view --job <job-id> --log > /tmp/ci-job-<job-id>.log       # the whole job
gh run view <run-id> --attempt 1 --log-failed > /tmp/ci-<run-id>-a1.log   # the original attempt after a re-run
gh run download <run-id> -D /tmp/ci-artifacts                     # JUnit XML, screenshots, dumps, if uploaded
```

- **Empty output is not "no error".** `gh run view --log-failed` and `--log` have, in several gh releases, printed nothing and still exited 0, when gh couldn't match the downloaded log archive to the job's steps. If the output is empty, fetch the raw job log from the API, and upgrade gh:
  ```bash
  gh api repos/{owner}/{repo}/actions/jobs/<job-id>/logs > /tmp/ci-job-<job-id>.log
  ```
- **Attempts.** After a re-run, `gh run view` shows the latest attempt. Pass `--attempt N` to read the one that failed.
- **Retention.** Logs and artifacts expire after the repository's retention period (90 days by default). Save them to files early.
- **Annotations.** Timeouts, invalid workflow files and some runner errors appear as annotations on the run summary, not always in the step log.

## 3. Is main red?

```bash
gh run list --branch main --workflow ci.yml --limit 5      # substitute the default branch and workflow file
gh run view <main-run-id> --log-failed > /tmp/ci-main.log
gh run download <main-run-id> -n <junit-artifact-name> -D /tmp/ci-main-junit
```

Compare the set of failing tests in main's latest run with this run's set, not just the first error. If main's run failed before tests ran (build, compile, collection, setup), this PR's own tests are unverified.

## 4. Re-run once (ask first)

```bash
gh run rerun <run-id> --failed           # only the failed jobs
gh run rerun <run-id> --failed --debug   # with runner and step debug logging
gh run rerun --job <job-id>              # one specific job
gh run watch <run-id> --exit-status
```

A re-run reuses the original commit, the original merge commit for `pull_request` runs, and the original workflow file. It can't pick up anything that has landed on the base branch since. To test against today's base, update the branch.

## 5. Get the exact code CI tested

- **`pull_request` runs test a merge.** They check out `refs/pull/<n>/merge`, a merge of the PR head into the base as it was when the run started, and `GITHUB_SHA` is that merge commit. `push` runs test the pushed commit itself.
- **Find both SHAs in the log.** For a `pull_request` run, the checkout step's log includes a line like `HEAD is now at <merge-sha> Merge <head-sha> into <base-sha>`. Use those two SHAs to rebuild the exact merge (`reproduce-locally.md` §2):
  ```bash
  grep -m1 'HEAD is now at' /tmp/ci-job-<job-id>.log
  ```
- **Today's merge ref** is `git fetch origin refs/pull/1234/merge:pr-1234-merge`. It reflects the current base, which may differ from what the run tested.
- **Fork PRs.** The head commit lives in the fork, so `git fetch origin` won't bring it. Fetch it through the PR ref:
  ```bash
  git fetch origin pull/1234/head:pr-1234-head
  ```

## 6. Timeouts, cancellation and signals

- **A job timeout ends as `cancelled`, not `failure`.** The default `timeout-minutes` is 360 for a job. The run summary usually carries an annotation that the job "has exceeded the maximum execution time of N minutes", but sometimes only "The operation was canceled." The reliable check is the job's duration against its configured timeout.
- **Other causes of `cancelled`:** a `concurrency` group with `cancel-in-progress: true` cancelling an older run when a newer push arrives; `strategy.fail-fast` (on by default) cancelling the other matrix legs when one fails; a manual cancel.
- **How the runner stops a step.** On a cancel, the runner sends SIGINT to the step's process, then SIGTERM if it hasn't exited after 7.5 seconds, then kills the process tree after another 2.5 seconds. A cancelled or timed-out step therefore commonly ends with exit 130, 143 or 137. None of those mean OOM on a cancelled step. Child processes of a shell step may not receive the signal at all, so cleanup code in them may never run.
- **Jobs with `if: always()`** keep running through a cancel, which can make a cancelled run look partly green.

## 7. Caches

```bash
gh cache list --limit 50                 # key, size, ref, last used
gh cache list --key npm-                 # entries whose key starts with a prefix
gh cache delete <cache-id-or-key>        # ask first
```

- **Scope.** A run can restore caches created on its own ref and on the base branch. Caches created by a PR run are scoped to that PR's merge ref, so a poisoned PR cache doesn't affect main, and main can stay green.
- **Immutability.** An entry is never overwritten under the same key. A bad entry keeps being restored until its key changes, it is deleted, or it is evicted after going unused for 7 days.
- **Bypass without deleting** by changing the key in the workflow, for example adding a version suffix. Then fix the key properly: include `runner.os`, `runner.arch`, the runtime version, and `hashFiles()` of the lockfile.

## 8. Triggers, required checks and false greens

- **Merge conflicts.** Workflows triggered by `pull_request` don't run while the PR has a merge conflict. `gh pr view 1234 --json mergeable,mergeStateStatus` shows it.
- **Path, branch and commit-message skips.** If a workflow is skipped at the trigger by `paths`, `branches` or a `[skip ci]`-style marker, its required checks stay in the "Expected" state ("Waiting for status to be reported") and block the merge. A job skipped by a job-level `if:` reports success instead, so move path logic into a job-level condition when the check is required.
- **Required check names.** List the names the branch requires and compare them with the names reported on the head SHA:
  ```bash
  gh ruleset check main                                          # rulesets that apply to the branch
  gh api repos/{owner}/{repo}/rules/branches/main \
    --jq '[.[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context]'
  gh api repos/{owner}/{repo}/branches/main/protection/required_status_checks --jq '.contexts'  # classic protection; needs admin access
  gh pr checks 1234 --json name,state,bucket                     # what actually reported
  ```
  A matrix job's check name includes its matrix values, for example `test (3.11)`. Renaming a job, changing its `name:`, or changing a matrix value creates a new check name, and the old required one waits forever. Fix by updating the required list in the same change (admin, ask first), or by making one aggregate job that `needs:` every leg the only required check. If that aggregate job uses `if: always()`, have it fail explicitly when any needed job didn't succeed, or a failed leg can leave it green.
- **Merge queues.** Workflows that provide required checks need the `merge_group` trigger, or checks never report for queued PRs.
- **First-time contributors.** Depending on repository settings, runs from a first-time contributor's fork wait for a maintainer to click "Approve and run". Until then the checks never start.
- **Skipped dependents.** A job skipped because a job it `needs:` failed shows as skipped, not failed. Read the whole run's conclusion, not the skipped job.
- **Watching.** `gh run watch --exit-status` and `gh pr checks --watch` can return before every workflow has registered on the commit. Re-read the final state once it settles:
  ```bash
  gh pr view 1234 --json headRefOid --jq .headRefOid
  gh pr checks 1234 --required
  gh run view <run-id> --json headSha,status,conclusion,jobs
  ```

## 9. Secrets on fork and bot PRs

- **Fork PRs.** Workflows triggered by `pull_request` from a fork receive no repository secrets (only `GITHUB_TOKEN`), and the token is read-only. Expect empty secrets, 401/403, or "Resource not accessible by integration".
- **Dependabot PRs.** Runs triggered by Dependabot get only Dependabot secrets, not Actions secrets, and a read-only `GITHUB_TOKEN` by default.
- **Don't fix this with `pull_request_target`** while checking out and running the PR's code. That trigger runs with the base repository's secrets and a write token, so it hands them to untrusted code. Skip the secret-dependent job for forks and bots with a visible notice, or run it after a maintainer has reviewed the code.

## 10. Shells and exit codes

- **Linux and macOS, no `shell:` set:** the step runs as `bash -e {0}`, which stops on a failing command but doesn't set `pipefail`. `npm test | tee out.log` passes even when the tests fail. Setting `shell: bash` explicitly runs `bash --noprofile --norc -eo pipefail {0}`.
- **Windows, no `shell:` set:** the default is `pwsh`. The runner prepends `$ErrorActionPreference = 'stop'` and appends a line that exits with `$LASTEXITCODE`. `'stop'` doesn't react to a native command's non-zero exit code, so in a multi-line step only the last native command's exit code decides the result: `npm test` followed by `npm run build` turns green when the tests fail. Split the commands into separate steps, check `if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }` after each one, or set `$PSNativeCommandUseErrorActionPreference = $true` at the top of the step (PowerShell 7.4 and later).
- **Masks to grep the workflow for:** `|| true`, `continue-on-error: true`, `set +e`, and `if: always()` on a job that reports a required check.

## 11. Debug logging and running jobs locally

- **Debug logging:** `gh run rerun <run-id> --debug` (ask first), or set the repository variables `ACTIONS_STEP_DEBUG` and `ACTIONS_RUNNER_DEBUG` to `true`. Debug output can be large and may include more of the environment than usual.
- **Lint:** `actionlint` catches most workflow syntax and expression errors, if it is installed.
- **`act`** (from the nektos project) runs workflow jobs in local containers:
  ```bash
  act -l                                             # list jobs and the events that trigger them
  act -j test                                        # run the job whose id is "test"
  act pull_request -j test                           # simulate the pull_request event
  act -j test --secret-file .secrets                 # read secrets from a file; never commit it
  act -j test --container-architecture linux/amd64   # on ARM machines
  ```
  Its default images aren't the hosted runner images, and some platform features behave differently. A local `act` pass is weaker evidence than a CI pass.
