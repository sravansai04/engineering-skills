# Failure Signatures

This file maps a first error to a likely class, then says what fixes that class and what only hides it. A signature is evidence, not a verdict. Confirm the class with the check listed for it before you fix anything.

False greens are not here: the checklist is SKILL.md step 8, and each platform's specific causes are in its platform file.

## Contents

1. Exit codes
2. Finding the first error in common ecosystems
3. Signatures by class
   - 3.1 Code or test regression
   - 3.2 Lockfile out of sync with the manifest
   - 3.3 Flaky test
   - 3.4 Infrastructure or runner
   - 3.5 Dependency drift
   - 3.6 Time bomb
   - 3.7 Stale or poisoned cache
   - 3.8 Environment mismatch
   - 3.9 Resource limits
   - 3.10 Stale branch / merge effect
   - 3.11 Pipeline configuration

## 1. Exit codes

On POSIX shells, a process killed by signal N exits with status 128+N.

| Code | Usual meaning | Notes |
|---|---|---|
| 1 | Generic failure | Most test runners use it for "tests failed". Find the error in the log. |
| 2 | Misuse or usage error; `make` target failed | `make` returns 2 when any recipe fails. The real error is above it. pytest uses 2 for "interrupted". |
| 4, 5 | pytest: usage error (4), no tests collected (5) | Exit 5 means a selection or glob matched nothing. Check whether CI swallows it. |
| 124 | GNU `timeout` killed the command | A wrapper timeout, not the CI job timeout. |
| 126 | Found but not executable | The script's executable bit is missing. See section 3.8. |
| 127 | Command not found | A tool isn't installed, or isn't on `PATH`, in this image. |
| 130 | SIGINT | Rare from a person in CI, but common from the platform: several CI systems stop a cancelled or timed-out step with SIGINT first, then SIGTERM, then SIGKILL (GitHub Actions' exact sequence is in `github-actions.md`). So 130, 143 or 137 on a cancelled step means a cancel or timeout, not a crash or OOM. Check the job's duration against its timeout before blaming memory. |
| 134 | SIGABRT | A native abort. Usually an assertion in C/C++ code or a runtime abort. |
| 137 | SIGKILL | Most often the out-of-memory killer, unless the step was being cancelled or had timed out, in which case it is the platform's final kill (see 130). |
| 139 | SIGSEGV | A segfault in native code: native extensions, a mismatched binary architecture, stack exhaustion. |
| 143 | SIGTERM | A graceful stop: a cancel, a timeout, or the runner shutting down. |

## 2. Finding the first error in common ecosystems

Search for these markers from the top of the failing step, and take the earliest one that belongs to the failure.

| Ecosystem | Markers worth searching for | Where the real cause usually is |
|---|---|---|
| Python / pytest | `ERROR collecting`, `Traceback (most recent call last)`, lines starting `E   `, `short test summary info` | A collection error stops every test in that module, so fix collection errors first. The summary at the end lists the failing tests. The cause is in the first `E` block. |
| JavaScript / TypeScript | `error TS` followed by a number, `●` (Jest failure marker), `npm ERR!` or `npm error`, `ERR_PNPM_`, `YN0` codes (Yarn) | Type errors at build time come before any test runs. For install errors, read the first resolver line, not the generic "exit handler" line. |
| Go | `--- FAIL:`, `panic:`, `FAIL` followed by a package path, `file.go:LINE:COL:` (build errors) | A panic in one test aborts the whole package binary. The output after the panic belongs to the panic. |
| JVM (Maven / Gradle) | `[ERROR]`, `* What went wrong:`, `Tests run:` followed by `Failures:`, `Caused by:` | The deepest `Caused by:` in a stack trace is usually the root cause. Surefire and Gradle write per-test reports to `target/surefire-reports` and `build/reports/tests` respectively, if CI uploads them. |
| Rust | `error[E` followed by a code, `thread '...' panicked at`, `test result: FAILED` | Compile errors print in order, so the first one usually causes the later ones. |
| Ruby / RSpec | `Failures:`, `rspec ./spec/...:LINE` | RSpec prints a re-run line for each failing example. Run the first one. |
| .NET | `error CS` followed by a number, `Failed ` (test line), `Total tests:` | Build errors come before test output. |
| Docker builds | `ERROR [`, `failed to solve:` | The failing build stage and command are named on the `ERROR [` line. |
| Shell | `command not found`, `No such file or directory`, `Permission denied`, `unbound variable` | With `set -e`, the first failing command ends the step. Without it, the step fails on a later symptom, or not at all. In PowerShell, a failing native command doesn't stop the script, and only the last native command's exit code decides the step. |

## 3. Signatures by class

Each class lists the signatures that point to it, a check that confirms it, the real fix, and the moves that only hide it.

### 3.1 Code or test regression
- **Signatures.** An assertion mismatch, a type or compile error, or an exception thrown from code the change touched. The failure is identical on re-run and on every runner in the matrix.
- **Confirm.** It reproduces locally with CI's commands, and the stack trace or assertion points into the diff, or into code the diff calls.
- **Fix.** Change the code. If the old expectation is now wrong because the behavior change is intended, update the test, say so in the PR, and look for other callers that relied on the old behavior.
- **Hiding it.** Loosening the assertion until it passes, updating snapshots or golden files without reading the diff, or marking the test skipped.

### 3.2 Lockfile out of sync with the manifest
This is usually caused by the change under test, not by drift.
- **Signatures.** The lockfile-enforcing install fails before any test runs. Greppable messages:
  - **npm:** `can only install packages when your package.json and package-lock.json` (followed by `Missing:` / `Invalid:` lines naming the packages).
  - **pnpm:** `ERR_PNPM_OUTDATED_LOCKFILE`.
  - **Yarn (Berry):** `YN0028` (the lockfile would have been modified).
  - **Cargo:** `Cargo.lock needs to be updated but --locked was passed`.
  - **Go:** `missing go.sum entry` or `updates to go.mod needed`.
  - **Poetry 2.x:** `pyproject.toml changed significantly since poetry.lock was last generated`. Poetry 1.x printed `poetry.lock is not consistent with pyproject.toml`.
- **Common causes.** The manifest was edited without re-locking. The lockfile was written by a different major version of the package manager. Or it was generated on another OS and dropped platform-specific optional dependencies, for example a missing native binary package for `linux-x64` when the lock was made on macOS.
- **Confirm.** Run CI's install command locally with CI's package-manager version, on a clean checkout of the PR head. Check whether the PR touched the manifest.
- **Fix.** Regenerate the lock with the project's pinned package-manager version (the `packageManager` field used by Corepack, `.tool-versions`, or the version CI printed). Change only what the manifest change requires, and commit the lockfile with the manifest. If the files are untouched and the install still fails, it is drift: see 3.5.
- **Hiding it.** Switching CI to the forgiving install (`npm install`, no `--frozen-lockfile`), or deleting and regenerating the whole lockfile, which upgrades everything at once.

### 3.3 Flaky test
- **Signatures.** The same SHA passes and fails. The failure involves timeouts, `sleep`, ordering, a port already in use, `connection refused` during startup, dates, or random data. It fails on unrelated PRs, and only one leg of the matrix fails, and a different leg each time.
- **Confirm.** Reproduce it under the suspected condition: repeated runs, random order with a fixed seed, constrained CPU, a different time zone. See `flaky-tests.md`.
- **Fix.** Remove the nondeterminism.
- **Hiding it.** Repeated re-runs, adding or raising automatic retries to get a PR through, or bigger sleeps. An existing retry policy that reports flaky results to a tracked place is a detector; retries added silently are a mask.

### 3.4 Infrastructure or runner
- **Signatures:**
  - **Runner problems.** The runner received a shutdown signal, lost communication with the server, or failed to provision.
  - **Network services.** Registry rate limits (Docker Hub's `toomanyrequests`), HTTP 5xx from package registries or artifact/cache services, or DNS resolution failures for public hosts.
  - **No output.** The job died before any project command ran, and a re-run gets past the same point.
- **Confirm.** Check the CI provider's status page, and see whether the same error appears across unrelated repos or branches at the same time. Be careful with "lost communication": the job's own memory or CPU starvation can cause it, so check what the previous step was doing (see 3.9). A setup failure that repeats identically on re-run is usually not infrastructure: see the tree's node D.
- **Fix.** Retry and link the evidence. If it recurs, harden the pipeline: authenticate registry pulls, cache dependencies, mirror critical images, and retry network fetches with backoff during setup.
- **Hiding it.** Putting retries around the test command itself, which also retries real failures.

### 3.5 Dependency drift
- **Signatures.** Nothing changed in the repo between the green run and the red one, or only unrelated files did, yet a resolver picked a newer version. A new deprecation or API error appears from a library. The install step logs a version you didn't expect.
- **Confirm.** Diff the resolved versions between the two runs, using the install logs, lockfile history or image digests. Check for floating inputs: version ranges with no lockfile, `latest` or major-only image tags, `*-latest` runner labels (they move to new OS releases and new preinstalled tool defaults), tool installers that fetch "the current version", and actions or plugins pinned to a moving tag.
- **Fix.** Adapt the code to the new version, or pin deliberately with a comment and a follow-up to unpin. Enforce the lockfile in CI.
- **Hiding it.** Deleting and regenerating the entire lockfile, or pinning a version with no note about why.

### 3.6 Time bomb
- **Signatures.** A deterministic failure that starts on a particular date with no code or dependency change anywhere. It fails everywhere, main included. Typical causes: an expired test certificate or token, a hard-coded "future" date that has now passed, an age or expiry computed from a fixed date, a year or epoch rollover.
- **Confirm.** Re-running the last green SHA today also fails, and the resolved dependencies are identical to that green run. Grep fixtures and tests for literal dates and years, and check certificate expiry (`openssl x509 -enddate -noout -in <cert>`). Pinning the clock to a date before the failure started should make it pass.
- **Fix.** Inject a clock and pin it in tests, or generate certificates, tokens and dates at test time relative to "now".
- **Hiding it.** Bumping the hard-coded date or regenerating the certificate with another fixed expiry, which re-arms the same bomb.

### 3.7 Stale or poisoned cache
- **Signatures.** The failure starts on a run that restored a cache (a cache hit), and repeats on every re-run, because the same key restores the same content. It passes locally with a clean install. Main can be green, because many platforms scope caches per branch or PR. Typical messages: native-module ABI or version errors (`NODE_MODULE_VERSION`, `was compiled against a different Node.js version`, an `.so` built for another Python), "module not found" for something the lockfile does include, or build or generated output that doesn't match the source.
- **Common causes.** A dependency or build cache keyed without the runtime version, the OS or the architecture. A key that doesn't hash the lockfile. Generated code cached without its inputs in the key. A remote build cache (Gradle, Bazel, Turborepo, Nx and similar) serving bad artifacts.
- **Confirm.** Re-run with the cache bypassed: change the key (for example add a version suffix) or delete the cache entry (the platform files show how), and see whether the failure disappears.
- **Fix.** Put the runtime version, OS and architecture, and the lockfile hash, into the cache key. Never cache build outputs that aren't keyed by their inputs.
- **Hiding it.** Turning caching off permanently without finding the bad key, or deleting the entry every time it recurs.

### 3.8 Environment mismatch
Each signature below comes with its cause.

- **`Cannot find module './Button'` on Linux when the file is `button.tsx`.** The filesystem's case sensitivity differs: macOS and Windows defaults are case-insensitive, Linux is case-sensitive.
- **`/bin/bash^M: bad interpreter`.** The script was committed with CRLF line endings. Fix it with `.gitattributes` (`*.sh text eol=lf`).
- **`Permission denied` running a script, or exit 126.** The executable bit isn't committed. Fix it with `git update-index --chmod=+x path/to/script.sh`.
- **The test passes locally and fails in CI, and its expected value contains a date, a sort order, a decimal separator or a currency format.** The time zone or locale differs. Hosted CI runners commonly default to UTC, so check the runner's actual settings in the log.
- **A secret-backed step fails only on PRs from forks or from a dependency-update bot (empty token, 401/403, "Resource not accessible by integration").** Many platforms withhold repository secrets from fork PRs and hand them a read-only token. Some, GitHub among them, also run bot-authored dependency PRs with a separate, smaller secret set and a read-only token. The platform files give the exact rules.
- **Behavior differs only in CI around snapshots, prompts or colors.** The tool detects `CI=true` and changes its behavior. For example, Jest in CI mode fails on a missing snapshot instead of writing it.
- **A different runtime version is printed in the setup step.** The version file, such as `.nvmrc`, `.python-version`, `.tool-versions` or the `go`/`toolchain` directive in `go.mod`, isn't read by both the local and the CI setup.

To confirm any of these, flip that one variable locally and watch the result change. To fix it, make the code independent of the variable, or make the environment explicit in a file that both local and CI setups read.

### 3.9 Resource limits
- **Signatures:**
  - **Memory:**
    - Exit 137 or `Killed` (on a step that wasn't being cancelled; see section 1).
    - `JavaScript heap out of memory` (Node.js).
    - `java.lang.OutOfMemoryError` (JVM).
    - `fatal error: runtime: out of memory` (Go).
    - Python's `MemoryError`.
    - The Gradle daemon disappearing unexpectedly.
  - **Disk:** `No space left on device` (ENOSPC).
  - **Time:**
    - A job that hit its timeout. Some platforms report this as cancelled or aborted, not failed, so compare the duration with the configured timeout.
    - A step that printed nothing for too long, on platforms with a no-output timeout.
    - Per-test timeouts such as Go's `panic: test timed out after`, Jest's `Exceeded timeout of`, or a pytest-timeout failure.
    - Durations climbing steadily over recent runs.
- **Confirm.** Compare the job's duration and peak memory with the last green run, along with test counts, fixture sizes and worker counts. A common hidden cause is a worker count derived from the host's CPU count inside a container that is limited to fewer CPUs. A job that sits at the same point until the timeout is a hang, not slowness: make it fail fast with a stack, using a per-test timeout (`go test -timeout`, pytest-timeout, Jest's `testTimeout`) or a thread dump (`jstack`, `py-spy dump`, SIGQUIT for a Go binary).
- **Fix.** Find what grew or what hung: a memory leak, an unclosed resource, a deadlock, a test waiting on a prompt or an unclosed handle, a quadratic loop over growing fixtures, too many parallel workers, or build output piling up on disk. Raise a limit only to cover growth you have measured and judged legitimate.
- **Hiding it.** Raising every timeout, or giving the runner more memory, without knowing why the usage grew.

### 3.10 Stale branch / merge effect
- **Signatures.** It passes on the branch tip locally and fails in CI on a PR. The failure involves a symbol, migration, config key or test fixture that changed on the base branch. Or the PR has a merge conflict and checks never started.
- **Confirm.** Check whether the base moved since the last green run and whether the new base commits touch the failing code. Then merge the base into a scratch worktree and reproduce there (`reproduce-locally.md` §2). For "never started", check the PR's mergeability on the platform.
- **Fix.** Update the branch, then resolve the interaction in this PR.
- **Hiding it.** Repeatedly re-running the old run, which keeps testing the same stale merge.

### 3.11 Pipeline configuration
- **Signatures.** A YAML parse error, an "invalid workflow file" annotation, a job that is never scheduled, a reference to a missing step output or an undefined variable, a permissions error on a same-repo PR because the token's permissions are too narrow, a trigger filter that excludes the files that changed, or a required check whose name no longer matches any job.
- **Confirm.** Read the platform's error, and lint the config with the platform's linter (the platform files name it).
- **Fix.** Correct the config. Grant the narrowest token permission that the step actually needs.
- **Hiding it.** Granting broad write permissions to make an error go away, or removing a check from the required list instead of fixing why it doesn't report.
