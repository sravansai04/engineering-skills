# GitLab CI/CD

Commands and platform behavior for each step of the triage, using the `glab` CLI. Replace `42` (merge request IID), `<pipeline-id>` and `<job-id>` with real values. `glab api` fills `:id` with the current project when run inside the repository. Commands marked "ask first" are visible to others or spend shared CI minutes; get the user's go-ahead before running them. Flag names and failure reasons shift between GitLab and `glab` releases, so check `--help` when a command is rejected.

## Contents

1. Find what failed (step 2)
2. Read the logs and the failure reason
3. Is main red? Compare the failure sets (step 4)
4. Re-run once (step 4)
5. What code did the pipeline test? (steps 4 and 6)
6. Timeouts and cancellation
7. Caches
8. False greens (step 8)
9. Secrets on fork MRs
10. Debug logging, linting and running jobs locally

## 1. Find what failed

```bash
glab ci get --merge-request 42 --with-job-details        # the MR's latest pipeline, with jobs
glab ci get -p <pipeline-id> -d -F json > /tmp/pipeline.json
glab ci get -p <pipeline-id> --status failed             # only failed jobs
glab ci list --ref my-branch                             # recent pipelines for the branch
```

List every job that didn't succeed, including `canceled` and manual jobs that never ran.

## 2. Read the logs and the failure reason

```bash
glab ci trace <job-id> > /tmp/ci-job-<job-id>.log                       # the job log
glab api projects/:id/jobs/<job-id>/trace > /tmp/ci-job-<job-id>.log    # raw log through the API
glab api projects/:id/jobs/<job-id> \
  | jq '{name, status, failure_reason, duration, started_at, finished_at, runner: .runner.description}'
```

The job's `failure_reason` often classifies the failure on its own:

| `failure_reason` | Usually means | Class |
|---|---|---|
| `script_failure` | A command in `script` exited non-zero. Also used for some image-pull and artifact-upload failures, so read the log. | Read the first error |
| `job_execution_timeout`, `stuck_or_timeout_failure` | The job hit its timeout, or got stuck | Resource limit |
| `runner_system_failure`, `runner_interrupted`, `runner_external_dependency_failure`, `api_failure`, `scheduler_failure` | The runner or GitLab itself failed | Infrastructure |
| `stuck_pending_no_matching_runners` | No runner matches the job's tags or protection settings | Runner availability (tree LEAF 2) |
| `missing_dependency_failure` | Artifacts from a job this one depends on are missing or expired | Pipeline config, or expired artifacts |
| `unmet_prerequisites` | The runner couldn't prepare the job's prerequisites | Infrastructure or config |

Job logs and artifacts can expire depending on project settings and `expire_in`, so save them early.

## 3. Is main red?

```bash
glab ci list --ref main                     # substitute the default branch
glab ci list --ref main --status failed
glab ci get -p <main-pipeline-id> -d
```

Compare the set of failing tests in main's latest pipeline with this one's. JUnit results uploaded with `artifacts:reports:junit` appear in the pipeline's and the MR's test report views. If main's pipeline failed before tests ran, this MR's own tests are unverified.

## 4. Re-run once (ask first)

```bash
glab ci retry <job-id>          # retry one job
```

A retried job runs on the same commit as the original pipeline. To test against today's target branch, rebase or merge the MR, or run a new pipeline.

## 5. What code did the pipeline test?

GitLab merge request pipelines come in kinds, and only some of them test a merge:

- **Branch pipelines and plain merge request pipelines** run on the source branch's own commit. Reproduce on the branch head.
- **Merged results pipelines** run on a temporary merge of the source branch into the target branch.
- **Merge train pipelines** run on the merge of the MR into the target branch together with the MRs queued ahead of it.

`CI_MERGE_REQUEST_EVENT_TYPE` (`detached`, `merged_result` or `merge_train`) says which kind ran; print it in a diagnostic step if the log doesn't show it. For merged results, the job's `CI_COMMIT_SHA` is the temporary merge commit, and `CI_MERGE_REQUEST_SOURCE_BRANCH_SHA` and `CI_MERGE_REQUEST_TARGET_BRANCH_SHA` give the two parents to rebuild it (`reproduce-locally.md` §2). Merge requests from forks can be fetched with `git fetch origin merge-requests/42/head:mr-42-head`.

## 6. Timeouts and cancellation

- **A timeout ends as `failed`, not `canceled`,** with `failure_reason` `job_execution_timeout` and a log line saying the job's execution took longer than its limit. A job's `timeout:` overrides the project's CI/CD timeout (and may be longer than it), but a runner's maximum timeout, when one is set, caps both.
- **`canceled`** usually comes from a person, or from auto-cancelling redundant pipelines: when a newer pipeline starts on the same branch, jobs marked `interruptible: true` in the older pipeline are cancelled.
- A cancelled or timed-out job's script can end with exit 143 or 137 because the runner stopped it. On such a job, that is not evidence of OOM.

## 7. Caches

- **Keys.** `cache:key:files` derives the key from files such as the lockfile; `cache:key:prefix` adds a fixed prefix. Put the runtime version and image in the key or prefix, so a runtime upgrade doesn't restore incompatible native builds.
- **Bypass** by changing the key or prefix in `.gitlab-ci.yml`, or clear all of the project's runner caches with the "Clear runner caches" action on the pipelines page (ask first; it affects every branch).
- **Scope.** Caches are local to a runner unless a distributed cache is configured, so a cache problem can appear only on some runners. Note the runner in the job log when comparing runs.

## 8. False greens

- **`allow_failure: true`** lets a job fail while the pipeline shows as passed, with a warning marker ("passed with warnings"). Treat a failed job that is allowed to fail as red for the purpose of this triage.
- **Manual jobs** defined with `when: manual` outside `rules` default to `allow_failure: true`, so one that never ran doesn't stop the pipeline from passing. (Inside `rules`, `when: manual` defaults to blocking.)
- **`rules:changes` / `only:changes`** can leave a job out of the pipeline entirely. Check that the job you care about exists in the pipeline, not just that the pipeline passed.
- **"Skipped pipelines are considered successful"** is a project merge-check setting. With it on, a skipped pipeline doesn't block the merge.
- **Shell behavior.** For Bash-based jobs, a pipe can hide a failure unless the script sets `pipefail`; check the job's shell and any `set +e`. On Windows runners with PowerShell, a native command's non-zero exit code doesn't stop the script by itself, so a multi-command job can pass on the last command's success alone.

## 9. Secrets on fork MRs

By default, pipelines for merge requests from forks run in the fork's project, without the parent project's CI/CD variables. Protected variables are also only available to pipelines on protected branches and tags. Expect empty secrets or 401/403 in those cases. Running a fork MR's pipeline in the parent project gives it the parent's variables, so a maintainer should review the code first.

## 10. Debug logging, linting and running jobs locally

- **Lint:** `glab ci lint` validates `.gitlab-ci.yml`. The pipeline editor's full configuration view shows the result after `include:` and `extends:` are merged in.
- **Debug logging:** setting the variable `CI_DEBUG_TRACE: "true"` on a job prints every command and variable. It can expose secret values in the log, so prefer a targeted diagnostic step, and ask first.
- **Running locally:** start the job's `image:` with its `services:` on a shared Docker network, export its `variables:`, and run `before_script` and `script` lines in order:
  ```bash
  docker run --rm -it --platform linux/amd64 -v "$PWD":/work -w /work <job-image> bash
  ```
