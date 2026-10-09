# Discovering and running a project's checks

Read this when `discover-checks.sh` output is ambiguous, the stack is unfamiliar, the repo is a monorepo, or you need to run a single test by name.

## Contents

1. Reading CI config
2. Per-ecosystem map
3. Monorepos: running only what is affected
4. Running one test, and listing what will run
5. Bypassing caches
6. Environment parity

## 1. Reading CI config

CI is the closest thing to a definition of "passing" because it gates the merge. When you read a pipeline file, extract:

- **The commands**: every `run:` (GitHub Actions), `script:` (GitLab, Bitbucket, Azure), `command:` (CircleCI, Buildkite), or `sh` step (Jenkins). Prefer the exact invocation, flags included; `pytest -q -m "not slow"` and `pytest` are different checks. Steps can also live outside the workflow file: local composite actions (`uses: ./.github/actions/<name>`), reusable workflows (`uses: ./.github/workflows/<file>`), GitLab `include:` files, and CircleCI orbs. Read those too.
- **The matrix**: language versions and operating systems. You can usually run only one locally. Run the one closest to production and name the others as not verified if the change is version-sensitive (syntax, stdlib APIs, path handling on Windows).
- **Services**: databases, caches, or brokers started as CI services or containers. Integration tests that need them may skip themselves silently locally. Check the skipped count, and start the service the way the project documents (often `docker compose up -d <service>`).
- **Environment variables**: `CI=true`, `NODE_ENV=test`, `DATABASE_URL`, feature-flag overrides. Tests can behave differently without them.
- **Path filters and conditions**: jobs that run only when certain paths change, or only on the main branch. A job that would run on your PR counts even if it is not in the default workflow.
- **Separate jobs**: lint, types, unit, integration, e2e, build, docs, license or dependency audit. Each one is a check you should either run or list as not run.

## 2. Per-ecosystem map

To look by hand rather than through `discover-checks.sh`:

```bash
npm run                                   # lists package.json scripts (pnpm run works too)
grep -E '^[A-Za-z0-9_.-]+:' Makefile      # make targets; many repos also have `make help`
grep -E '^\[tool\.' pyproject.toml        # which Python tools are configured (pytest, ruff, mypy, ...)
grep -nE '^[[:space:]]*(- )?run:' .github/workflows/*.yml   # the exact commands CI runs
```

The "list" column shows how to see what the project defines; the "typical checks" column shows common commands when the project wraps nothing. Prefer the project's own wrapper whenever one exists.

**Never let a runner download a tool.** In a non-interactive shell `npx <tool>` installs and runs whatever registry package has that name if the tool is not a local dependency (npm assumes `--yes` when stdin is not a TTY), at the latest version rather than the project's pin; `npx tsc` without TypeScript installed fetches an unrelated package called `tsc`. Use `npx --no -- <tool>` (fails instead of fetching), `./node_modules/.bin/<tool>`, or the package script. `pnpm exec` and `yarn <bin>` run local binaries only; `bunx` also auto-installs, so use `bunx --no-install`. If a tool is not a declared dependency, record the check as not run and suggest adding it.

| Signal file | List what is defined | Typical checks |
|---|---|---|
| `package.json` (lockfile tells the manager: `package-lock.json` npm, `pnpm-lock.yaml` pnpm, `yarn.lock` yarn, `bun.lock`/`bun.lockb` bun) | `npm run` or `pnpm run` with no script name; or read the `scripts` block | `npm run lint`, `npm run build`, `npm test`; `npx --no -- tsc --noEmit`, `npx --no -- eslint .`, `npx --no -- prettier --check .`, `npx --no -- vitest run`, `npx --no -- jest` |
| `deno.json` | `deno task` | `deno check .`, `deno lint`, `deno fmt --check`, `deno test` |
| `pyproject.toml`, `setup.cfg`, `tox.ini`, `noxfile.py` | `[tool.*]` sections; `tox list` (tox 4) or `tox -l` (tox 3); `nox --list` | `pytest`, `ruff check .`, `ruff format --check .`, `black --check .`, `mypy`, `pyright`; prefix with `uv run`, `poetry run`, `pdm run`, or `hatch run` when the project uses that tool |
| `Cargo.toml` | `cargo --list` shows installed subcommands | `cargo build --all-targets`, `cargo test`, `cargo clippy --all-targets -- -D warnings`, `cargo fmt --check` |
| `go.mod` | `Makefile` or `magefile.go` if present | `go build ./...`, `go vet ./...`, `go test ./...` (add `-race` for concurrent code), `test -z "$(gofmt -l .)"`, `golangci-lint run` if configured |
| `build.gradle(.kts)`, `gradlew` | `./gradlew tasks --all` | `./gradlew check` (tests plus verification tasks), `./gradlew build` |
| `pom.xml`, `mvnw` | read the plugins section | `./mvnw verify` |
| `*.sln`, `*.csproj` | `dotnet --list-sdks` for versions | `dotnet build`, `dotnet test`, `dotnet format --verify-no-changes` |
| `Gemfile` | `bundle exec rake -T` | `bundle exec rspec` or `bundle exec rake test`, `bundle exec rubocop` |
| `composer.json` | `composer run-script --list` | `vendor/bin/phpunit`, `vendor/bin/phpstan analyse`, `vendor/bin/php-cs-fixer fix --dry-run --diff` |
| `mix.exs` | `mix help` | `mix compile --warnings-as-errors`, `mix format --check-formatted`, `mix test` |
| `Package.swift` | | `swift build`, `swift test` |
| `pubspec.yaml` | | `dart analyze` or `flutter analyze`, `dart test` or `flutter test`, `dart format --output=none --set-exit-if-changed .` |
| `CMakeLists.txt` | | `cmake -S . -B build && cmake --build build && ctest --test-dir build` (`--test-dir` needs CMake 3.20+) |
| `MODULE.bazel`, `WORKSPACE` | `bazel query //...` | `bazel build //...`, `bazel test //...` |
| `Makefile` | `make help` if defined; otherwise read the targets | the targets named `check`, `test`, `lint`, `fmt`, `ci`, `verify` |
| `justfile` | `just --list` | the recipes named like checks |
| `Taskfile.yml` | `task --list-all` | the tasks named like checks |
| `.pre-commit-config.yaml` | the `id:` entries | `pre-commit run --from-ref "$(git merge-base origin/main HEAD)" --to-ref HEAD` (add `--files <paths>` for uncommitted files); then `git status --short` |
| `lefthook.yml` | the hook sections | `lefthook run pre-commit` (and `pre-push` if defined) |
| `.husky/` | the hook files | run the commands they contain |

Git hooks are checks too. If the repo installs pre-commit or pre-push hooks, their commands will run on commit and push anyway; running them now means no surprises.

Formatters: run them in check mode (`--check`, `--verify-no-changes`, `--set-exit-if-changed`). Anything that runs fixers in write mode, a formatter across the repo or `pre-commit run --all-files` with hooks such as end-of-file and whitespace fixers, can rewrite files you did not touch: check `git status --short` afterwards and revert edits outside your change.

Exit codes do not always tell the truth. `gofmt -l` lists unformatted files and still exits 0, hence `test -z "$(gofmt -l .)"`; some audit and report-mode tools behave the same way. Read the output, not only the exit code.

Non-interactive flags: anything that prompts (an init wizard, a changeset prompt, an "are you sure") or watches (`vitest`, `jest --watch`, dev-mode test scripts) will hang an agent shell. Pass `CI=true`, `--yes`-style answers, or the run-once form (`vitest run`).

## 3. Monorepos: running only what is affected

Running the whole repo's suite can be impractical. Run checks for every package your change touches and every package that depends on those (its dependents, also called reverse dependencies), and name the scope in the report. A change to shared code that is tested only in its own package leaves its most important consumers untested.

| Tool | Changed package plus its dependents | This package only (fast feedback, not enough for shared code) |
|---|---|---|
| Nx | `npx --no -- nx affected -t lint test build --base=origin/main` | `npx --no -- nx test <project>` |
| Turborepo | `npx --no -- turbo run lint test build --affected`, or `--filter=...[origin/main]` | `--filter=<package>` |
| pnpm workspaces | `pnpm --filter "...[origin/main]" test` | `pnpm --filter <package> test` |
| Gradle multi-project | `./gradlew :module:buildDependents` (builds and tests the module and every project that depends on it) | `./gradlew :module:check` |
| Maven multi-module | `./mvnw -pl module -am -amd verify` (`-amd` adds dependents; `-am` alone builds only what the module depends on) | `./mvnw -pl module verify` |
| Cargo workspace | `cargo test --workspace` when other workspace crates depend on the changed one | `cargo test -p crate` |
| Go | `go test ./...` (the test cache keeps unaffected packages cheap) | `go test ./path/to/pkg/...` |
| Bazel | `bazel test $(bazel query 'tests(rdeps(//..., //path/to/pkg/...))')` | `bazel test //path/to/pkg/...` |

When in doubt, run more.

## 4. Running one test, and listing what will run

Run the new or changed test by name for fast feedback, and to prove it was collected.

| Runner | Run one | List what would run |
|---|---|---|
| pytest | `pytest path/to/test_file.py::test_name` | `pytest --collect-only -q` |
| Jest | `npx --no -- jest path/to/file -t "name pattern"` | `npx --no -- jest --listTests` |
| Vitest | `npx --no -- vitest run path/to/file -t "name pattern"` | `npx --no -- vitest list` |
| Go | `go test ./pkg -run 'TestName$'` | `go test -list . ./pkg` |
| Cargo | `cargo test test_name` | `cargo test -- --list` |
| Gradle | `./gradlew test --tests 'com.example.FooTest'` | |
| Maven Surefire | `./mvnw -Dtest=FooTest test` | |
| .NET | `dotnet test --filter "FullyQualifiedName~FooTests"` | `dotnet test --list-tests` |
| RSpec | `bundle exec rspec spec/foo_spec.rb:42` | `bundle exec rspec --dry-run` |
| PHPUnit | `vendor/bin/phpunit --filter testName` | `vendor/bin/phpunit --list-tests` |

Common reasons a new test does not run: the file name does not match the runner's pattern (pytest collects `test_*.py` and `*_test.py` by default; Jest and Vitest use `testMatch` or `include` globs), the test sits in a directory excluded by config, a marker or tag filter in CI excludes it, or a focused test elsewhere (`.only`, `fit`) is suppressing everything else.

Exit codes that mean "nothing ran": pytest returns 5 when it collects no tests. Jest fails when no tests are found unless `--passWithNoTests` is passed; if a script passes that flag, a typo in a path silently runs nothing. `go test` prints `[no test files]` for packages without tests and still exits 0.

## 5. Bypassing caches

Caches are usually correct. Force a fresh run when you suspect the cache missed an input (an environment variable, a file outside the declared inputs, a generated file).

| Tool | Force a rerun |
|---|---|
| Go | `go test -count=1 ./...` |
| Turborepo | `turbo run test --force` |
| Nx | `nx affected -t test --skipNxCache` |
| Gradle | `./gradlew test --rerun-tasks` |
| Bazel | `bazel test //... --cache_test_results=no` |
| pytest | results are not cached; `--cache-clear` resets plugin state such as `--lf` |
| Jest | `npx --no -- jest --no-cache` (clears the transform cache, not results) |

## 6. Environment parity

Compare your local toolchain to CI before trusting a local pass on version-sensitive code:

- Version pins: `.nvmrc`, `.node-version`, `engines` in `package.json`, `.python-version`, `requires-python` in `pyproject.toml`, `.tool-versions` (asdf, mise), `.mise.toml`, `rust-toolchain.toml`, the `go` directive in `go.mod`, `global.json` (.NET), `.ruby-version`.
- Package-manager versions: the `packageManager` field in `package.json`; a different npm or yarn major can rewrite the lockfile wholesale.
- Clean installs: CI typically installs from the lockfile. If your change added or changed a dependency, confirm a locked install still succeeds; only the forms that fail on drift prove the lockfile matches the manifest:

  | Ecosystem | Fails when the lockfile is out of date |
  |---|---|
  | npm | `npm ci` |
  | pnpm | `pnpm install --frozen-lockfile` |
  | Yarn | `yarn install --immutable` (Yarn 2+), `yarn install --frozen-lockfile` (Yarn 1) |
  | uv | `uv sync --locked` |
  | Poetry | `poetry check --lock`, then `poetry install` |
  | Bundler | `BUNDLE_FROZEN=true bundle install` |
  | Cargo | `cargo build --locked` |
  | Go | `go mod tidy -diff` (Go 1.23+), or `go mod tidy && git diff --exit-code go.mod go.sum` |
  | Composer | `composer validate` (errors on a stale lock), then `composer install` |

  Plain `poetry install` or `bundle install` may re-resolve instead of failing, so they prove nothing about drift.
