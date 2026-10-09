# Jenkins, CircleCI, Azure Pipelines and Others

Platform behavior for each step of the triage on systems other than GitHub Actions and GitLab. The questions are the same everywhere: which jobs didn't succeed and why, where the raw log is, whether the default branch is red, how to re-run once, what code was tested, how timeouts and cancels are reported, and what can make a pipeline look green when it isn't. Actions marked "ask first" are visible to others or spend shared CI capacity; get the user's go-ahead. UI labels and API fields shift between versions, so confirm against your instance.

## Contents

1. Jenkins
2. CircleCI
3. Azure Pipelines
4. Any other CI system

## 1. Jenkins

**Find what failed and read the log.** Every build URL has machine-readable endpoints (add `--user "$JENKINS_USER:$JENKINS_API_TOKEN"` when the instance needs auth):

```bash
curl -s "$BUILD_URL/api/json?tree=result,building,duration,timestamp" | jq .
curl -s "$BUILD_URL/consoleText" > /tmp/ci-build.log          # the raw console log
curl -s "$BUILD_URL/testReport/api/json" > /tmp/ci-tests.json # test results, if the junit step ran
```

For multibranch pipelines, the default branch's latest builds are under `$JOB_URL/job/main/` (`lastCompletedBuild/api/json`, `lastSuccessfulBuild/api/json`), which answers "is main red?". Compare the failing tests in both test reports, not just the first error.

**Build results:**

| Result | Usually means |
|---|---|
| `FAILURE` | A step failed. Find the first error in the console log. |
| `UNSTABLE` | The build finished but something was marked unstable, most often failing tests recorded by the `junit` step. Treat it as red. Depending on how results reach your code host, it may not block a merge. |
| `ABORTED` | A person stopped it, a newer build superseded it (for example `disableConcurrentBuilds(abortPrevious: true)`), or a `timeout` step fired. A timeout logs `Timeout has been exceeded` (often after `Cancelling nested steps due to timeout`), so search for it and compare the duration with the configured limit. A timeout that interrupts a shell step is sometimes reported as `FAILURE` instead. |
| `NOT_BUILT` | A stage or the build was skipped, for example by a `when` condition. |

**Infrastructure signatures:** an agent going offline mid-build, `ChannelClosedException`, "Cannot contact" an agent, or a node that never comes online. Check other jobs on the same agent and label.

**Stale workspaces.** Persistent agents reuse a job's workspace between builds unless the pipeline cleans it. Leftover build output, generated files or dependencies can make a build pass or fail depending on which agent and workspace it lands on, which looks like flakiness. Compare the agent names in the green and red runs, and check for a clean step (`cleanWs()`, `deleteDir()`, or a fresh checkout).

**Shell behavior.** The `sh` step runs the system shell with `-xe` unless the script has its own shebang. That stops on a failing command but doesn't set `pipefail`, and `/bin/sh` on many Linux images is a shell without `pipefail` at all. A script starting with `#!/bin/bash` followed by `set -euo pipefail` gets strict behavior; note that a custom shebang also drops the default `-xe`. `returnStatus: true` and `catchError` turn failures into values, which can hide them.

**Re-run and diagnose (ask first).** "Rebuild" or "Replay" from the build page. Replay can run a modified Jenkinsfile once without committing it, which suits diagnostics, but it is still a visible build.

**Lint a declarative Jenkinsfile:**

```bash
curl -X POST --user "$JENKINS_USER:$JENKINS_API_TOKEN" \
  -F "jenkinsfile=<Jenkinsfile" "$JENKINS_URL/pipeline-model-converter/validate"
```

The SSH CLI's `declarative-linter` command does the same. Neither validates scripted pipelines.

**What was tested.** For pull requests, multibranch setups can build either the PR head or a merge with the target branch, depending on the branch source's discovery settings. The checkout section of the console log names the commits; reproduce on the same one.

## 2. CircleCI

- **Find and read.** The job page lists each step with its output, and the "Tests" tab shows results collected by `store_test_results`. Download step output from the page or the API, and save it to a file before searching.
- **No-output timeout.** A `run` step that prints nothing for 10 minutes (the default `no_output_timeout`) is killed with `Too long with no output (exceeded 10m0s): context deadline exceeded`. That is a hang, a prompt waiting for input, or output buffering, more often than slowness. Raising `no_output_timeout` helps only after you have found which.
- **Memory.** Exit 137 or a "killed" message usually means the job exceeded its resource class's memory, unless the job was being cancelled.
- **Re-run (ask first).** "Rerun workflow from failed" re-runs failed jobs on the same commit. "Rerun job with SSH" re-runs the job and keeps the machine open for you to inspect, which is the most direct way to look at the real environment when a failure won't reproduce locally. Close the SSH session when done; it holds a runner.
- **Test splitting.** With `parallelism` and `circleci tests split --split-by=timings`, which tests share a container depends on timing data, so order-dependent failures can move between containers. Reproduce with the same file list the failing container received (print it in a diagnostic step).
- **Lint.** `circleci config validate` checks the config locally. `circleci config process` shows it with orbs expanded.
- **Secrets on fork PRs.** Fork PR builds don't receive project secrets unless the project explicitly enables passing them, which exposes them to untrusted code.

## 3. Azure Pipelines

- **Find and read:**
  ```bash
  az pipelines runs list --branch main --top 5 -o table              # is the default branch red?
  az pipelines runs show --id <run-id> -o json                       # result, sourceVersion, timing
  ```
  Logs for each job and task are on the run page and through the REST API's build logs endpoints.
- **Results.** `succeeded`, `partiallySucceeded`, `failed`, `canceled`. `partiallySucceeded` usually means a task with `continueOnError: true` failed. That is a false green for the triage: find the task that failed.
- **Timeouts.** A job that exceeds `timeoutInMinutes` (60 by default) is cancelled, not failed, with `The job running on agent <name> ran longer than the maximum time of N minutes` in the log. Hosted agents also have their own maximum job length, which wins over a larger setting.
- **Infrastructure signatures.** `We stopped hearing from agent` means the agent stopped sending heartbeats. Check whether the job's previous task was memory- or CPU-heavy before calling it infrastructure.
- **Debug logging.** Set the pipeline variable `system.debug` to `true` for the run (ask first).
- **What was tested.** PR builds usually run on a merge commit (`refs/pull/<n>/merge`), and `Build.SourceVersion` in the log names the commit.

## 4. Any other CI system

For Buildkite, TeamCity, Bitbucket Pipelines, Drone, Woodpecker, Tekton, or an in-house system, find these before triaging. The docs, the CLI's `--help`, or the job page usually answer them:

1. **The job list with statuses** for a run, including cancelled and skipped jobs.
2. **The raw log** for one job, as a downloadable file or an API endpoint.
3. **How a timeout is reported** (failed, cancelled, aborted, or a separate "timed out" status) and the configured limit.
4. **How to re-run one job once** on the same commit, and whether a re-run picks up a newer base.
5. **Which commit was tested** for a pull request: the head, or a merge with the target.
6. **How results reach the code host,** and which check names are required there. A status the code host never receives leaves the merge blocked or, worse, ungated.
7. **What can make the pipeline green anyway:** soft-fail or allow-failure settings, skipped steps, shells without `pipefail`.
8. **How caching works** and how to bypass one entry.
