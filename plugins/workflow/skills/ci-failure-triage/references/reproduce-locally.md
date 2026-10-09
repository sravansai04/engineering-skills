# Reproducing a CI Failure Locally

A local reproduction counts only if it runs what CI ran: the same code, the same toolchain, the same install, the same environment, and the same command. When "it passes locally", one of those five differs. This file shows how to find which one. Platform-specific details (where the tested SHAs appear in the log, fetching fork PRs, running jobs locally) are in the platform files: `github-actions.md`, `gitlab-ci.md`, `jenkins-and-others.md`.

## Contents

1. Extract the environment from the CI config
2. Check out exactly what CI tested
3. Install the way CI installs (lockfile enforcement and caches)
4. Match the runtime, OS and architecture
5. Match environment variables, selection, sharding and resources
6. Run CI jobs locally
7. When it still won't reproduce

## 1. Extract the environment from the CI config

Read the failing job's definition, along with every file it includes or extends. Note each item below.

| What | Where to look (GitHub Actions / GitLab CI / Jenkins) |
|---|---|
| OS / image | `runs-on`, `container:` / `image:` / `agent { docker { image ... } }` |
| Language and tool versions | setup-step inputs (for example `node-version`, `python-version`, `java-version`, `go-version`); version files the setup reads (`.nvmrc`, `.node-version`, `.python-version`, `.tool-versions`, the `go`/`toolchain` directive in `go.mod`, `rust-toolchain.toml`, `global.json`, the Maven/Gradle wrapper properties) |
| Services | `services:` (database and cache versions, health checks, ports) |
| Env vars | `env:` at workflow, job and step level / `variables:` / `environment {}`. Also repository- or org-level variables in the CI settings. |
| Matrix | `strategy.matrix` / `parallel: matrix:`. Note the values for the failing leg. |
| Install command | The step that installs dependencies, and any cache-restore step before it, with its cache key |
| Test command | The exact command, its flags, and its working directory (`working-directory`, `cd`) |
| Shell | `defaults.run.shell` / `shell:` / the `sh` step's defaults. This decides `-e`, `pipefail` and, on Windows, PowerShell's exit-code behavior. |

The setup steps in the CI log usually print the versions they actually resolved, such as "Node 20.x" resolving to a specific patch release. Prefer what the log printed over what the config requested.

## 2. Check out exactly what CI tested

- **Use a clean tree.** Work in a separate worktree or a fresh clone, never the working copy you develop in. Generated files, ignored build output and local config that CI doesn't have are the classic cause of "works on my machine". `git status --ignored` shows what your normal checkout has that a fresh one wouldn't.
- **Get the exact SHAs from the run, not from the branch.** For a PR run that tests a merge, you need both the head SHA and the base SHA that CI merged. The branch tip and today's base may both have moved since. Each platform file says where those SHAs appear. For PRs from forks, the head commit isn't on your remote's branches, so fetch it by PR ref as the platform file shows. Running a fork PR's code locally is running an untrusted author's code: apply the trust gate in SKILL.md step 6 first.
- **Rebuild the merge in a detached scratch worktree, then remove it.** Detached worktrees don't create branches, so a second triage doesn't collide with the first:
  ```bash
  git fetch origin
  dir="$(mktemp -d)/ci-triage"                        # fresh path: no collision with another session or a stale tree
  git worktree add --detach "$dir" <head-sha> && echo "$dir"
  git -C "$dir" merge --no-edit <base-sha>            # skip this line if CI tested the head alone
  # ...reproduce in that directory...
  git worktree remove --force "$dir"                  # removes only the scratch tree
  ```
  Shell variables don't survive between separate commands, so use the printed path literally in later ones. For where to keep worktrees, their setup and safe cleanup, see `workflow:git-worktrees`.

## 3. Install the way CI installs

CI usually installs with a command that fails if the lockfile and the manifest disagree, while developers often run the forgiving variant. Use the CI form:

| Ecosystem | Lockfile-respecting install | Notes |
|---|---|---|
| npm | `npm ci` | Deletes `node_modules` and fails if `package.json` and `package-lock.json` are out of sync. |
| pnpm | `pnpm install --frozen-lockfile` | This is already the default in CI environments. |
| Yarn 1 | `yarn install --frozen-lockfile` | |
| Yarn 2+ | `yarn install --immutable` | |
| uv | `uv sync --locked` | Fails if `uv.lock` would change. |
| Poetry | `poetry check --lock`, then `poetry install` | |
| pip | `pip install -r requirements.txt` with exact pins (`==`), ideally with `--require-hashes` | An unpinned requirements file is itself a drift risk. |
| Bundler | `bundle config set frozen true`, then `bundle install` | |
| Go | `go mod download`; detect drift with `go mod tidy && git diff --exit-code go.mod go.sum` | `go mod verify` checks the module cache against `go.sum`. |
| Cargo | `cargo build --locked` / `cargo test --locked` | |
| .NET | `dotnet restore --locked-mode` | Requires a committed `packages.lock.json`. |
| Maven / Gradle | Use the wrapper (`./mvnw`, `./gradlew`) so you get the pinned build-tool version | Dynamic versions (`1.+`, version ranges, `-SNAPSHOT`) float unless dependency locking is enabled. |

**Use the package-manager version CI used,** not whatever is on your machine. Check the `packageManager` field in `package.json` (used by Corepack), `.tool-versions`, the setup step's inputs, or the version CI printed. A lockfile written by a different major version of the package manager is a common source of "out of sync" errors.

**Test with and without CI's cache.** If CI restores a dependency or build cache, a clean local install is the "no cache" case. If the clean install passes and CI fails on every re-run, suspect the cache before anything else: see `failure-signatures.md` §3.7.

## 4. Match the runtime, OS and architecture

- **Install the exact version the CI log printed**, using the project's version manager or a container image.
- **Run inside a container when CI does.** If CI runs on x86-64 and your machine is ARM (Apple Silicon, ARM Linux), add `--platform linux/amd64`; otherwise you test a different architecture and miss failures in native extensions, binary downloads and floating-point edge cases:
  ```bash
  docker run --rm -it --platform linux/amd64 -v "$PWD":/work -w /work <ci-image> bash
  ```
- **Hosted VM runners aren't containers.** A container of the same OS release gets close, but its preinstalled tools differ, so treat any remaining difference as a suspect.
- **macOS and Windows filesystems are case-insensitive by default**, and Linux is case-sensitive. Windows may also check files out with CRLF line endings, depending on your git settings.

## 5. Match environment variables, selection, sharding and resources

- **Environment.** Set at least `CI=true`, plus every variable from the job's `env:`. Also match `TZ` and the locale (`LANG`, `LC_ALL`) to what the runner uses: check the log or add a diagnostic step, and don't assume. Many tools change behavior under `CI=true`. Jest's CI mode, for example, fails on a missing snapshot instead of writing one.
- **Selection and order.** Use the same test paths, markers, tags and filters. If CI shards the suite (for example `jest --shard=2/4` or a timing-based splitter), run the same shard. Order and shared-state bugs depend on which tests share the process.
- **Parallelism.** Use the same worker count. Many runners default to "number of CPUs", which differs between your laptop and the runner.
- **Seed.** If the runner randomizes order, use the seed printed in the CI log.
- **Resources.** Constrain the container to the runner's size, using the provider's documented runner specs:
  ```bash
  docker run --rm -it --platform linux/amd64 --cpus=2 --memory=7g -v "$PWD":/work -w /work <ci-image> bash
  ```
  Timing flakes and out-of-memory failures often only appear under these limits.

## 6. Run CI jobs locally

Some platforms have tools that run a job definition on your machine (the platform files list them). Their default images and platform features differ from the hosted runners, so a local pass is weaker evidence than a CI pass. Use them for fast iteration, and confirm in CI. When no such tool fits, run the job's container image yourself and execute its script lines in order.

## 7. When it still won't reproduce

Stop guessing, and collect data from CI. Each of these is visible to others or uses shared CI capacity, so get the user's go-ahead first.

1. **Re-run with debug logging.** Each platform file shows how. Debug modes can print more than usual; check what they expose before enabling them on a public project.
2. **Push a diagnostic commit to a separate scratch branch or draft PR, never to the PR branch.** That way nothing needs to be dropped or force-pushed later. If the workflow only runs for PRs, open the scratch branch as a draft PR. Make it print tool versions, `df -h`, `free -m` or `ulimit -a`, the number of CPUs, the locale and time zone, and selected env vars (`printenv | grep -E '^(CI|TZ|LANG|LC_)' | sort`). Never dump the whole environment, since it can contain secrets. Close the scratch PR and delete the branch when done.
3. **Upload artifacts on failure**: test reports, application logs, screenshots, thread dumps, core dumps. Then download and inspect them.
4. **Change one variable at a time** toward CI's values, and note which change first reproduces the failure. That variable is your cause, or points straight at it.
