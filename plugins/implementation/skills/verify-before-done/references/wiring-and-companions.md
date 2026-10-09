# Wiring checks and companion changes

Read this in Steps 6 and 7: to confirm new code is reachable from a real entry point, and to work out which docs, changelog, config, and generated files a repo expects a change to carry.

## Contents

1. Proving reachability
2. Registration points by kind
3. Feature flags and configuration
4. Detecting a repo's companion-change conventions

## 1. Proving reachability

New code is reachable when there is an unbroken path from something that actually runs (a route, a CLI entry point, a scheduler, a UI event, a public export) to it. Prove it in this order, cheapest first:

1. **Search for callers.** `git grep -n --untracked 'NewThing'` across the repo (plain `git grep` skips files you have not added yet, which is where new code usually is; `rg` also works). If the only hits are the definition and its own tests, treat it as a red flag, not proof: many frameworks reach code by file location, naming convention, decorators, or reflection, with no textual reference at all (see the convention-based row in section 2). Also search for the name as a string, since config files, templates, and string-based registries refer to code that way.
2. **Check the registration point** for its kind (table below). Many frameworks discover things only when they are listed somewhere: a route table, a module's provider list, an `__init__.py` export, a plugin manifest. Others discover them by where the file sits and what it is named.
3. **Ask the framework.** Introspection commands print what is actually registered, which beats reading config.
4. **Hit it.** Exercising the real entry point (Step 4 of the skill) is the strongest proof. If the request reaches your code, it is wired.

Dead-code tools help in large changes, though they report pre-existing findings too; look only at what involves your change. Run only tools the project already has; a tool that is not installed is a check you list as not run, not one you download ad hoc:

| Stack | Tool |
|---|---|
| JavaScript/TypeScript | `npx --no -- knip` (unused files, exports, and dependencies), if the project depends on it |
| Python | `vulture src/`, if installed |
| Go | `deadcode ./...` from `golang.org/x/tools/cmd/deadcode`, if the project pins it (for example as a `tool` in `go.mod`, run with `go tool deadcode ./...`); `go run golang.org/x/tools/cmd/deadcode@latest` downloads and runs unpinned code, so ask before using it |
| Rust | the compiler's `dead_code` warnings in `cargo build` output |
| C# | the IDE0051 and IDE0052 analyzer diagnostics (unused private members) |

## 2. Registration points by kind

| Kind | Where it is usually registered | How to confirm |
|---|---|---|
| HTTP route | router file, controller annotations or attributes, URL configuration | Flask: `flask routes`. Rails: `bin/rails routes -g widgets`. Laravel: `php artisan route:list`. Django: `python manage.py show_urls` (needs django-extensions), or read `urls.py` includes. FastAPI: the generated `/openapi.json`. Spring Boot: `/actuator/mappings` if that endpoint is exposed. NestJS: the "Mapped ... route" lines in the startup log. Others: request it and check you do not get a 404 |
| Dependency injection | module or provider lists, container config, `@Component` or similar scanning roots, `builder.Services.Add...` calls | Spring Boot: `/actuator/beans` if that endpoint is exposed. ASP.NET Core: in Development the host validates the container on build (`ValidateOnBuild`, `ValidateScopes`), so a missing registration fails at startup. NestJS: an unresolvable provider fails at bootstrap with the module name. Elsewhere: start the app; an unresolvable dependency usually fails at boot or first use, so exercise the path |
| CLI command | `bin` in `package.json`, `[project.scripts]` in `pyproject.toml`, a command registry or router, `cmd/` mains in Go | run the installed command and its `--help` |
| Package export | `index.ts` barrels, the `exports` field in `package.json`, `__init__.py` and `__all__`, `pub use` in Rust `lib.rs` | import it from a scratch consumer using the public path |
| Event handler or subscriber | subscriber lists, decorators, message-bus routing config | publish a test event and watch the handler run |
| Background job or scheduled task | scheduler config, cron entries, queue consumer config, deployment manifests (for example a Kubernetes CronJob) | trigger it manually; confirm a worker in each environment consumes its queue. Celery: `celery -A proj inspect registered` with a worker running |
| Database migration | the migrations directory and its ordering or dependency metadata | the migration tool's status command shows it pending, then applied |
| UI page or component | router config, navigation menus, feature-flag gates, lazy-load maps | navigate to it from the real menu, not only by typing the URL |
| Permission or role | permission registries, policy files, role seed data | log in as a user who should and one who should not have access |
| Translations | locale or message files | switch locale, or confirm no raw message keys render |
| File-system or convention-based discovery | the file's path and name are the registration: file-based routes (`app/api/health/route.ts`, `pages/`, `src/routes/`), `management/commands/foo.py`, autoloaded controllers, test fixtures in `conftest.py`, component scanning, entry points named as strings in config | confirm the path matches the convention and the export or class name is what the framework expects (`GET`, `default`, `Command`, a decorator or annotation); then hit it |

A route reachable only by typing its URL, or an export available only through an internal path, is usually a wiring bug even though it "works".

## 3. Feature flags and configuration

- **Flag name**: compare the exact string at the definition, the check, and the configuration. A typo silently evaluates to the default, so the new path is permanently off.
- **Defaults per environment**: development, test, staging, production. Decide which should be on, and confirm that is what each environment's configuration says.
- **Both states exercised**: flag off behaves exactly as before; flag on reaches the new code. Tests should cover both.
- **Cleanup**: if the flag is temporary, note a follow-up to remove it.
- **New configuration keys**: present in every environment's config, in the example file (`.env.example`, `config.sample.yaml`, Helm or Compose values), and in the documentation. A missing key either has a safe default or fails at startup with a message naming it. Secrets go in the secret store, never in committed config.

## 4. Detecting a repo's companion-change conventions

Follow what the repo already does. Look at a few recently merged changes (`git log --stat -n 20`) to see which files usually travel with a code change.

| Companion | How to tell the repo uses it | What to do |
|---|---|---|
| Changelog file | `CHANGELOG.md` with an "Unreleased" section (the Keep a Changelog style) | add an entry under Unreleased in the existing style |
| Changesets | a `.changeset/` directory | write `.changeset/<short-slug>.md` by hand: a frontmatter block mapping each changed package to `patch`, `minor`, or `major` (for example `"my-package": minor`), then a one-line summary. The `changeset` command prompts interactively and will hang a non-interactive shell |
| News fragments | `[tool.towncrier]` in `pyproject.toml`, or a `towncrier.toml`; fragments in a directory such as `newsfragments/` or `changelog.d/` | add a fragment file named the way the config expects |
| Release notes (reno) | a `releasenotes/notes/` directory | add a note in the existing format |
| Generated from commits | `release-please-config.json`, `.releaserc`, or a commitlint config | no file to edit; the commit message becomes the release note, so get it right (see `workflow:commit-message`) |
| API description | `openapi.yaml`, `openapi.json`, `swagger.*`, `schema.graphql` | update it, or regenerate it if it is generated from code, and include the result |
| Generated clients and types | codegen config (`buf.gen.yaml`, `codegen.yml`, OpenAPI generator config) plus committed output | rerun the generator and commit its output if the repo commits generated code |
| User docs | `docs/`, a docs site config, README usage sections | update usage, options, and examples that the change affects |
| Version number | a version field the repo bumps manually per change (check recent history) | bump it only if the repo does this per change rather than at release time |
| Migrations | a migrations directory with one file per schema change | add a new migration; never edit one that has already been applied anywhere |
| Dependency notices | `NOTICE`, `THIRD_PARTY_LICENSES`, or an allowed-licenses check in CI | update when adding a dependency |
| Observability | dashboards, alerts, or log-field conventions in the repo | add logs or metrics for a new critical path if the repo's existing paths have them |

If you cannot tell whether a companion is expected, list it in the report as a question for the user rather than guessing either way.
