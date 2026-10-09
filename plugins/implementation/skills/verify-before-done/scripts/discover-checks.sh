#!/usr/bin/env bash
# discover-checks.sh - list the check commands a project already defines.
#
# Usage: discover-checks.sh [DIR]      (DIR defaults to the current directory)
#        discover-checks.sh --selftest  (check it against a throwaway project)
#        discover-checks.sh -h | --help
#
# Reads manifests, task-runner files, hook configs, CI pipelines and contributor
# docs, and prints what it finds so you can pick the project's OWN build, type,
# lint, format and test commands instead of guessing. Static only: it never runs
# a build tool, task runner or package script, so it is safe on any checkout.
# Uses node or python3 (if present) only to parse JSON.
#
# Output is a starting point. CI config is usually the most authoritative source
# of "what must pass"; contributor docs come second; tool defaults come last.
# Suggested package-binary commands never download a missing tool (npx --no,
# bunx --no-install): a tool the project does not declare is a check not run.
#
# Requires bash with POSIX grep and awk.

set -u

# --selftest: builds a throwaway project (package.json scripts, a Makefile, a
# GitHub Actions workflow) and checks that each source is reported, that an
# empty directory says nothing was found, and that a bad DIR exits 2.
selftest() {
  self="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
  work="$(mktemp -d "${TMPDIR:-/tmp}/discover-checks-selftest.XXXXXX")" || return 2
  fails=0
  mkdir -p "$work/proj/.github/workflows" "$work/empty"
  printf '{"name": "demo", "scripts": {"test": "vitest run", "lint": "eslint ."}}\n' >"$work/proj/package.json"
  printf 'test:\n\tgo test ./...\n\nlint:\n\tgolangci-lint run\n' >"$work/proj/Makefile"
  printf 'jobs:\n  t:\n    steps:\n      - run: npm run lint\n      - run: npm test\n' >"$work/proj/.github/workflows/ci.yml"
  out=$(bash "$self" "$work/proj" 2>&1); rc=$?
  for needle in "rc=0" "package.json scripts" "npm run test" "-> vitest run" "Make targets (Makefile)" \
                "make lint" "CI: .github/workflows/ci.yml" "npm test"; do
    if printf 'rc=%s\n%s\n' "$rc" "$out" | grep -qF -- "$needle"; then
      echo "ok   reports: $needle"
    else
      echo "FAIL missing: $needle"; fails=$((fails + 1))
    fi
  done
  if bash "$self" "$work/empty" 2>&1 | grep -q 'No manifests'; then
    echo "ok   an empty directory reports that nothing was found"
  else
    echo "FAIL an empty directory should report that nothing was found"; fails=$((fails + 1))
  fi
  bash "$self" "$work/no-such-dir" >/dev/null 2>&1
  if [ "$?" -eq 2 ]; then echo "ok   a missing DIR exits 2"; else echo "FAIL a missing DIR should exit 2"; fails=$((fails + 1)); fi
  if bash "$self" -h | grep -q 'Usage' && bash "$self" --help | grep -q -- '--selftest'; then
    echo "ok   -h and --help print usage"
  else
    echo "FAIL -h / --help"; fails=$((fails + 1))
  fi
  rm -rf "$work"
  if [ "$fails" -eq 0 ]; then echo "selftest: all checks passed"; return 0; fi
  echo "selftest: $fails check(s) failed"
  return 1
}

DIR=${1:-.}
case "$DIR" in
  -h|--help) awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; exit 0 ;;
  --selftest) selftest; exit $? ;;
esac
if [ ! -d "$DIR" ]; then
  echo "discover-checks: not a directory: $DIR" >&2
  exit 2
fi
cd "$DIR" || exit 2

MAX_LINES=60
FOUND=0

section() { printf '\n## %s\n' "$1"; FOUND=1; }
note() { printf '  %s\n' "$*"; }
has() { command -v "$1" >/dev/null 2>&1; }
# True if any argument names an existing path (unmatched globs stay literal and fail).
any() { for f in "$@"; do [ -e "$f" ] && return 0; done; return 1; }
first_existing() { for f in "$@"; do [ -e "$f" ] && { printf '%s' "$f"; return 0; }; done; return 1; }

# Print "name<TAB>command" for every entry of the top-level "scripts" object in
# a JSON manifest (package.json, composer.json, deno.json tasks via $2).
json_entries() {
  file=$1; key=${2:-scripts}
  if has node; then
    node -e '
      const fs = require("fs");
      let j; try { j = JSON.parse(fs.readFileSync(process.argv[1], "utf8")); } catch (e) { process.exit(3); }
      const s = (j && j[process.argv[2]]) || {};
      for (const [k, v] of Object.entries(s)) {
        if (k.startsWith("//")) continue;
        console.log(k + "\t" + (Array.isArray(v) ? v.join(" && ") : typeof v === "string" ? v : JSON.stringify(v)));
      }' "$file" "$key" 2>/dev/null && return 0
  fi
  if has python3; then
    python3 -I -c '
import json, sys
try:
    j = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    sys.exit(3)
s = j.get(sys.argv[2]) or {}
for k, v in s.items():
    if k.startswith("//"):
        continue
    print(k + "\t" + (" && ".join(v) if isinstance(v, list) else v if isinstance(v, str) else json.dumps(v)))
' "$file" "$key" 2>/dev/null && return 0
  fi
  echo "(could not parse; read the \"$key\" block in $file directly)"
}

# Print lines more indented than a matching YAML key (block scalars and lists),
# or the inline value. $1 = key alternation, e.g. "run" or "script|before_script".
# Keys nested under a "defaults:" block (GitHub Actions shell/working-directory
# settings) are not commands and are skipped.
yaml_commands() {
  keys=$1; file=$2
  awk -v keys="$keys" '
    function ind(s) { match(s, /^ */); return RLENGTH }
    BEGIN { keyre = "^[ ]*(-[ ]+)?(" keys "):" }
    {
      if (inblock) {
        if ($0 ~ /^[ \t]*$/) next
        if (ind($0) > base) { l = $0; sub(/^ +/, "", l); print "    " l; next }
        inblock = 0
      }
      if ($0 ~ /^[ \t]*(#|$)/) next
      if (indef && ind($0) <= dbase) indef = 0
      if ($0 ~ /^[ ]*defaults:[ ]*$/) { indef = 1; dbase = ind($0); next }
      if (indef) next
      if ($0 ~ keyre) {
        v = $0; sub(keyre, "", v); sub(/^[ ]+/, "", v); sub(/[ ]+$/, "", v)
        if (v == "" || v ~ /^[|>][-+0-9]*$/) { inblock = 1; base = ind($0); if ($0 ~ /^[ ]*-[ ]/) base += 2 }
        else print "  " v
      }
    }' "$file"
}

capped() { awk -v max="$MAX_LINES" 'NR <= max { print } END { if (NR > max) printf "  ... (%d more lines)\n", NR - max }'; }

X="npx --no --"   # package-binary runner that refuses to download; refined below
echo "discover-checks: $(pwd)"

# ---------------------------------------------------- instruction files ------
DOCS=""
for f in AGENTS.md CLAUDE.md .claude/CLAUDE.md CONTRIBUTING.md .github/CONTRIBUTING.md docs/CONTRIBUTING.md DEVELOPMENT.md docs/development.md HACKING.md README.md; do
  [ -f "$f" ] && DOCS="$DOCS $f"
done
if [ -n "$DOCS" ]; then
  section "Contributor / agent docs (commands they mention)"
  for f in $DOCS; do
    grep -nE '(^|[`$ ])(make|just|task|npm|npx|pnpm|yarn|bun|bunx|deno|pytest|tox|nox|uv|poetry|hatch|ruff|mypy|cargo|go|gradle|\./gradlew|mvn|\./mvnw|dotnet|bundle|rake|rspec|composer|php|mix|swift|dart|flutter|pre-commit|cmake|ctest|bazel)[[:space:]]+[a-z]' "$f" 2>/dev/null |
      grep -iE 'test|lint|check|fmt|format|build|type|vet|verify|ci|analy[sz]e|spec|clippy|tsc' |
      head -n 15 | sed "s|^|  $f:|"
  done
fi

# ------------------------------------------------------------- JS / TS ------
if [ -f package.json ]; then
  PM=npm; RUN="npm run"; X="npx --no --"; PMSRC="from lockfile"
  if [ -f pnpm-lock.yaml ]; then PM=pnpm; RUN="pnpm run"; X="pnpm exec"
  elif [ -f yarn.lock ]; then PM=yarn; RUN="yarn run"; X="yarn"
  elif [ -f bun.lock ] || [ -f bun.lockb ]; then PM=bun; RUN="bun run"; X="bunx --no-install"
  elif [ ! -f package-lock.json ] && [ ! -f npm-shrinkwrap.json ]; then PMSRC="no lockfile found; check the packageManager field"
  fi
  section "package.json scripts (package manager: $PM, $PMSRC)"
  json_entries package.json scripts | awk -F'\t' -v run="$RUN" '
    NF >= 2 { printf "  %s %-22s -> %s\n", run, $1, substr($0, length($1) + 2) ; next }
    { print "  " $0 }' | capped
  TOOLS=""
  [ -f tsconfig.json ] && TOOLS="$TOOLS|types: $X tsc --noEmit   (projects using references: $X tsc -b)"
  any eslint.config.* .eslintrc* && TOOLS="$TOOLS|lint: $X eslint ."
  any .prettierrc* prettier.config.* && TOOLS="$TOOLS|format: $X prettier --check ."
  any biome.json biome.jsonc && TOOLS="$TOOLS|lint+format: $X biome check ."
  any jest.config.* && TOOLS="$TOOLS|tests: $X jest"
  any vitest.config.* vitest.workspace.* && TOOLS="$TOOLS|tests: $X vitest run   (plain 'vitest' watches in an interactive terminal)"
  any playwright.config.* && TOOLS="$TOOLS|e2e: $X playwright test"
  any cypress.config.* && TOOLS="$TOOLS|e2e: $X cypress run"
  if [ -n "$TOOLS" ]; then
    note "Tool configs present (prefer the scripts above when they wrap these; if a"
    note "tool is not a project dependency the command fails rather than downloading"
    note "it: record that check as not run instead of fetching the tool ad hoc):"
    printf '%s\n' "$TOOLS" | tr '|' '\n' | sed '/^$/d; s/^/    /'
  fi
fi

if [ -f deno.json ] || [ -f deno.jsonc ]; then
  section "Deno"
  note "deno task          (lists tasks)"
  note "deno check . | deno lint | deno fmt --check | deno test"
fi

MONO=""
[ -f pnpm-workspace.yaml ] && MONO="$MONO pnpm-workspace.yaml"
[ -f nx.json ] && MONO="$MONO nx.json"
[ -f turbo.json ] && MONO="$MONO turbo.json"
[ -f lerna.json ] && MONO="$MONO lerna.json"
[ -f rush.json ] && MONO="$MONO rush.json"
if [ -f package.json ] && grep -q '"workspaces"' package.json 2>/dev/null; then MONO="$MONO package.json#workspaces"; fi
if [ -n "$MONO" ]; then
  section "Monorepo tooling:$MONO"
  [ -f nx.json ] && note "affected only: $X nx affected --targets=lint,test,build --base=origin/main"
  [ -f turbo.json ] && note "affected only: $X turbo run lint test build --affected   (or --filter=...[origin/main])"
  note "Run checks for every package your change touches AND the packages that depend on them"
  note "(see references/discovering-checks.md section 3; per-package commands alone miss dependents)."
fi

# --------------------------------------------------------------- Python ------
PYPROJ=""
[ -f pyproject.toml ] && PYPROJ=pyproject.toml
if [ -n "$PYPROJ" ] || [ -f setup.py ] || [ -f setup.cfg ] || [ -f requirements.txt ] || [ -f tox.ini ] || [ -f noxfile.py ]; then
  PR=""
  if [ -f uv.lock ]; then PR="uv run "
  elif [ -f poetry.lock ]; then PR="poetry run "
  elif [ -f pdm.lock ]; then PR="pdm run "
  elif [ -f Pipfile.lock ] || [ -f Pipfile ]; then PR="pipenv run "
  fi
  section "Python${PR:+ (runner: ${PR% })}"
  if [ -n "$PYPROJ" ]; then
    TOOLS=$(grep -oE '^\[tool\.[A-Za-z0-9_-]+' "$PYPROJ" | sed 's/^\[tool\.//' | sort -u | tr '\n' ' ')
    [ -n "$TOOLS" ] && note "[tool.*] sections in pyproject.toml: $TOOLS"
    # Task-runner tables: print their keys.
    for tbl in 'tool[.]poe[.]tasks' 'tool[.]pdm[.]scripts' 'tool[.]taskipy[.]tasks' 'tool[.]hatch[.]envs[.][A-Za-z0-9_-]+[.]scripts'; do
      awk -v tbl="$tbl" '
        BEGIN { t = "^\\[" tbl "\\]" }
        $0 ~ t { on = 1; hdr = $0; next }
        /^\[/ { on = 0 }
        on && /^[A-Za-z0-9_."-]+[ ]*=/ { k = $0; sub(/[ ]*=.*/, "", k); printf "  %s  task: %s\n", hdr, k }
      ' "$PYPROJ"
    done | capped
    grep -q '^\[project\.scripts\]' "$PYPROJ" && note "[project.scripts] defines console entry points: check new CLIs are listed there."
  fi
  for f in setup.cfg tox.ini; do
    [ -f "$f" ] && grep -oE '^\[(tool:pytest|flake8|mypy|isort|pycodestyle|pylint|coverage:[a-z]+)\]' "$f" | sed "s|^|  $f: |"
  done
  [ -f tox.ini ] && note "tox list     then: tox run -e ENVNAME    (tox 3: tox -l / tox -e ENVNAME)"
  [ -f noxfile.py ] && note "nox --list   then: nox -s SESSION"
  hint=""
  { [ -f pytest.ini ] || grep -qs 'tool.pytest' pyproject.toml || grep -qs 'tool:pytest' setup.cfg || [ -f conftest.py ] || [ -d tests ]; } && hint="$hint|tests: ${PR}pytest"
  { [ -f ruff.toml ] || [ -f .ruff.toml ] || grep -qs '^\[tool\.ruff' pyproject.toml; } && hint="$hint|lint: ${PR}ruff check .|format: ${PR}ruff format --check ."
  grep -qs '^\[tool\.black' pyproject.toml && hint="$hint|format: ${PR}black --check ."
  { [ -f mypy.ini ] || [ -f .mypy.ini ] || grep -qs '^\[tool\.mypy' pyproject.toml || grep -qs '^\[mypy' setup.cfg; } && hint="$hint|types: ${PR}mypy   (add the package path if no 'files' is configured)"
  { [ -f pyrightconfig.json ] || grep -qs '^\[tool\.pyright' pyproject.toml; } && hint="$hint|types: ${PR}pyright"
  [ -f .flake8 ] && hint="$hint|lint: ${PR}flake8"
  [ -f manage.py ] && hint="$hint|django: ${PR}python manage.py check   and   ${PR}python manage.py makemigrations --check --dry-run"
  [ -n "$hint" ] && printf '%s\n' "$hint" | tr '|' '\n' | sed '/^$/d; s/^/  /'
fi

# ------------------------------------------------------ other ecosystems -----
if [ -f Cargo.toml ]; then
  section "Rust"
  note "cargo build --all-targets | cargo test | cargo clippy --all-targets -- -D warnings | cargo fmt --check"
fi
if [ -f go.mod ] || [ -f go.work ]; then
  section "Go"
  note "go build ./... | go vet ./... | go test ./...   (add -race for concurrent code)"
  note "format: test -z \"\$(gofmt -l .)\"   (gofmt -l lists unformatted files but exits 0: read its output)"
  f=$(first_existing .golangci.yml .golangci.yaml .golangci.toml .golangci.json) && note "golangci-lint run   ($f present)"
fi
if any gradlew build.gradle build.gradle.kts settings.gradle settings.gradle.kts; then
  section "Gradle"
  G=gradle; [ -f gradlew ] && G=./gradlew
  note "$G check   (runs tests + verification tasks)   |   $G build   (check + assemble)   |   $G tasks --all   (list)"
fi
if [ -f pom.xml ]; then
  section "Maven"
  M=mvn; [ -f mvnw ] && M=./mvnw
  note "$M verify   (compile, test, integration-test, checks bound to verify)"
fi
if any ./*.sln ./*.slnx ./*.csproj ./*.fsproj ./*/*.csproj ./*/*.fsproj; then
  section ".NET"
  note "dotnet build | dotnet test | dotnet format --verify-no-changes"
fi
if [ -f Gemfile ]; then
  section "Ruby"
  [ -f Rakefile ] && note "bundle exec rake -T   (list tasks)"
  [ -d spec ] && note "bundle exec rspec"
  [ -d test ] && [ -f Rakefile ] && note "bundle exec rake test"
  [ -f .rubocop.yml ] && note "bundle exec rubocop"
  { [ -f bin/rails ] || [ -f config/application.rb ]; } && note "bin/rails routes   (confirm new routes are registered)"
fi
if [ -f composer.json ]; then
  section "PHP (composer scripts)"
  json_entries composer.json scripts | awk -F'\t' '
    NF >= 2 { printf "  composer run-script %-18s -> %s\n", $1, substr($0, length($1) + 2); next }
    { print "  " $0 }' | capped
  f=$(first_existing phpunit.xml phpunit.xml.dist) && note "vendor/bin/phpunit   ($f present)"
  f=$(first_existing phpstan.neon phpstan.neon.dist phpstan.dist.neon) && note "vendor/bin/phpstan analyse   ($f present)"
  f=$(first_existing psalm.xml psalm.xml.dist) && note "vendor/bin/psalm   ($f present)"
  f=$(first_existing .php-cs-fixer.php .php-cs-fixer.dist.php) && note "vendor/bin/php-cs-fixer fix --dry-run --diff   ($f present)"
  [ -f artisan ] && note "php artisan route:list   (confirm new routes are registered)"
fi
if [ -f mix.exs ]; then
  section "Elixir"
  note "mix compile --warnings-as-errors | mix format --check-formatted | mix test"
fi
if [ -f Package.swift ]; then
  section "Swift"
  note "swift build | swift test"
fi
if [ -f pubspec.yaml ]; then
  section "Dart / Flutter"
  if grep -qE '^[[:space:]]+sdk:[[:space:]]*flutter' pubspec.yaml; then
    note "flutter analyze | flutter test | dart format --output=none --set-exit-if-changed ."
  else
    note "dart analyze | dart test | dart format --output=none --set-exit-if-changed ."
  fi
fi
if [ -f CMakeLists.txt ]; then
  section "CMake"
  note "cmake -S . -B build && cmake --build build && ctest --test-dir build   (ctest --test-dir needs CMake 3.20+)"
fi
if [ -f MODULE.bazel ] || [ -f WORKSPACE ] || [ -f WORKSPACE.bazel ]; then
  section "Bazel"
  note "bazel build //... | bazel test //...   (narrow to the affected targets in large repos)"
fi

# -------------------------------------------------------- task runners -------
MK=$(first_existing GNUmakefile Makefile makefile) && {
  section "Make targets ($MK)"
  grep -E '^[A-Za-z0-9][A-Za-z0-9_./-]*[[:space:]]*::?([^=]|$)' "$MK" |
    awk '{ t = $0; sub(/[ \t]*::?.*/, "", t); d = ""; if (match($0, /##[ ]*/)) d = substr($0, RSTART + RLENGTH)
           if (!(t in seen)) { seen[t] = 1; if (d != "") printf "  make %-20s # %s\n", t, d; else printf "  make %s\n", t } }' | capped
  grep -qE '^include[[:space:]]' "$MK" && note "(the Makefile includes other files; targets defined there are not listed)"
}
JF=$(first_existing justfile Justfile .justfile) && {
  section "just recipes ($JF)  - full list: just --list"
  grep -E '^@?[A-Za-z0-9_-]+([[:space:]][^:]*)?:([^=]|$)' "$JF" | grep -vE '^(set|alias|export|import|mod)[[:space:]]' |
    sed -E 's/^@?([A-Za-z0-9_-]+).*/  just \1/' | capped
}
TF=$(first_existing Taskfile.yml Taskfile.yaml taskfile.yml taskfile.yaml) && {
  section "Task targets ($TF)  - full list: task --list-all"
  awk '
    /^tasks:/ { on = 1; next }
    on && /^[^ \t#]/ { on = 0 }
    on && /^[ ]+[A-Za-z0-9_:.-]+:[ ]*$/ {
      match($0, /^ +/); if (lvl == 0) lvl = RLENGTH
      if (RLENGTH == lvl) { t = $0; sub(/^ +/, "", t); sub(/:.*$/, "", t); print "  task " t }
    }' "$TF" | capped
}

# ------------------------------------------------------------ git hooks ------
HOOKS=0
if [ -f .pre-commit-config.yaml ]; then
  [ $HOOKS -eq 0 ] && section "Git hooks"; HOOKS=1
  note "pre-commit run --from-ref \"\$(git merge-base origin/main HEAD)\" --to-ref HEAD   (your committed range;"
  note "  add --files PATH... for uncommitted ones). Fixer hooks rewrite files: run git status --short"
  note "  afterwards and revert edits to files outside your change. --all-files touches the whole repo."
  grep -E '^[[:space:]]*-[[:space:]]*id:' .pre-commit-config.yaml | sed -E 's/^[[:space:]]*-[[:space:]]*id:[[:space:]]*/    hook: /' | capped
fi
f=$(first_existing lefthook.yml .lefthook.yml lefthook.yaml .lefthook.yaml) && {
  [ $HOOKS -eq 0 ] && section "Git hooks"; HOOKS=1
  note "lefthook run pre-commit   ($f; also check pre-push)"
}
if [ -d .husky ]; then
  [ $HOOKS -eq 0 ] && section "Git hooks"; HOOKS=1
  for h in .husky/*; do
    [ -f "$h" ] || continue
    note "$h:"; grep -vE '^[[:space:]]*(#|$)|husky\.sh' "$h" | sed 's/^/      /' | head -n 10
  done
fi
HP=$(git config --get core.hooksPath 2>/dev/null) && [ -n "$HP" ] && {
  [ $HOOKS -eq 0 ] && section "Git hooks"; HOOKS=1
  note "core.hooksPath = $HP  (read those scripts: they are what runs on commit/push)"
}

# ------------------------------------------------------------------- CI ------
if any .github/workflows/*.yml .github/workflows/*.yaml .github/actions/*/action.yml .github/actions/*/action.yaml; then
  for wf in .github/workflows/*.yml .github/workflows/*.yaml .github/actions/*/action.yml .github/actions/*/action.yaml; do
    [ -f "$wf" ] || continue
    out=$(yaml_commands run "$wf")
    local_uses=$(grep -E '^[[:space:]]*(-[[:space:]]+)?uses:[[:space:]]*["'"'"']?\./' "$wf" | sed -E 's/^[^:]*uses:[[:space:]]*//; s/["'"'"']//g' | sort -u)
    [ -z "$out" ] && [ -z "$local_uses" ] && continue
    section "CI: $wf (run steps)"
    [ -n "$out" ] && printf '%s\n' "$out" | capped
    [ -n "$local_uses" ] && printf '%s\n' "$local_uses" | sed 's/^/  also read (local action or reusable workflow): /'
  done
fi
[ -f .gitlab-ci.yml ] && { section "CI: .gitlab-ci.yml (script steps)"; yaml_commands 'before_script|script|after_script' .gitlab-ci.yml | capped; }
[ -f .circleci/config.yml ] && { section "CI: .circleci/config.yml (run steps)"; yaml_commands 'run|command' .circleci/config.yml | capped; }
f=$(first_existing azure-pipelines.yml azure-pipelines.yaml) && { section "CI: $f"; yaml_commands 'script|bash|pwsh|powershell' "$f" | capped; }
[ -f bitbucket-pipelines.yml ] && { section "CI: bitbucket-pipelines.yml"; yaml_commands 'script' bitbucket-pipelines.yml | capped; }
f=$(first_existing .buildkite/pipeline.yml .buildkite/pipeline.yaml) && { section "CI: $f"; yaml_commands 'command|commands' "$f" | capped; }

# Services CI starts for tests (databases, caches, brokers). Integration tests
# that need them may skip or fail locally until you start the same services.
SVC=""
for f in .github/workflows/*.yml .github/workflows/*.yaml .gitlab-ci.yml; do
  [ -f "$f" ] || continue
  s=$(yaml_commands services "$f" | grep -E 'image:|^    - [^0-9]' | sed -E 's/^ +//; s/^- //; s/^(name|image):[[:space:]]*//; s/["'"'"']//g' | sort -u | tr '\n' ' ')
  [ -n "$s" ] && SVC="$SVC|$f: $s"
done
if [ -f .circleci/config.yml ]; then
  s=$(yaml_commands docker .circleci/config.yml | grep -E 'image:' | sed -E 's/^ +//; s/^- //; s/^image:[[:space:]]*//; s/["'"'"']//g' | sort -u | tr '\n' ' ')
  [ -n "$s" ] && SVC="$SVC|.circleci/config.yml (docker images; extra images are services): $s"
fi
if [ -n "$SVC" ]; then
  section "CI services (start these locally before integration tests, e.g. docker compose up -d)"
  printf '%s\n' "$SVC" | tr '|' '\n' | sed '/^$/d; s/^/  /'
fi
[ -f Jenkinsfile ] && { section "CI: Jenkinsfile (sh/bat steps)"; grep -nE '^[[:space:]]*(sh|bat|pwsh)[[:space:](]' Jenkinsfile | sed 's/^/  /' | capped; }
for f in .travis.yml .drone.yml; do [ -f "$f" ] && { section "CI: $f"; yaml_commands 'script|commands' "$f" | capped; }; done

# --------------------------------------------------- nested project roots ----
NESTED=$(find . -mindepth 2 -maxdepth 4 \
  \( -name node_modules -o -name .git -o -name vendor -o -name dist -o -name build -o -name target -o -name .venv -o -name venv -o -name .tox \) -prune -o \
  \( -name package.json -o -name pyproject.toml -o -name go.mod -o -name Cargo.toml -o -name pom.xml -o -name build.gradle -o -name build.gradle.kts -o -name composer.json -o -name Gemfile \) -print 2>/dev/null | sort | head -n 25)
if [ -n "$NESTED" ]; then
  section "Nested project roots (run discover-checks.sh in the ones your change touches)"
  printf '%s\n' "$NESTED" | sed 's/^/  /'
fi

if [ "$FOUND" -eq 0 ]; then
  echo
  echo "No manifests, task runners, hooks or CI config found here. Check you are at the"
  echo "project root, then ask the user how they build and test this project."
fi
exit 0
