# Environment-Only Bugs

Read this when the same code behaves differently in different places: "works on my
machine", passes locally but fails in CI, or works in staging but fails in production
(or on one host, region, browser, or customer and not others).

## Contents
1. The method: diff, then converge
2. What can differ (checklist)
3. Capture a fingerprint on each side
4. Reproduce the failing environment locally
5. CI-only failures
6. Safety while debugging live environments

---

## 1. The method: diff, then converge

If the code is the same and the behavior differs, something else differs. Don't
guess which thing. Instead:

1. **Prove the code really is the same.** Compare the commit SHA, build ID, image
   digest, or artifact checksum on both sides. A surprising number of
   environment-only bugs turn out to be a different build: stale deploy, cached
   asset, wrong branch, unapplied migration.
2. **List every difference** using the checklist below, and capture fingerprints from
   both sides (section 3).
3. **Converge one variable at a time.** Make the working environment more like the
   failing one (or the reverse), one difference per step, until the behavior flips.
   This is bisection over configuration instead of commits. Change the cheapest and
   most likely differences first.
4. **When it flips, you have the trigger, not yet the root cause.** Continue with the
   main workflow: why does that variable change behavior? The answer is often an
   implicit assumption in the code, like a default locale, a case-insensitive file
   system, an unbounded timeout, or an unset variable that falls back silently.

## 2. What can differ (checklist)

| Area | Things to compare |
|---|---|
| Build | Commit, build flags, debug vs release, minification and tree-shaking, generated code, compile-time feature flags, stale artifacts or caches |
| Runtime | Language runtime version, OS and version, C library (glibc vs musl), CPU architecture (x86_64 vs arm64), container base image |
| Dependencies | Whether the lockfile is honored, transitive versions, native extensions, optional dependencies present on only one side |
| Configuration | Environment variables, config files, secrets, feature flags, defaults that apply when a value is unset, precedence between sources |
| Data | Volume, shape, nulls, encoding and Unicode, legacy rows, special characters, permissions on records, cache contents |
| Time and locale | Time zone, DST, locale (number, date, and sort formats), system clock accuracy, clock skew between hosts |
| Resources | Memory and CPU limits (container or cgroup), file descriptor limits, disk space and inodes, temp directory, thread and connection pool sizes. Pools and worker counts sized from the visible core count can far exceed a container's CPU quota, causing throttling and timeouts only where the quota applies |
| Network | DNS, proxies, TLS CA bundles and certificate expiry, firewalls, IPv4 vs IPv6, latency (timeouts that only trip far away), MTU |
| Scale and concurrency | Number of cores, replicas, load balancer behavior (sticky sessions), concurrent users, queue depth |
| File system | Case sensitivity (macOS and Windows defaults vs Linux), path separators, line endings (CRLF vs LF), permissions, symlinks, read-only mounts |
| Identity and permissions | OS user, service account, cloud or IAM role, security policies such as SELinux or AppArmor |
| Integrations | Sandbox vs live third-party endpoints, API versions, rate limits, webhooks that only reach some environments |
| Clients | Browser and version, extensions, cached assets and service workers, cookies, content security policy, device and screen size |
| Lifecycle state | Warm vs cold caches, migrations applied, startup order, long uptime (leaks, counters, token expiry) |

## 3. Capture a fingerprint on each side

Collect the same facts from the working and the failing environment, save each to a
file, and diff them. Run only what applies to the stack. Redact secrets before sharing
or saving anything.

```bash
# Platform
uname -a
cat /etc/os-release            # Linux
sw_vers                        # macOS
nproc 2>/dev/null || sysctl -n hw.ncpu
ulimit -a
date; date -u; echo "TZ=${TZ:-unset}"
locale

# Runtime version (pick the relevant ones)
node --version; python -VV; java -version; go version; rustc -Vv; dotnet --info; ruby -v

# Resolved dependency set
pip freeze                     # or: poetry show / uv pip freeze
npm ls --all                   # or the pnpm / yarn equivalent
go list -m all
cargo tree
mvn dependency:tree            # or: gradle dependencies
bundle list

# Environment variables, names only (values can be secrets)
env | cut -d= -f1 | sort

# Container limits, if inside a container. nproc counts the CPUs a process may run
# on, not its CPU quota, so read the quota too.
cat /sys/fs/cgroup/memory.max 2>/dev/null          # cgroup v2 memory limit
cat /sys/fs/cgroup/cpu.max 2>/dev/null             # cgroup v2: "QUOTA PERIOD", or "max PERIOD" for no limit
cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us 2>/dev/null  # cgroup v1 equivalent (-1 means no limit)
```

Then compare: `diff working.txt failing.txt`. Compare environment variable *values*
separately, and only for the variables the failing code path actually reads.

Ask the application too. Many frameworks can print their effective configuration,
which shows what was actually used after defaults and overrides were applied.
Prefer that over reading config files.

## 4. Reproduce the failing environment locally

- Run the exact artifact that fails: the same container image by digest, the same
  package version, the same build flags.
- Recreate its limits and settings, for example
  `docker run --rm -it --memory=512m --cpus=1 -e TZ=America/New_York IMAGE CMD`.
- Replay the exact failing input: the same request with headers and body, the same
  file, the same message payload. Capture it from logs or traces where policy allows.
- Use a representative data sample. Production-shaped data (sizes, nulls, odd
  characters, old records) triggers bugs that tidy fixtures never do. Use anonymized
  or synthetic data with the same shape rather than copying personal data onto a
  laptop.

## 5. CI-only failures

CI environments differ from developer machines in predictable ways. Check these first:

- Clean checkout: no untracked files, no local caches, no locally generated config. A
  file that exists only on your machine (or is ignored by version control) is a
  common culprit.
- Different parallelism, test sharding, and test order.
- Time zone is often UTC. Locale is often minimal (`C` or `POSIX`).
- No TTY, no display, no interactive prompts; different user and home directory.
- Tighter CPU and memory limits, slower disks, shared runners with noisy neighbors.
- Cached dependency layers that can be stale in their own way.

Reproduce by running the CI job's own container image and commands locally. For
pipeline mechanics, such as which job failed, cache problems, and runner
infrastructure, use the `workflow:ci-failure-triage` skill if it is installed;
otherwise work through this list and the job's own log. Return here once the failure
is known to be a real defect in the code or the tests.

## 6. Safety while debugging live environments

- Observe before you change. Logs, metrics, traces, and read-only queries come first.
- Don't attach a pausing debugger or add heavy logging to a production process that
  serves real traffic. Prefer sampling profilers, dumps taken on a signal, and
  temporary logging behind a flag that targets a single test account or request.
- Never paste secrets, tokens, or personal data into tickets, chats, or commits while
  sharing evidence.
- Record every change you make in a shared environment, so you can revert it and
  explain it later.
