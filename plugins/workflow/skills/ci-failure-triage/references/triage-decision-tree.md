# CI Triage Decision Tree

This file walks from "a check is red" (or "this green looks suspicious") to a leaf that names an action and when you're done. Answer each question with evidence such as a log line, a run link, or a command's output, not with an impression. Most leaves name a class from the table in SKILL.md step 5; `failure-signatures.md` §3 has the details for each class. Platform commands are in your platform file.

Actions that others can see (re-runs, pushes, issue comments, cache deletion, config changes) still need the user's go-ahead, wherever the tree reaches them.

## The tree

```
START: a check is red, or a green looks wrong (jump to G)
│
├─ A. Did the check run on the latest commit at all?
│    ├─ Never started, and the PR has a merge conflict ──────────────► LEAF 9 (stale branch)
│    ├─ Never started / "waiting for status", no conflict ───────────► LEAF 1 (trigger/config)
│    ├─ Queued for a long time, never picked up ─────────────────────► LEAF 2 (runner availability)
│    └─ Ran ──► B
│
├─ B. Which jobs didn't succeed? (count cancelled and timed-out jobs too)
│    ├─ Only cancelled jobs ─► did any run until its timeout, or carry a
│    │                        timeout annotation?
│    │    ├─ Yes ────────────────────────────────────────────────────► LEAF 5 (resource limit: timeout)
│    │    └─ No: fail-fast sibling, newer push, manual cancel ───────► LEAF 3 (cancel, not failure)
│    └─ At least one failed (or timed-out) job ──► C
│
├─ C. Is there real build/test output before the failure?
│    ├─ No: runner lost, setup or checkout failed, a registry/cache/
│    │       artifact service returned 429/5xx ──────────────────────► D
│    └─ Yes ──► find the FIRST real error ──► E
│
├─ D. A setup-level failure. Which fits?
│    ├─ The job starved the runner (exit 137, "Killed", memory climbing
│    │   in earlier steps, "lost communication" right after a heavy step) ► LEAF 5
│    ├─ Other repos or runs fail the same way, or the provider reports
│    │   an incident ────────────────────────────────────────────────► LEAF 4 (infrastructure)
│    └─ No incident, and it fails the same way on re-run ──► read the
│        failing setup step's own error:
│        ├─ Permission or token scope; missing action, ref or image ─► LEAF 1
│        ├─ Requested version not found; a tag or image moved ───────► LEAF 6
│        └─ Secret empty only on fork or bot PRs ────────────────────► LEAF 7
│
├─ E. Does the first error's signature already name the class?
│    ├─ OOM / exit 137 / ENOSPC / job or test timeout ───────────────► LEAF 5 (resource limit)
│    ├─ Frozen-lockfile mismatch ────────────────────────────────────► LEAF 13 (lockfile)
│    ├─ Resolver picked a new version / version not found ───────────► LEAF 6 (dependency drift)
│    ├─ Native-module ABI mismatch; outputs that don't match source ─► LEAF 14 (stale cache)
│    ├─ Config parse error / invalid workflow / missing permission ──► LEAF 1 (trigger/config)
│    ├─ Empty secret / 401/403 only on fork or bot PRs ──────────────► LEAF 7 (environment)
│    └─ An assertion, compile, or runtime error in project code ─────► F
│
├─ F. Start the one re-run now; it runs while you check the default branch.
│    Is the default branch red?
│    ├─ Yes, the same failure set, and its tests ran ────────────────► LEAF 8 (not this change)
│    ├─ Yes, and main's failure stops tests from running ────────────► LEAF 8 (own tests UNVERIFIED)
│    ├─ Yes, but this run has failures main doesn't ─► LEAF 8 for the shared ones;
│    │                                                 triage the extra ones from E
│    └─ No ──► F2. Has the base moved since the last green run, and do the
│              new base commits touch the failing code?
│              ├─ Yes ──► reproduce on the merge: fails there, passes on the tip ► LEAF 9
│              └─ No, or the merge doesn't reproduce it ──► F3. The re-run result:
│                   ├─ Passes ─────────────────────────────────────────► LEAF 10 (flaky)
│                   └─ Fails the same way: deterministic for now ──► F4. Reproduce
│                        locally with CI's exact commands
│                        ├─ Reproduces ──► F5. Did resolved dependency versions
│                        │   change since the last green run?
│                        │   ├─ Yes, and the code diff doesn't explain it ───► LEAF 6
│                        │   ├─ No change anywhere, and the last green SHA
│                        │   │   fails today too ────────────────────────────► LEAF 15 (time bomb)
│                        │   └─ Otherwise ───────────────────────────────────► LEAF 11 (regression)
│                        └─ Doesn't reproduce ──► F6. Move toward CI one variable
│                             at a time: random order, parallelism and shard, TZ,
│                             runtime version, merge commit, CPU/memory budget
│                             ├─ Reproduces under a CI condition ─────► LEAF 7 or LEAF 10
│                             ├─ Passes with a clean install, but fails on
│                             │   every CI re-run ──► bypass the cache ─► LEAF 14
│                             └─ Still not ──► check the test's history on other
│                                  runs and PRs (two failures in a row can still
│                                  be a flake), add CI diagnostics ──► back to E
│
└─ G. A green you don't trust: walk the checklist in SKILL.md step 8
     ├─ A required check never reported on the head SHA (including a
     │   renamed job or a changed matrix value) ─────────────────────► LEAF 1
     ├─ Conclusion is cancelled/skipped/neutral, or still running ───► wait, re-read the final state
     └─ Target test didn't run, test count dropped, passed only on a
        retry, or a mask hides the exit code ────────────────────────► LEAF 12 (false green)
```

## Leaves

Index: 1 trigger/config or required-check mismatch · 2 runner availability · 3 cancelled, not failed · 4 infrastructure · 5 resource limit · 6 dependency drift · 7 environment mismatch · 8 not this change · 9 stale branch · 10 flaky · 11 regression · 12 false green · 13 lockfile out of sync · 14 stale or poisoned cache · 15 time bomb.

### LEAF 1: Trigger, pipeline configuration, or required-check mismatch
- **Confirm.** Read the platform's own error first. An invalid config usually produces a run with an error annotation and zero jobs. Otherwise look for:
  - **A required check whose name no longer matches any job.** Compare the required check names in the branch protection rule or ruleset with the check names actually reported on the head SHA. A renamed job, a changed display name, or a changed matrix value (`test (3.11)` becoming `test (3.12)`) creates a new name, and the old required name waits forever.
  - **A trigger-level path filter, branch filter or skip-ci marker** keeping a required pipeline from starting.
  - **A merge queue** whose pipelines lack the queue's trigger.
  - **A run from a first-time fork contributor** waiting for a maintainer to approve it.
  - **A token missing a permission, or a missing action, ref or image** referenced by a setup step.
- **Fix.**
  - For a name mismatch, update the required-check list in the same change (that needs a repository admin and the user's go-ahead), or keep required names stable. One common way is a single aggregate job that depends on every matrix leg and is the only required check.
  - For filters, move path logic out of the trigger and into a job-level condition, so the required check still reports (your platform file shows how skipped jobs report).
  - For an approval wait, ask a maintainer to review the code and approve the run.
  - Lint the config with the platform's linter.

  Pushing another commit clears none of the name, filter or approval cases, so don't loop on it.
- **Done when** every required check reports on the head SHA.

### LEAF 2: Runner availability
- **Confirm.** Compare the requested runner label or tags with the runners that exist. A self-hosted runner may be offline, a label may be misspelled, or a concurrency limit may have been reached.
- **Fix.** Correct the label, or escalate to whoever owns the runners. Don't change the runner type just to get a green, because a different image changes the environment under test.
- **Done when** the job is picked up and runs to a conclusion.

### LEAF 3: Cancelled, not failed
- **Confirm.** Work out who cancelled the job: a newer push superseding it (a concurrency or auto-cancel setting), fail-fast cancelling matrix siblings, or a person. Check the duration first. A job whose duration reached its timeout belongs in LEAF 5, not here.
- **Fix.** If a newer run superseded it, look at the newer run instead. If fail-fast cancelled it, triage the sibling that actually failed. If a person cancelled it, find out why before re-running.
- **Done when** the run you are evaluating ran to completion.

### LEAF 4: Infrastructure
- **Confirm.** The same failure shows up across unrelated branches or repos, the provider's status page reports an incident, or the error comes from the platform rather than the project (a registry 429/5xx, failed cache service calls, runner provisioning errors).
- **Fix.** Retry, and link the evidence in the PR. If it recurs, make the pipeline sturdier. Cache dependencies, pin images, authenticate registry pulls so they get a higher rate limit, and add retry-with-backoff around network fetches in setup steps only, never around tests.
- **Done when** a run with the same SHA passes and the evidence is recorded.

### LEAF 5: Resource limit
- **Confirm.** Find which resource ran out:
  - **Memory:** exit 137, `Killed`, a heap OOM message, or the runner losing contact right after a memory-heavy step. A 137 on a step that was being cancelled or had timed out is the platform's final kill, not OOM.
  - **Disk:** `No space left on device`.
  - **Time:** a job, step, no-output or per-test timeout. A job timeout can show up as cancelled or aborted; its duration matches the configured timeout.

  Then compare that resource with the last green run. Look at test durations, build output size, the number of parallel workers, and the size of the dependency tree. A job that stops at the same point every time until the timeout is a hang, not slowness.
- **Fix.** Find what grew or what hung. Common causes are a test that leaks memory or never closes a resource, a deadlock, a process waiting on a prompt, a worker count derived from host CPUs inside a container that only has two, unbounded fixture data, or caches and build outputs piling up on disk. Make a hang fail fast with a stack trace (`failure-signatures.md` §3.9). Raise a limit only when the growth is legitimate, and show the measurement when you do.
- **Done when** the job completes with headroom you can state, for example "peak RSS 2.9 GB of 7 GB" or "38 minutes of a 60-minute limit, previously 35".

### LEAF 6: Dependency drift
- **Confirm.** Diff the resolved versions between the last green run and the red one. Look in the lockfile diff, in the install step's log output, or at the image digest. A version range, a floating Docker tag, a `*-latest` runner label or an unpinned tool installer can all move without any commit in the repo. If the resolved versions are identical and the last green SHA fails today too, go to LEAF 15.
- **Fix.** Fix the code to work with the new version, or pin the dependency explicitly with a tracking note explaining why. Enforce the lockfile in CI.
- **Done when** the build is green and the dependency set is pinned or the upgrade is deliberate.

### LEAF 7: Environment mismatch
- **Confirm.** Find the variable that differs and prove it matters by flipping it locally. Candidates:
  - **Operating system:** the OS itself, filesystem case sensitivity, line endings, the executable bit, the shell.
  - **Toolchain:** the runtime version, the package-manager version.
  - **Process environment:** locale, time zone, `CI=true`, env vars that are missing or empty.
  - **Fork and bot PRs:** secrets withheld because the run came from a fork or a dependency-update bot.
- **Fix.** Make the code or test independent of that variable, or make CI's environment explicit, for example by pinning the runtime version in a file that both local and CI setups read. For fork or bot PRs, skip the secret-dependent job and say so visibly. Don't hand secrets to code you haven't reviewed.
- **Done when** it passes in CI and you have shown it fails locally under the CI value of that variable.

### LEAF 8: Not this change
- **Confirm.** The default branch shows the same failures on its latest runs. Compare the full set of failing tests and errors (JUnit report or failure summary), not only the first error. Any failure that main doesn't have belongs to this PR: triage it from E. If main's failure stops tests from running (a build, compile, collection or setup error), this PR's own tests never ran, so they are UNVERIFIED, not passing.
- **Fix.** Find the culprit commit by checking which main run first went red. If no commit explains it, because re-running the last green main SHA fails today too, it is drift (LEAF 6) or a time bomb (LEAF 15). Check for an open fix PR or issue, and file one if there isn't any. Once the fix lands, update this branch. Don't bundle an unrelated fix into this PR unless the user asks; if you do, put it in a separate commit with its own explanation.
- **Report** "Not caused by this change" only if this PR's tests actually ran. Otherwise report "Blocked by main (own tests unverified)".
- **Done when** main is fixed and this PR is green after updating its branch, with its own tests having run.

### LEAF 9: Stale branch / merge effect
- **Confirm.** Either the PR has a merge conflict and its checks never started (check its mergeability on the platform), or merging the base into the branch reproduces the failure and the branch tip alone does not.
- **Fix.** Update the branch by merging or rebasing, following the repository's convention, then resolve conflicts and fix the interaction inside this PR, since it is now this PR's problem.
- **Done when** it is green on a run whose merge base includes current main.

### LEAF 10: Flaky
- **Confirm.** Show that the same SHA both passes and fails. Then find the category (timing, ordering, shared state, concurrency, network, time and date, or randomness) by reproducing it under that condition. The procedure is in `flaky-tests.md`. To tell whether the flake predates this PR, search CI history and the issue tracker for the test name: failures on main or on unrelated PRs before this branch existed mean it is pre-existing.
- **Decide what happens to this PR:**
  - **(a) This change introduced or worsened it**, for example a new test that shares state, a new timing dependency, or a flake in a test covering code this PR touches. Fix it in this PR.
  - **(b) Pre-existing, with a tracking issue.** Add this run's link to the issue as an occurrence. The single green re-run is then an acceptable basis to proceed.
  - **(c) Pre-existing and untracked.** File the issue first, with a named owner (template in `flaky-tests.md` §5), then proceed as in (b).

  Quarantine only under the rules in `flaky-tests.md` §5: the flake blocks others, a fix can't land promptly, and the test doesn't cover code this change touches.
- **Fix,** when fixing: remove the nondeterminism.
- **Done when** the test passes repeatedly under the condition that used to break it (many iterations, random seeds, constrained CPU), or, in (b) and (c), the occurrence is recorded on a tracked issue that has an owner.

### LEAF 11: Code or test regression
- **Confirm.** The failure is deterministic, it reproduces locally with CI's commands, and it involves behavior this change affects.
- **Fix.** Fix the code. If the behavior change was intended, update the test, explain why in the PR, and check that no other caller relied on the old behavior. Use `implementation:debug-root-cause` when the mechanism isn't obvious; if it isn't installed, test one hypothesis at a time against the reproduction.
- **Done when** the failing test passes and the rest of the suite still passes locally and in CI.

### LEAF 12: False green
- **Confirm.** Walk the checklist in SKILL.md step 8 and name the item that fails. An existing retry policy that reports flaky results to a tracked place is not itself a mask, but a test that passed only on a retry is still a flake: handle it in LEAF 10.
- **Fix.** Remove the mask and let the real result show. Then triage that result from B.
- **Done when** every required check reports success on the head SHA and the target tests ran and passed on their first attempt.

### LEAF 13: Lockfile out of sync with the manifest
- **Confirm.** CI's lockfile-enforcing install, run locally with CI's package-manager version on a clean checkout of the PR head, fails the same way. The PR touched the manifest or the lockfile, or the lockfile was written by a different package-manager version or on a different OS. Messages and causes are in `failure-signatures.md` §3.2.
- **Fix.** Regenerate the lock with the project's pinned package-manager version, change only what the manifest change requires, and commit it with the manifest. If neither file changed and the install still fails, it is drift: LEAF 6.
- **Done when** the frozen install passes in CI and the lockfile diff matches the manifest change.

### LEAF 14: Stale or poisoned cache
- **Confirm.** Bypass the cache by changing its key or deleting the entry (your platform file shows how), re-run, and see the failure disappear.
- **Fix.** Put the runtime version, OS and architecture, and the lockfile hash, into the cache key, and stop caching build outputs that aren't keyed by their inputs (`failure-signatures.md` §3.7).
- **Done when** a run with the corrected key passes, and a later run that restores the new cache passes too.

### LEAF 15: Time bomb
- **Confirm.** The last green SHA fails today with identical dependencies, and pinning the clock to an earlier date makes it pass. Look for literal dates in fixtures and tests, and expired certificates or tokens (`failure-signatures.md` §3.6).
- **Fix.** Inject a clock, or generate certificates, tokens and dates at test time relative to "now".
- **Done when** the test passes with the clock pinned on both sides of the date that triggered it, and no fixed expiry is left in the fixtures.
