# Ecosystem reference: version, source, docs

Where each ecosystem records the version that actually runs, how to ask the tooling, where
the installed source lives, how to introspect a signature, where versioned docs are, and
how deprecations are marked. Placeholders: `<pkg>` package/distribution name, `<ver>`
exact version, `<mod>` import/module name.

Run every command through the project's own toolchain, not a global install that may
differ: its virtualenv (`.venv/bin/python`, `uv run --no-sync`, `poetry run`), `./gradlew`,
`bundle exec`, and for JavaScript a runner that never downloads (`npx --no -- <bin>`,
`pnpm exec <bin>`, `yarn <bin>`, `./node_modules/.bin/<bin>`).

## Contents

- [Summary table](#summary-table)
- [JavaScript / TypeScript](#javascript--typescript)
- [Python](#python)
- [Go](#go)
- [Rust](#rust)
- [PHP](#php)
- [Ruby](#ruby)
- [JVM: Maven and Gradle](#jvm-maven-and-gradle)
- [.NET](#net)
- [Swift, CocoaPods, Dart/Flutter, Elixir](#swift-cocoapods-dartflutter-elixir)
- [Infrastructure and tooling config](#infrastructure-and-tooling-config)
- [Checking a package before adding it](#checking-a-package-before-adding-it)

## Summary table

| Ecosystem | Pinned in | Ask for installed version | Installed source | Versioned docs |
|---|---|---|---|---|
| JS/TS | `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lock` | `npm ls <pkg>`, `pnpm why <pkg>`, `yarn why <pkg>` | `node_modules/<pkg>/` | project site version switcher; `unpkg.com/<pkg>@<ver>/` for files |
| Python | `uv.lock`, `poetry.lock`, `Pipfile.lock`, `pdm.lock`, pinned `requirements*.txt` | `python -m pip show <pkg>`, `uv pip show <pkg>`, `poetry show <pkg>` | `.venv/lib/python3.X/site-packages/` | `<project>.readthedocs.io/en/<ver>/`, `pypi.org/project/<pkg>/<ver>/` |
| Go | `go.mod` (+ module graph) | `go list -m <module>` | `$(go env GOMODCACHE)/<module>@<ver>/`, or `vendor/` | `pkg.go.dev/<module>@<ver>` |
| Rust | `Cargo.lock` | `cargo tree -i <crate>`, `cargo pkgid <crate>` | `~/.cargo/registry/src/*/<crate>-<ver>/` | `docs.rs/<crate>/<ver>/` |
| PHP | `composer.lock` | `composer show <vendor/pkg>` | `vendor/<vendor>/<pkg>/` | repo at tag; framework sites with version in path |
| Ruby | `Gemfile.lock` | `bundle info <gem>` | `bundle info --path <gem>` | `rubydoc.info/gems/<gem>/<ver>` |
| Maven | `pom.xml` + BOMs (no lockfile by default) | `mvn dependency:tree -Dincludes=<group>:<artifact>` | `~/.m2/repository/<group path>/<artifact>/<ver>/` | `javadoc.io/doc/<group>/<artifact>/<ver>` |
| Gradle | `gradle.lockfile` (if locking enabled), `libs.versions.toml` | `./gradlew dependencyInsight --dependency <name> --configuration runtimeClasspath` | `~/.gradle/caches/modules-2/files-2.1/<group>/<artifact>/<ver>/` | `javadoc.io/doc/<group>/<artifact>/<ver>` |
| .NET | `packages.lock.json` (if enabled), `Directory.Packages.props`, `.csproj` | `dotnet list package --include-transitive` | `~/.nuget/packages/<id lowercase>/<ver>/` | `learn.microsoft.com/dotnet/api/...?view=<moniker>`, `nuget.org/packages/<id>/<ver>` |
| Dart | `pubspec.lock` | `dart pub deps` | `~/.pub-cache/hosted/pub.dev/<pkg>-<ver>/` | `pub.dev/documentation/<pkg>/<ver>/` |
| Elixir | `mix.lock` | `mix deps` | `deps/<name>/` | `hexdocs.pm/<pkg>/<ver>/` |
| Swift (SwiftPM CLI) | `Package.resolved` | `swift package show-dependencies` | `.build/checkouts/<name>/` | repo at tag |
| Swift (Xcode app) | `<App>.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved`, or the same path under `<App>.xcworkspace` | read the resolved file | `~/Library/Developer/Xcode/DerivedData/<App>-<hash>/SourcePackages/checkouts/<name>/` | repo at tag |
| CocoaPods | `Podfile.lock` | `Pods/Manifest.lock` (what was last installed); `pod outdated` for newer releases | `Pods/<Name>/` | repo at tag; `cocoapods.org/pods/<Name>` |

## JavaScript / TypeScript

**Pinned in.** `package-lock.json` / `npm-shrinkwrap.json` (npm), `pnpm-lock.yaml`,
`yarn.lock`, `bun.lock` (text lockfile in current Bun; older projects have binary
`bun.lockb`). `package.json` holds ranges only.

**Installed version.**

```bash
npm ls <pkg>            # every resolved copy and the path that pulled it in
npm explain <pkg>       # why each copy is installed
pnpm why <pkg>          # pnpm equivalent
yarn why <pkg>          # yarn (classic and berry)
bun pm ls               # bun
```

Or read `node_modules/<pkg>/package.json` directly. `node -p "require('<pkg>/package.json').version"`
fails with `ERR_PACKAGE_PATH_NOT_EXPORTED` when the package's `exports` map hides its
`package.json`; read the file instead. Several copies at different versions are normal; the
one that matters is the copy resolved from the file you are editing (nearest `node_modules`
walking up from it, or the workspace's own folder in a monorepo).

**Layout gotchas.** pnpm symlinks `node_modules/<pkg>` into
`node_modules/.pnpm/<pkg>@<ver>/node_modules/<pkg>`, so the version is in the path.

Yarn Plug'n'Play (Yarn 2+, `nodeLinker: pnp`) has no `node_modules`, so plain `node -e
"require(...)"`, `rg node_modules/...` and `npx` all fail or see nothing. Packages are zip
archives in the project's `.yarn/cache/` only when `enableGlobalCache` is false (the
zero-installs setup); since Yarn 4 the default is true and the zips live in the global
cache under `~/.yarn/berry/`. Check with `yarn config get enableGlobalCache` and
`yarn config get cacheFolder`. To read the source:

```bash
yarn node -p "require.resolve('<pkg>/package.json')"   # path inside the zip; unzip -l / unzip -p it
yarn unplug <pkg>                                      # extracts it to .yarn/unplugged/ (edits project state; ask first)
yarn <bin>                                             # run a dependency's binary
```

**Running binaries.** Bare `npx <bin>` runs the local copy when one is installed, but when
it is not, npm fetches the latest package with that name, and it skips the confirmation
prompt whenever stdin is not a terminal (as in an agent's shell) or CI is detected. The
check then runs against a different version, or a different package entirely: the npm
package named `tsc` is a stub, not TypeScript. Use `npx --no -- <bin>` (fails instead of
downloading), `pnpm exec <bin>`, `yarn <bin>`, or `./node_modules/.bin/<bin>`. `bunx`,
`pnpm dlx` and `yarn dlx` download on purpose; use them only for a deliberate one-off.

**Available versions.** `npm view <pkg> versions --json`, `npm view <pkg> dist-tags`,
`npm view <pkg>@<ver> engines peerDependencies`.

**Where the API surface is.** In the package's `package.json`, follow `exports` (look for
`"types"` conditions), then `types`/`typings`, then `main`/`module`. Prefer `.d.ts` over
compiled JavaScript. Untyped packages may have `node_modules/@types/<pkg>`; its
major.minor should track the library's. Many packages ship `CHANGELOG.md` and `README.md`
inside `node_modules/<pkg>/`.

**Introspect.**

```bash
npx --no -- tsc --noEmit                                     # type-check against installed types
node -e "console.log(Object.keys(require('<pkg>')))"         # CommonJS exports (yarn node under PnP)
node --input-type=module -e "import * as m from '<pkg>'; console.log(Object.keys(m))"
```

**Versioned docs.** Project sites usually have a version switcher or versioned
subdomain/path. Published files at an exact version: `https://unpkg.com/<pkg>@<ver>/` or
`https://cdn.jsdelivr.net/npm/<pkg>@<ver>/` (includes the shipped `.d.ts`).

**Deprecations.** `@deprecated` JSDoc tags in `.d.ts` (editors strike these through);
deprecated releases show via `npm view <pkg>@<ver> deprecated`; runtime
`DeprecationWarning`s (run Node with `--trace-deprecation` to locate the caller).

**Runtime pins.** `.nvmrc`, `.node-version`, `engines.node`, `packageManager`, `volta` in
`package.json`, CI matrix.

**Re-sync from the lockfile** (rewrites `node_modules`; ask first): `npm ci`,
`pnpm install --frozen-lockfile`, `yarn install --immutable` (Yarn 2+; `--frozen-lockfile`
on Yarn 1), `bun install --frozen-lockfile`.

## Python

**Pinned in.** `uv.lock`, `poetry.lock`, `Pipfile.lock`, `pdm.lock`, `requirements*.txt`
with `==` pins, constraints files. `pyproject.toml` dependency lists are ranges.

**Use the project's interpreter.** `.venv/bin/python`, `uv run --no-sync ...`,
`poetry run ...`, `pipenv run ...`, `pdm run ...`. The global `python` often has a
different version or none of the dependencies. Plain `uv run` locks and syncs the project
environment before it runs the command, so it can install or remove packages; `--no-sync`
runs against the environment as it is.

**Installed version.**

```bash
python -m pip show <dist>           # Version, Location, Requires, Required-by
uv pip show <dist>
poetry show <dist>
python -c "import importlib.metadata as m; print(m.version('<dist>'))"
uv tree --invert --package <dist>   # who depends on it
```

**Import name versus distribution name.** `import yaml` comes from `PyYAML`, `PIL` from
`Pillow`, `sklearn` from `scikit-learn`. Map one to the other (Python 3.10+):
`python -c "import importlib.metadata as m; print(m.packages_distributions().get('<mod>'))"`.

**Available versions.** `python -m pip index versions <dist>` (marked experimental), or the
JSON API `https://pypi.org/pypi/<dist>/json`.

**Where the source is.** `python -c "import <mod>; print(<mod>.__file__)"`;
`python -m pip show -f <dist>` lists every installed file. Start at the package's
`__init__.py` to see what is re-exported publicly. Typed packages ship `py.typed` and may
have `.pyi` stubs next to modules; separate stub distributions are named `types-<dist>` or
`<dist>-stubs`. For C extensions, the `.pyi` stub or `help()` is the readable surface.

**Introspect.**

```bash
python -c "import inspect, <mod>; print(inspect.signature(<mod>.<func>))"
python -m pydoc <mod>.<attr>
python -W error::DeprecationWarning -c "import <mod>"   # turn deprecations into errors
```

**Versioned docs.** Read the Docs: `https://<project>.readthedocs.io/en/<ver>/` (also
`stable`, `latest`; the slug format varies per project). Release page:
`https://pypi.org/project/<dist>/<ver>/`. Standard library: `https://docs.python.org/3.<minor>/`.

**Deprecations.** `warnings.warn(..., DeprecationWarning)` (or `PendingDeprecationWarning`,
`FutureWarning`), `@warnings.deprecated` (Python 3.13+) or
`typing_extensions.deprecated`, "deprecated" in docstrings. In tests:
`pytest -W error::DeprecationWarning`.

**Runtime pins.** `.python-version`, `requires-python`, `tox.ini`/`noxfile.py`, CI matrix.

**Re-sync from the lockfile** (rewrites the environment; ask first): `uv sync --locked`
(fails if `uv.lock` is stale), `poetry sync` (Poetry 2; `poetry install --sync` on 1.x),
`pipenv sync`, `pdm sync`, or `python -m pip install -r requirements.txt` into the
project's virtualenv.

## Go

**Pinned in.** `go.mod` `require` lines plus the module graph (minimal version
selection). `go.sum` holds checksums and can mention versions that are not selected, so do
not read the version from it.

**Installed version.**

```bash
go list -m <module>           # selected version
go list -m all                # whole build list
go mod why -m <module>        # why it is needed
go list -m -versions <module> # available versions
go list -m -u <module>        # available upgrade
```

**Major versions are different import paths.** v2+ modules end in `/vN`
(`example.com/mod/v3`). Code written for v3 against the v1 path will not compile, and the
reverse is a classic source of "undefined" errors.

**Where the source is.** `go list -m -f '{{.Dir}}' <module>` (download first with
`go mod download <module>` if empty). The cache root is `go env GOMODCACHE`; uppercase
letters in module paths are stored as `!` plus lowercase. A `vendor/` directory, when
present and used, is what builds.

**Introspect.** Run inside the module so the selected versions are used:

```bash
go doc <importpath>                 # package summary
go doc <importpath>.<Symbol>        # one symbol's signature and comment
go doc -all <importpath>
go doc -src <importpath>.<Symbol>   # its source
go build ./... && go vet ./...
```

`ExampleXxx` functions in the package's `*_test.go` files are compiled, runnable examples.

**Versioned docs.** `https://pkg.go.dev/<module>@<ver>`; standard library at a release,
e.g. `https://pkg.go.dev/net/http@go1.22.0`.

**Deprecations.** A paragraph beginning `Deprecated:` in a doc comment (and a
`// Deprecated:` comment above `module` in a deprecated module's `go.mod`). `staticcheck`
reports uses as SA1019.

**Runtime pins.** `go` and `toolchain` directives in `go.mod`.

## Rust

**Pinned in.** `Cargo.lock`. In `Cargo.toml`, `"1.2"` means `^1.2`.

**Installed version.**

```bash
cargo tree -i <crate>          # resolved version(s) and who depends on them
cargo pkgid <crate>            # package ID including version
cargo metadata --format-version 1   # JSON with each package's manifest_path
cargo info <crate>             # registry info (recent Cargo)
```

**Where the source is.** `$CARGO_HOME/registry/src/<index>/<crate>-<ver>/` (default
`CARGO_HOME` is `~/.cargo`); git dependencies under `~/.cargo/git/checkouts/`; `vendor/`
if the project vendors. Public API starts at `src/lib.rs`; `examples/` and doc tests are
runnable usage.

**Introspect.** `cargo doc -p <crate> --no-deps --open` renders docs for exactly the locked
version and the features this project enables. `cargo check` is the fast compile check.

**Feature gates.** Items can exist only behind Cargo features. docs.rs renders all
features and labels them "Available on crate feature X only"; check the crate's
`[features]` and this project's `features = [...]` before assuming an item is available.

**Versioned docs.** `https://docs.rs/<crate>/<ver>/`.

**Deprecations.** `#[deprecated(since = "...", note = "...")]`; the compiler's
`deprecated` lint warns at call sites.

**Runtime pins.** `rust-toolchain.toml`, `rust-version` (MSRV) and `edition` in `Cargo.toml`.

## PHP

**Pinned in.** `composer.lock`. `composer.json` holds constraints.

**Installed version.**

```bash
composer show <vendor/pkg>               # installed version, source, requirements
composer show --path <vendor/pkg>        # install directory
composer why <vendor/pkg>                # what requires it
composer show --available <vendor/pkg>   # versions offered by repositories
composer outdated <vendor/pkg>           # newer releases
```

**Where the source is.** `vendor/<vendor>/<pkg>/`; `composer.json` there names the
autoload roots.

**Introspect.** Reflection prints a method's real signature, defaults included:

```bash
php -r 'require "vendor/autoload.php"; echo new ReflectionMethod("Vendor\\Pkg\\SomeClass", "someMethod");'
```

`php --rc <Class>` works for built-in and extension classes. Run the project's static
analyser (PHPStan, Psalm) if configured.

**Versioned docs.** Most PHP libraries document in the repository, so browse it at the
release tag. Framework doc sites usually carry the major version in the URL path. Language
changes: the php.net migration appendix per release (e.g. `https://www.php.net/manual/en/migration84.php`).

**Deprecations.** `@deprecated` in PHPDoc, the `#[\Deprecated]` attribute (PHP 8.4+),
`trigger_error(..., E_USER_DEPRECATED)` or `trigger_deprecation()` calls.

**Runtime pins.** `require.php` and `config.platform.php` in `composer.json`.

## Ruby

**Pinned in.** `Gemfile.lock`.

**Installed version.**

```bash
bundle info <gem>                    # version, summary, path
bundle info --path <gem>             # path only
bundle outdated <gem>
gem list --remote --all --exact <gem>   # available versions
bundle exec ruby -e 'puts Gem.loaded_specs["<gem>"].version'
```

**Introspect.**

```bash
bundle exec ruby -e 'require "<lib>"; p <Class>.instance_method(:<meth>).parameters'
bundle exec ri '<Class>#<meth>'      # if ri docs were installed
```

**Versioned docs.** `https://www.rubydoc.info/gems/<gem>/<ver>`; Rails publishes
`https://api.rubyonrails.org/v<major.minor>/` and `https://guides.rubyonrails.org/v<major.minor>/`.

**Deprecations.** YARD `@deprecated`, framework deprecators (Rails logs deprecation
warnings in test output), `warn` calls mentioning deprecation.

**Runtime pins.** `.ruby-version`, the `ruby` line in `Gemfile`.

## JVM: Maven and Gradle

**Pinned in.** Maven has no lockfile by default; the effective version can come from a
parent POM or an imported BOM rather than the dependency line you see. Gradle may use
`gradle.lockfile` (dependency locking) and a version catalog (`gradle/libs.versions.toml`),
but conflict resolution and platforms/BOMs can still change the resolved version.

**Resolved version.**

```bash
mvn dependency:tree -Dincludes=<groupId>:<artifactId>
mvn help:effective-pom
./gradlew dependencyInsight --dependency <artifactId> --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath
```

**Where the source is.** Maven: `~/.m2/repository/<group/as/path>/<artifactId>/<ver>/`;
fetch source jars with `mvn dependency:sources`. Gradle:
`~/.gradle/caches/modules-2/files-2.1/<group>/<artifact>/<ver>/<hash>/`. Read a class
with `unzip -p <artifact>-<ver>-sources.jar path/to/Class.java`.

**Introspect.** `javap -cp <path/to/artifact.jar> <fully.qualified.ClassName>` lists the
public members actually compiled into the jar.

**Versioned docs.** `https://javadoc.io/doc/<groupId>/<artifactId>/<ver>`; framework
reference docs usually carry the version in the path.

**Deprecations.** `@Deprecated` (with `since` and `forRemoval` in modern Java), `@deprecated`
Javadoc tag; Kotlin `@Deprecated(message, replaceWith, level)`.

**Runtime pins.** `maven.compiler.release`, Gradle Java toolchain configuration, CI JDK.

## .NET

**Pinned in.** `packages.lock.json` (when `RestorePackagesWithLockFile` is on),
`Directory.Packages.props` (central package management), `PackageReference` in project files.

**Resolved version.** `dotnet list package --include-transitive`.

**Where the source is.** The global packages folder (`dotnet nuget locals global-packages --list`),
typically `~/.nuget/packages/<id lowercase>/<ver>/`. `lib/<tfm>/` holds the assembly and,
usually, an `.xml` file with the XML doc comments, which is readable documentation for the
exact version.

**Versioned docs.** `https://learn.microsoft.com/dotnet/api/<namespace.type>?view=<moniker>`
(for example `view=net-8.0`); package page `https://www.nuget.org/packages/<id>/<ver>`.

**Deprecations.** `[Obsolete]` (compiler warnings CS0612/CS0618, or an error when marked
`error: true`).

**Runtime pins.** `global.json` (SDK), `<TargetFramework>`.

## Swift, CocoaPods, Dart/Flutter, Elixir

- **Swift (SwiftPM command line).** `Package.resolved` at the package root;
  `swift package show-dependencies`; sources in `.build/checkouts/<name>/`.
- **Swift (Xcode-managed packages).** Most app projects resolve packages through Xcode, so
  `Package.resolved` sits at
  `<App>.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved`, or under
  `<App>.xcworkspace/xcshareddata/swiftpm/` when the project uses a workspace. Sources are
  checked out in `~/Library/Developer/Xcode/DerivedData/<App>-<hash>/SourcePackages/checkouts/<name>/`
  (the DerivedData location can be customized in Xcode settings).
- **CocoaPods.** `Podfile.lock` holds the resolved versions (`PODS:` section) and
  `Pods/Manifest.lock` records what was last installed; if the two differ, the installed
  pods are stale. Sources are in `Pods/<Name>/`; `pod outdated` lists newer releases. Swift deprecations in any of
  these: `@available(*, deprecated, message: ...)`; Objective-C: `DEPRECATED_MSG_ATTRIBUTE`
  or `API_DEPRECATED`.
- **Dart/Flutter.** `pubspec.lock`; `dart pub deps` (or `flutter pub deps`); sources in
  `~/.pub-cache/hosted/pub.dev/<pkg>-<ver>/`; docs at
  `https://pub.dev/documentation/<pkg>/<ver>/`. Deprecations: `@Deprecated('...')`.
- **Elixir.** `mix.lock`; `mix deps`, `mix deps.tree`, `mix hex.info <pkg>` (releases);
  sources in `deps/<name>/`; docs at `https://hexdocs.pm/<pkg>/<ver>/`. Deprecations:
  `@deprecated` module attribute.

## Infrastructure and tooling config

Config schemas are versioned like libraries. Ask the installed thing for its schema:

| Tool | Version source | Version-correct schema or docs |
|---|---|---|
| Kubernetes | `kubectl version` | `kubectl explain <resource>.<field>` (served by the cluster itself) |
| Terraform providers | `.terraform.lock.hcl`, `terraform version` | `registry.terraform.io/providers/<namespace>/<name>/<ver>/docs` |
| Helm charts | `Chart.lock`, `helm list` | `helm show values <chart> --version <ver>` |
| GitHub Actions | `uses: owner/action@<ref>` | the action's `action.yml` at that ref |
| Container images | tag or digest in Dockerfile/compose | the image's docs for that tag; never assume `latest` |

## Checking a package before adding it

Confirm the name exists, is the project you mean, and is alive, before proposing it.
Compare the repository link with the docs you read; a near-miss name, a very recent first
release, or a missing or mismatched repository link is a reason to stop and ask.

| Registry | Exists, repository, first release, deprecation |
|---|---|
| npm | `npm view <pkg> name version repository.url deprecated time.created time.modified` |
| PyPI | `https://pypi.org/pypi/<dist>/json`: `info.project_urls`, earliest `upload_time` across `releases`, per-file `yanked` |
| crates.io | `cargo info <crate>`; `https://crates.io/api/v1/crates/<crate>` (`repository`, `created_at`, yanked versions) |
| Go | `go list -m -versions <module>` (the module path names the repository); `pkg.go.dev/<module>` shows deprecation and retraction notices |
| Packagist | `composer show --available <vendor/pkg>`; `https://packagist.org/packages/<vendor>/<pkg>.json` (`repository`, `time`, `abandoned`) |
| RubyGems | `https://rubygems.org/api/v1/gems/<gem>.json` (`source_code_uri`, `homepage_uri`) and `/api/v1/versions/<gem>.json` (release dates, yanked) |
| Maven Central | `https://repo1.maven.org/maven2/<group/as/path>/<artifact>/maven-metadata.xml`; the group id should match the project's domain or hosting account |
| NuGet | `https://www.nuget.org/packages/<id>` (deprecation banner, repository link, reserved-prefix check mark) |
| pub.dev / Hex | `https://pub.dev/packages/<pkg>` (discontinued flag, verified publisher); `mix hex.info <pkg>` (links, retired releases) |
