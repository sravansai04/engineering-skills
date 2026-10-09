# Setting up a fresh worktree

A new worktree is a checkout of tracked files and nothing else. This file covers
how to make it runnable without coupling it to other worktrees.

## Contents

1. What a new worktree lacks
2. Dependencies by ecosystem
3. Env files and local config
4. Ports, databases, containers, and other shared resources
5. Build output and caches
6. Absolute paths that break
7. Hooks
8. Large repositories
9. Editors, test runners, and file watchers
10. Disk usage
11. Make setup one command

## 1. What a new worktree lacks

| Missing | Typical examples | Fix |
|---|---|---|
| Dependencies | `node_modules/`, `.venv/`, `vendor/`, `deps/` | Install fresh (section 2) |
| Build output and generated code | `dist/`, `target/`, `build/`, generated clients | Build in the worktree |
| Local config and secrets | `.env`, `.env.local`, `config/local.*`, `.bundle/config` | Create from a template or copy named files (section 3) |
| Submodule contents | empty submodule folders | `git -C <wt> submodule update --init --recursive` |
| Local data | SQLite files, fixtures you downloaded, seeded databases | Re-create, or copy/clone deliberately |
| Editor state | run configurations, workspace settings | Recreate per worktree |

To see exactly what your main checkout has that git does not track (dependency
and build folders filtered out):

```bash
git -C "$MAIN" ls-files --others --ignored --exclude-standard --directory |
  grep -Ev '(^|/)(node_modules|\.venv|venv|target|dist|build|vendor|coverage|__pycache__|\.next|\.cache)(/|$)'
```

`"${CLAUDE_SKILL_DIR}/scripts/wt-create.sh"` prints this list after creating a worktree.

## 2. Dependencies by ecosystem

Install inside the worktree with the form that fails rather than rewrites the
lockfile when the two disagree. Several everyday commands (`bundle install`,
`cargo fetch`, `dart pub get`, `dotnet restore`, `mix deps.get`) quietly update
the lockfile unless told not to; the table gives the enforcing form. Whatever you
run, check `git -C "$WT" status --short` afterwards as the backstop: if the
install modified a tracked file, stop, because the tool or its version differs
from what the project expects.

| Lockfile / manifest | Install command | Notes |
|---|---|---|
| `package-lock.json` | `npm ci` | The global npm cache makes repeat installs fast. |
| `pnpm-lock.yaml` | `pnpm install --frozen-lockfile` | Packages are linked from a global store, so extra worktrees cost little disk when the store is on the same filesystem. |
| `yarn.lock` (Yarn 1) | `yarn install --frozen-lockfile` | |
| `yarn.lock` (Yarn 2+) | `yarn install --immutable` | With committed zero-install caches there may be nothing to install. |
| `bun.lock` / `bun.lockb` | `bun install --frozen-lockfile` | |
| `uv.lock` | `uv sync --locked` | Creates `.venv` inside the worktree. |
| `poetry.lock` | `poetry install` | Poetry keys its virtualenv by project path, so each worktree gets its own, stored outside the tree. Run `poetry env remove --all` in the worktree before removing it, or the environment lingers in Poetry's cache. |
| `Pipfile.lock` | `pipenv sync` | |
| `requirements.txt` | `python -m venv .venv && .venv/bin/python -m pip install -r requirements.txt` | On Windows use `.venv\Scripts\python`. |
| `Gemfile.lock` | `BUNDLE_FROZEN=true bundle install` | The variable makes Bundler fail instead of rewriting `Gemfile.lock`, and unlike `bundle config set --local frozen true` it writes no `.bundle/config` into the tree. If the project installs gems into the tree (`BUNDLE_PATH`), copy its untracked `.bundle/config` too. |
| `go.sum` | `go mod download` | Module and build caches are global and content-addressed; safe to share. |
| `Cargo.lock` | `cargo fetch --locked`, then `cargo build --locked` | `target/` is per worktree, so the first build is a full build. See section 5. |
| `composer.lock` | `composer install` | |
| `pom.xml` | `./mvnw -DskipTests package` (or `mvn`) | Avoid `install` in parallel worktrees (section 5). |
| `build.gradle(.kts)` | `./gradlew assemble` | Avoid `publishToMavenLocal` in parallel worktrees. |
| `*.sln` / `*.csproj` | `dotnet restore --locked-mode` when `packages.lock.json` exists, else `dotnet restore` | NuGet's global packages folder is shared and safe. |
| `mix.lock` | `mix deps.get --check-locked` | `deps/` and `_build/` are per worktree. |
| `pubspec.lock` | `dart pub get --enforce-lockfile` / `flutter pub get --enforce-lockfile` | |

Do not symlink a dependency folder or virtualenv from another worktree. Branches
can pin different versions, an install in one tree then changes the other, and
virtualenvs contain absolute paths to the place they were created.

## 3. Env files and local config

1. **Prefer the template.** If the repository ships `.env.example`,
   `.env.sample`, or `config/*.example`, create the worktree's file from it and
   fill in values. That keeps the worktree's settings explicit and avoids
   spreading every secret from your main checkout.
2. **Otherwise copy by name**, one file at a time:

   ```bash
   cp "$MAIN/.env" "$WT/.env"
   ```

   Then change everything that must differ per worktree: ports, database names,
   container project name, callback URLs.
3. **Confirm the copy is still ignored in the new tree.** The worktree may be on
   a branch whose `.gitignore` differs:

   ```bash
   git -C "$WT" check-ignore -v .env     # prints the matching rule; no output means NOT ignored
   ```

4. **Copy vs symlink.** Copy anything that must differ or that the task might
   edit. Symlink only large, read-only, identical assets (a downloaded dataset, a
   model file). `git worktree remove` deletes the link, not its target.
5. **Before removal**, an env file you edited in the worktree is exactly the kind
   of ignored file `git worktree remove` deletes without asking. The preflight
   flags ignored files that differ from the main checkout's copy.

## 4. Ports, databases, containers, and other shared resources

Worktrees isolate files, not the machine. Anything addressed by a fixed name or
number is shared:

| Resource | Collision | Isolate with |
|---|---|---|
| Dev server and debug ports | Second server fails to bind, or you test the wrong tree | A slot per worktree: `PORT=$((3000 + 100 * SLOT))`, debug port `9229 + SLOT` |
| Local database | Migrations from one branch break another; tests clobber data | Per-worktree database or schema name, e.g. `myapp_dev_retry_backoff` |
| Docker Compose | Containers, networks, and volumes are namespaced by project name, which defaults to the directory name | `COMPOSE_PROJECT_NAME=myapp-retry-backoff` in the worktree's `.env`; parameterize published ports (`"${APP_PORT:-3000}:3000"`); fixed `container_name:` entries collide regardless |
| Sockets, PID files, temp dirs | Fixed paths like `/tmp/myapp.sock` | Put them under the worktree or include the slot in the name |
| Browser automation profiles | Locked profile directory | Per-worktree profile directory |
| OAuth/webhook callback URLs | Registered for one port only | Run those flows only in the slot whose port is registered |

Write the slot's values into the worktree's own env file so every command run
there picks them up, and record the slot in your report.

## 5. Build output and caches

- **Per-tree output is the isolation.** Keep `dist/`, `target/`, `build/`,
  `_build/`, `bin/`/`obj/` inside each worktree.
- **Content-addressed global caches are safe to share**: npm cache, pnpm store,
  uv cache, Go build and module cache, Gradle build cache, NuGet packages,
  Cargo registry. These make per-worktree installs cheap.
- **Shared mutable install locations are not.** Two worktrees publishing the
  same SNAPSHOT version into `~/.m2` (via `mvn install` or
  `publishToMavenLocal`) overwrite each other. `npm link` / `yarn link` register
  one global link per package name. `pip install -e .` into a shared environment
  points the package at whichever worktree ran it last. Keep these per worktree
  or avoid them during parallel work.
- **Rust**: a shared `CARGO_TARGET_DIR` saves disk but serializes builds behind a
  lock and rebuilds when branches differ; for parallel work keep `target/` per
  tree and use a compiler cache such as sccache if build time hurts.
- **C/C++ with ccache**: set ccache's `base_dir` so hashes use relative paths,
  otherwise objects compiled in one worktree never hit the cache in another.
- **Incremental state keyed by absolute path** (TypeScript build info, some test
  runner caches, `compile_commands.json`) does not carry over; let it rebuild.

## 6. Absolute paths that break

- **Virtualenvs and similar environments** embed their creation path in scripts
  and shebangs. Create one per worktree; never copy or move one.
- **The worktree link itself is absolute by default.** The worktree's `.git` file
  points at `<repo>/.git/worktrees/<name>` and that directory points back. Moving
  either side needs `git worktree move` or `git worktree repair`. Mounting a
  worktree into a container at a different path breaks git inside the container
  (`not a git repository`). Options: mount at the identical absolute path, use a
  separate clone in the container, or link with relative paths (git 2.48+;
  older git and some libgit2-based tools then refuse the repository).
- **Paths hardcoded in the repo or your tooling.** Scripts, task runners, or
  editor configs that `cd` into the main checkout's absolute path will operate
  on the main checkout even when launched from a worktree. Check:
  `git -C "$WT" grep -n "$MAIN"`.
- **Generated editor and debugger configs** (launch configs, run configurations)
  often store absolute paths; regenerate them per worktree.

## 7. Hooks

- Hooks run during creation, not just at commit time: `git worktree add` runs the
  post-checkout hook in the new tree. If it calls tools that are not installed
  there yet, it fails and `add` exits non-zero although the worktree was created
  (check `git worktree list` before retrying). Re-run the hook's job after
  setup; `git -C "$WT" checkout` with no arguments triggers it again.
- `.git/hooks` lives in the shared git directory, so every worktree runs the same
  installed hook scripts. A hook installed by a tool may embed the absolute path of
  an interpreter inside one checkout's environment; delete that environment and
  hooks fail in every worktree.
- A relative `core.hooksPath` is resolved from the root of the worktree running
  the hook, so each worktree uses its own branch's copy of a committed hooks
  folder.
- If `core.hooksPath` points at a directory that is generated during dependency
  install, a fresh worktree has no hooks at all until you install, and commits
  there skip the checks silently. Install dependencies before the first commit.
- Never bypass a hook (`--no-verify`) because it fails in a half-set-up worktree;
  finish the setup instead.

## 8. Large repositories

- **Sparse checkout** keeps a worktree small without affecting the others:
  `git worktree add --no-checkout <path> <branch>`, then
  `git -C <path> sparse-checkout set <dirs...>`, then `git -C <path> checkout`.
  The setting is stored per worktree.
- **Git LFS**: if large files appear as small text pointer files in the new
  worktree, run `git -C <wt> lfs pull`.
- **Partial (blobless) clones** download file contents on checkout, so creating a
  worktree may need network access.

## 9. Editors, test runners, and file watchers

- Open each worktree as its own editor window or project, so language servers,
  linters, and test explorers index the right tree.
- If worktrees live inside the repository, exclude that folder from the main
  project's search, indexing, and file watching (for example the editor's
  watcher/search exclude settings, or marking the folder excluded). Tools that
  walk the filesystem without honoring `.gitignore` (some test runners, module
  resolvers, and glob-based compiler configs) can pick up a nested worktree's
  copies of your files and report duplicates or run the wrong tests. If that
  happens, add an ignore rule for the folder or move worktrees outside the
  repository.
- Tools that read their own ignore file, not `.gitignore`, see nested worktrees
  as ordinary folders. The common one is Docker: `docker build .` sends the build
  context according to `.dockerignore`, so every nested worktree (with its
  dependencies and copied `.env` files) is uploaded, and `COPY . .` puts it in the
  image. Add the worktree folder to `.dockerignore` and to any similar file
  (`.npmignore`, packaging manifests, cloud-deploy ignore files).
- `git clean -ffdx` in the main checkout deletes nested worktrees, uncommitted
  work included. With a single `-f`, git skips them as nested repositories; the
  second `-f` removes that protection. Do not run it (or a "reset everything"
  script built on it) in a checkout that contains worktrees.
- On Linux, many worktrees each running a watching dev server can exhaust inotify
  watches (`ENOSPC: System limit for number of file watchers reached`). Stop idle
  dev servers or raise `fs.inotify.max_user_watches`.

## 10. Disk usage

History is shared; everything else is per worktree. A JavaScript or Rust
worktree can reach several gigabytes once dependencies and build output exist.

- Check: `du -sh <wt>` for one tree, `"${CLAUDE_SKILL_DIR}/scripts/wt-overview.sh" --stale 14`
  to find old ones.
- Remove finished worktrees promptly (through the preflight).
- When you must copy a large ignored file (a fixture database), a copy-on-write
  clone is nearly free on filesystems that support it: `cp -c` on macOS APFS,
  `cp --reflink=auto` with GNU coreutils on btrfs/XFS.

## 11. Make setup one command

If a project is worked on in many worktrees, an idempotent setup entry point pays
for itself: one command (`make setup`, `./scripts/setup`, a package-manager
script) that installs dependencies, creates the env file from the template,
assigns a port/database slot, initializes submodules, and runs migrations for the
per-worktree database. Then every worktree is set up the same way, and the
baseline in step 5 of the skill measures the code rather than the setup.
