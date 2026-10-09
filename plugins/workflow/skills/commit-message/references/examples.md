# Commit Message Examples

These examples calibrate the rules in SKILL.md. They use Conventional Commits. In a repo with a
different house style, keep the substance and change only the header shape.

## Contents

1. Subject lines: bad, then better
2. Full messages by situation
3. Turning a messy tree into a commit plan
4. Critiquing a message

---

## 1. Subject lines: bad, then better

| Bad | Problem | Better |
|---|---|---|
| `fix bug` | No type format, no area, no behavior named | `fix(auth): reject refresh tokens after password reset` |
| `Fixed the login issue.` | Past tense, vague, trailing period | `fix(login): keep the return URL across the SSO redirect` |
| `feat: updates` | Says nothing | `feat(export): add CSV download to the orders table` |
| `refactor: changed UserService.java, UserRepo.java, UserDto.java` | A file list, not a change | `refactor(users): move persistence out of UserService` |
| `chore: fix null pointer in parser` | Wrong type: users saw a crash | `fix(parser): handle empty input without crashing` |
| `feat(api): remove v1 endpoints` | A breaking change with no marker | `feat(api)!: remove the v1 endpoints` |
| `perf: speed up search` | No mechanism, no scale | `perf(search): index lowercase titles to avoid a full scan` |
| `WIP` / `more changes` / `address review comments` | Placeholders that became permanent | Name what the commit actually does |
| `fix(payments): handle the case where the gateway returns a timeout but the charge actually succeeded on their side` | Over 72 characters; the detail belongs in the body | `fix(payments): reconcile charges after gateway timeouts` |
| `PROJ-881` | A ticket key alone; the reason lives in another system | `fix(sync): retry 409 conflicts once before failing` with `Refs: PROJ-881` |

## 2. Full messages by situation

### Bug fix with a non-obvious cause (Go)

```text
fix(cache): stop serving entries past their TTL under clock skew

Nodes compared expiry against their local wall clock, so a node running
a few seconds behind kept serving entries the writer had already
expired. Store expiry as a duration from a monotonic read at insert time
instead of an absolute timestamp.

Entries written before this change keep the old format and expire on
the old rule; they age out within one TTL window.

Fixes #1307
```

The body explains the mechanism, the approach, and how the rollout behaves. It doesn't mention
which functions changed, because the diff shows that.

### Feature (TypeScript)

```text
feat(orders): let admins export the filtered table as CSV

Support asked for this weekly. Admins were copying rows by hand to
reconcile refunds. The export applies the current filters and column
order, streams rows rather than building the file in memory, and caps
at 100k rows with a message suggesting a narrower filter.

Refs: #842
```

### Pure refactor that prepares a fix (Python)

```text
refactor(billing): extract proration into its own function

No behavior change. Isolating the calculation lets the next commit
change where proration starts without touching invoice assembly, and
makes the rule testable on its own.
```

A refactor body should say that behavior is unchanged. Reviewers then know to check for exactly
that, and nothing more.

### Performance, with evidence (SQL / any backend)

```text
perf(reports): add a composite index for the daily revenue query

The dashboard query filtered on (account_id, created_at) but only
account_id was indexed, so large accounts scanned every row. On a copy
of production data the p95 drops from 2.4s to 40ms. The index adds
about 3% to the orders table's write time in the same benchmark.
```

Include numbers when you have them, and say what was measured and where.

### Breaking change (library, any language)

```text
feat(client)!: time out requests after 30s by default

The client used to wait indefinitely when no timeout was passed, which
hung worker pools when an upstream stalled. Requests now default to a
30s timeout.

BREAKING CHANGE: calls that relied on waiting indefinitely now raise a
timeout error after 30s. Pass timeout=None to restore the old behavior
for a specific call.
```

### Dependency bump with a security reason (Java / any)

```text
fix(deps): upgrade the XML parser to 2.14.1

The parser's published advisory covers an entity-expansion attack, and
the import endpoint parses uploaded files with it. No API changes in
this release; the full test suite passes unchanged.

Refs: CVE-YYYY-NNNNN
```

Cite the advisory's real identifier (CVE or GHSA) so the fix can be found by searching for it.
Naming the affected endpoint is acceptable here because the advisory is already public. For an
undisclosed flaw in your own code, keep the message neutral instead (message-format.md,
section "Security fixes").

### Routine dependency bump

```text
build(deps): bump the test runner to 3.2.0
```

A subject alone is fine when there's nothing to explain.

### Formatting-only commit

```text
style: apply prettier across the repository

Mechanical change produced by `npx prettier --write .` with prettier
3.3.3, the version pinned in package-lock.json. No hand edits. Add this
commit to .git-blame-ignore-revs after it lands.
```

Naming the exact command and version lets a reviewer reproduce the commit and confirm it holds
nothing else.

### Infrastructure / config (Terraform, YAML, etc.)

```text
fix(infra): raise the queue visibility timeout above the job runtime

Jobs take up to 4 minutes, but messages became visible again after 2,
so long jobs ran twice. Set the timeout to 6 minutes to leave headroom
for retries.
```

The change lives in a config file, but it's typed `fix` because it corrects behavior.

### CI change

```text
ci: cache the dependency directory between pipeline runs

Cuts the install step from about 3 minutes to 20 seconds on a warm
cache. The cache key includes the lockfile hash, so dependency changes
still trigger a clean install.
```

### Revert

```text
revert: add a composite index for the daily revenue query

This reverts commit 9c41e0be7a2d5f3c8b16e4a9d0f27c3b5e8a1d64.

Building the index on the largest shard held a lock long enough to
time out checkout requests. We'll reland it with a concurrent index
build in a migration.

Refs: 9c41e0b
```

### Pair-programmed commit

```text
fix(upload): resume multipart uploads after token refresh

The upload loop captured the auth header once, so parts sent after a
token refresh were rejected and the upload restarted from zero. Read
the header per part.

Co-authored-by: Priya Raman <priya@example.com>
```

## 3. Turning a messy tree into a commit plan

`git status --short` shows:

```text
 M src/api/handlers.rb        # renamed a helper + fixed nil check + reformatted
 M src/api/serializers.rb     # renamed helper call site
 M spec/api/handlers_spec.rb  # new test for the nil check
 M Gemfile                    # added a gem for the new export feature
 M Gemfile.lock
?? src/api/export.rb          # new feature
?? tmp/debug.log
```

Plan:

```text
1. style(api): reformat handlers.rb
     src/api/handlers.rb (formatting hunks only)
2. refactor(api): rename build_payload to serialize_record
     src/api/handlers.rb (rename hunks), src/api/serializers.rb
3. fix(api): return 404 instead of 500 when the record is missing
     src/api/handlers.rb (nil-check hunk), spec/api/handlers_spec.rb
4. feat(api): add a CSV export endpoint
     src/api/export.rb, Gemfile, Gemfile.lock
Excluded: tmp/debug.log (local output; suggest a .gitignore rule)
```

Why this order: the formatting goes first, so the later diffs on `handlers.rb` show only real
changes. The rename comes before the fix, so the fix's diff uses the final name. The gem and
lockfile go with the feature that needs them. If the formatting hunks overlap the rename or
the fix, don't pick hunks: regenerate the formatting commit by running the formatter on the
committed file (splitting-and-staging.md, section 6). Combine commits only if even that fails,
and say so in the body. Don't distort the code to force a split.

## 4. Critiquing a message

Input:

```text
Updated the payment code to fix the issue where sometimes payments would fail and also cleaned up some stuff and added logging.
```

Review:

- The subject is one 130-character line, past the 72-character limit, and has no blank line or
  body.
- It's in past tense ("Updated"). Use the imperative.
- It's vague: "the issue", "sometimes", and "some stuff" don't say what failed or why.
- It describes three changes (a fix, a cleanup, logging), so it's probably three commits. Check
  the diff.
- It has no type or scope, but the repo's history uses Conventional Commits.

Rewrite, assuming the diff confirms a retry bug as the main change:

```text
fix(payments): retry card authorization on gateway 503

Authorization failed outright whenever the gateway shed load, though
a retry a moment later succeeds. Retry 503s up to twice with jittered
backoff; other errors still fail immediately so declines aren't
retried.
```

Then commit the cleanup (`refactor(payments): ...`) and the logging
(`chore(payments): log gateway status codes on failure`) separately. If the logging exists
mainly to diagnose this bug, include it in the fix commit instead.
