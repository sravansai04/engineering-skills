# Risk Signals and Breaking-Change Checklist

Use this in step 3 of SKILL.md. Each signal below is something in the diff that requires specific content under "Risk & rollout" or "Breaking changes". On a non-trivial PR, finding none is also worth one line ("Low: no schema, config, dependency or contract changes"). Trivial PRs skip the risk line.

`<remote>/<base>` below is the base resolved in step 1 of SKILL.md: usually `origin/main`, but in a fork it is the upstream remote.

## Quick scan

List the changed paths that usually carry risk:

```bash
git diff --name-only <remote>/<base>...HEAD | grep -iE 'migrat|schema|\.sql$|\.lock$|-lock\.(json|ya?ml)$|go\.(mod|sum)$|package\.json$|requirements.*\.txt$|pyproject\.toml$|pom\.xml$|build\.gradle|gemfile|cargo\.toml$|dockerfile|\.github/workflows/|\.gitlab-ci\.yml$|jenkinsfile|openapi|swagger|\.proto$|\.graphql$|helm|values.*\.ya?ml$|\.tf$|\.env'
```

Find added or removed lines that mention flags, permissions or secrets:

```bash
git diff <remote>/<base>...HEAD | grep -E '^[+-][^+-]' | grep -iE 'feature.?flag|toggle|is_?enabled|permission|role|authori[sz]|secret|token|password|api.?key'
```

These are starting points. Adjust the patterns to the repository's layout once you've seen it. A match tells you to look closer. It doesn't prove a risk.

## Signals and what each requires

| Signal | Typical paths or content | Cover in the description |
|---|---|---|
| Schema migration | `migrations/`, `db/migrate/`, `alembic/versions/`, `prisma/migrations/`, Flyway/Liquibase changelogs, `*.sql` | Whether the migration runs before or after the code deploy. Whether the old code works with the new schema. Locking or rewrite cost on large tables. Any backfill and how it's batched. Whether it's reversible and what a down-migration loses. Use `data-api:db-migration-safety` for the analysis. |
| Dependency change | Manifests and lockfiles: `package.json` + lockfile, `go.mod`/`go.sum`, `Cargo.toml`/`Cargo.lock`, `requirements*.txt`, `poetry.lock`, `uv.lock`, `pom.xml`, `build.gradle(.kts)`, `Gemfile.lock`, `composer.lock` | Which packages changed and why. Major versus minor. For a major bump, link the upstream changelog and name the breaking notes that apply. Say when lockfile churn is only transitive. |
| Config or environment | `.env.example`, `config/`, Helm values, Kubernetes manifests, Terraform | New, renamed or removed keys and their defaults. What operators must set before the deploy. Whether a missing value fails loudly or silently changes behavior. |
| Public contract | OpenAPI/Swagger, `.proto`, GraphQL schema, exported library symbols, CLI flags, event and message schemas, webhook payloads | Whether the change is backward compatible. How it's versioned. Which consumers are affected. Check the breaking-change list below. Use `data-api:api-design` for the contract reasoning. |
| Auth, permissions, crypto, secrets handling | Middleware, policy and role checks, token handling, session code | What access changes and for whom. Ask for a reviewer with security context, and use `review-suite:secure-code-review` when appropriate. |
| Feature flag | New flag checks or flag config | Flag name, default in each environment, who flips it and when, kill-switch behavior, and the cleanup issue. |
| Build, CI or deploy | `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, `Dockerfile`, build scripts | What changes for every contributor or every deploy. How the change was validated, for example a CI run on this branch. |
| Deletion | Removed endpoints, files, columns, public functions, config keys | How you confirmed nothing still uses it: a search across repositories, usage metrics, or logs. Whether removal is staged behind a deprecation. |
| Hot-path performance | Queries in loops, new or dropped indexes, caching, serialization of large payloads | Measured before and after numbers with the method used. If nothing was measured, say so. Use `review-suite:performance-review` or `data-api:query-review` for depth. |
| Data writes and side effects | Backfills, bulk updates, emails, payments, third-party API writes | Whether the operation is idempotent. Whether there is a dry run. Batch size. What cannot be undone. |
| Concurrency or scheduling | Locks, retries, queues, cron schedules, timeouts | Behavior under retry and duplicate delivery, and during a rolling deploy when old and new code run side by side. |
| Security fix | A patched validation, authorization, deserialization or path-handling flaw; a dependency bump for a published advisory; an issue or commit that mentions a vulnerability | If the flaw isn't publicly disclosed yet, stop and follow "Security fixes" in SKILL.md step 3 before writing anything. A bump for an advisory that is already public can name and link it. |

## Breaking-change checklist

A change is breaking for someone if it does any of these:

**Removes or renames:**
- A public function, type or endpoint.
- A route, CLI flag or subcommand.
- A config key or environment variable.
- An event or message field.
- A database column that another service reads.

**Changes semantics:**
- Default values.
- Response shape, status codes or error types.
- Ordering or pagination behavior.
- Units, time zones or rounding.
- Validation that now rejects input it used to accept.

**Raises requirements:**
- The minimum language, runtime or platform version.
- A required permission or scope.
- A major dependency version that consumers also see.

**Changes formats:**
- Wire or serialization format.
- Persisted file or data format.
- Cache key layout that other versions share.

For each break, write who is affected, what they must change, whether a deprecation window or compatibility shim exists, and when the old behavior goes away. If the repository uses Conventional Commits, mark the title with `!` (for example `feat(api)!: ...`), because tooling that generates changelogs from squash commits may depend on it.
