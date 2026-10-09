#!/usr/bin/env bash
# scan-diff.sh - flag common leftovers and weakened checks in a change.
#
# Usage: scan-diff.sh [BASE_REF]
#        scan-diff.sh --selftest   (check this script against planted leftovers)
#        scan-diff.sh -h | --help
#
#   BASE_REF  Compare against the merge-base of HEAD and this ref. Default: the
#             first of origin/HEAD, origin/main, origin/master, main, master that
#             exists; falls back to HEAD (uncommitted changes only).
#
# Scans committed-since-base + staged + unstaged changes to tracked files, plus
# untracked (not ignored) files. Line rules look only at ADDED lines, so
# pre-existing code never shows up; the test and check-config sections also
# look at deleted files and removed assertions. Read-only: runs git, grep, awk.
#
# Output is a review list, not a verdict. Every hit needs a decision (remove it,
# or keep it and be able to say why). Secret-like values are never printed: a
# secret hit shows location and rule name only, and any other section that hits
# the same line hides its content too. A clean result is not a secret-scan
# pass; use a dedicated scanner when the repo has one.
#
# Requires git and a POSIX shell toolset (bash, grep -E, awk, sort).
# Exit codes: 0 nothing flagged, 1 something flagged for review, 2 usage/git error.

set -u

MAX_PER_SECTION=40
LARGE_FILE_BYTES=1048576
TAB=$(printf '\t')
EMPTY_TREE=4b825dc642cb6eb9a060e54bf8d69288fbee4904

# --selftest: builds throwaway git repos with planted leftovers and checks that
# this script never prints a secret value (even when the line matches another
# rule), reports each planted secret shape, weakened check and removed test,
# and exits 1 when something is flagged and 0 on a clean change.
selftest() {
  SCAN="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
  SH=$(command -v bash || echo sh)   # scan-diff.sh also runs under a POSIX sh
  ST_WORK=$(mktemp -d "${TMPDIR:-/tmp}/scan-diff-selftest.XXXXXX") || return 2
  FAILS=0
  G="git -c user.name=t -c user.email=t@example.com -c init.defaultBranch=main"

  pass() { printf 'PASS  %s\n' "$1"; }
  fail() { printf 'FAIL  %s\n' "$1"; FAILS=$((FAILS + 1)); }
  expect_in() { if printf '%s' "$OUT" | grep -qF -- "$2"; then pass "$1"; else fail "$1 (missing: $2)"; fi; }
  expect_not_in() { if printf '%s' "$OUT" | grep -qF -- "$2"; then fail "$1 (leaked: $2)"; else pass "$1"; fi; }

  # Fake credentials assembled at runtime so this file itself holds no
  # secret-shaped literal.
  GH="ghp_$(printf 'a%.0s' $(seq 1 36))"
  AWS="AKIA$(printf 'B%.0s' $(seq 1 16))"
  STRIPE="sk_live_$(printf 'c%.0s' $(seq 1 24))"
  GLPAT="glpat-$(printf 'd%.0s' $(seq 1 20))"
  YAMLPW="Sup3rSecretValue9"

  # ---------------------------------------------------------- dirty repo ------
  R="$ST_WORK/dirty"
  mkdir -p "$R/tests" "$R/.github/workflows"
  cd "$R" || return 2
  $G init -q
  printf 'def test_one():\n    assert 1\n    assert 2\n' >tests/test_a.py
  printf 'def test_x():\n    assert True\n' >tests/test_gone.py
  printf '{\n  "compilerOptions": {\n    "strict": true\n  }\n}\n' >tsconfig.json
  printf 'jobs:\n  t:\n    steps:\n      - run: npm test\n' >.github/workflows/ci.yml
  $G add -A && $G commit -qm base

  printf 'def test_one():\n    pass\n' >tests/test_a.py
  $G rm -q tests/test_gone.py
  printf '{\n  "compilerOptions": {\n    "strict": false\n  }\n}\n' >tsconfig.json
  printf 'jobs:\n  t:\n    steps:\n      - run: npm test\n        continue-on-error: true\n' >.github/workflows/ci.yml
  {
    printf 'console.log("token", "%s");\n' "$GH"
    printf '// const stripeKey = "%s";\n' "$STRIPE"
    printf '// TODO rotate %s\n' "$AWS"
    printf 'const token = "%s";\n' "$GLPAT"
  } >app.js
  printf 'password: %s\n' "$YAMLPW" >config.yml

  OUT=$("$SH" "$SCAN" 2>&1); RC=$?
  if [ "$RC" -eq 1 ]; then pass "dirty change exits 1"; else fail "dirty change exits 1 (got $RC)"; fi
  for v in "$GH" "$AWS" "$STRIPE" "$GLPAT" "$YAMLPW"; do
    expect_not_in "secret value never printed" "$v"
  done
  expect_in "github token reported" "app.js:1: github-token"
  expect_in "stripe key reported" "app.js:2: stripe-live-key"
  expect_in "aws key reported" "app.js:3: aws-access-key-id"
  expect_in "gitlab token reported" "app.js:4: gitlab-token"
  expect_in "unquoted YAML password reported" "config.yml:1: credential-in-config"
  expect_in "debug line content hidden" "app.js:1: [content hidden"
  expect_in "non-blocking CI step reported" "continue-on-error: true"
  expect_in "relaxed strictness reported" '"strict": false'
  expect_in "check config listed" "tsconfig.json: changed"
  expect_in "deleted test reported" "tests/test_gone.py: test file deleted"
  expect_in "shrunk test reported" "tests/test_a.py: 2 test/assertion lines removed, 0 added"

  # ---------------------------------------------------------- clean repo ------
  R="$ST_WORK/clean"
  mkdir -p "$R"
  cd "$R" || return 2
  $G init -q
  printf 'def add(a, b):\n    return a + b\n' >calc.py
  $G add -A && $G commit -qm base
  printf 'def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n' >calc.py
  OUT=$("$SH" "$SCAN" 2>&1); RC=$?
  if [ "$RC" -eq 0 ]; then pass "clean change exits 0"; else fail "clean change exits 0 (got $RC)"; printf '%s\n' "$OUT"; fi

  rm -rf "$ST_WORK"
  echo
  [ "$FAILS" -eq 0 ] && { echo "selftest: all checks passed"; return 0; }
  echo "selftest: $FAILS check(s) failed"
  return 1
}

case "${1:-}" in
  -h|--help) awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; exit 0 ;;
  --selftest) selftest; exit $? ;;
esac

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "scan-diff: not inside a git work tree" >&2
  exit 2
fi
cd "$(git rev-parse --show-toplevel)" || exit 2

# ---------------------------------------------------------------- base ref ---
BASE=""
BASE_LABEL=""
if [ -n "${1:-}" ]; then
  if ! git rev-parse --verify --quiet "${1}^{commit}" >/dev/null; then
    echo "scan-diff: unknown ref '$1'" >&2
    exit 2
  fi
  BASE=$(git merge-base HEAD "$1" 2>/dev/null || git rev-parse "${1}^{commit}")
  BASE_LABEL="merge-base with $1"
else
  for cand in origin/HEAD origin/main origin/master main master; do
    if git rev-parse --verify --quiet "${cand}^{commit}" >/dev/null; then
      if mb=$(git merge-base HEAD "$cand" 2>/dev/null); then
        BASE=$mb
        BASE_LABEL="merge-base with $cand"
        break
      fi
    fi
  done
  if [ -z "$BASE" ]; then
    if git rev-parse --verify --quiet HEAD >/dev/null; then
      BASE=$(git rev-parse HEAD)
      BASE_LABEL="HEAD (uncommitted changes only)"
    else
      BASE=$EMPTY_TREE
      BASE_LABEL="empty tree (no commits yet)"
    fi
  fi
fi

WORK=$(mktemp -d "${TMPDIR:-/tmp}/scan-diff.XXXXXX") || exit 2
trap 'rm -rf "$WORK"' EXIT
ADDED="$WORK/added.tsv"          # path<TAB>line<TAB>content, one row per added line
SECRET_HITS="$WORK/secrets.tsv"  # path<TAB>line<TAB>rule
: >"$ADDED"
: >"$SECRET_HITS"

GIT="git -c core.quotePath=false"

# Paths whose content is machine-generated and too noisy to scan line by line.
# Keep in sync with NOISE_RE below.
is_noise_path() {
  case "$1" in
    *package-lock.json|*npm-shrinkwrap.json|*yarn.lock|*pnpm-lock.yaml|*bun.lock|*bun.lockb) return 0 ;;
    *poetry.lock|*uv.lock|*Pipfile.lock|*pdm.lock|*Cargo.lock|*go.sum|*Gemfile.lock|*composer.lock) return 0 ;;
    *mix.lock|*Package.resolved|*pubspec.lock|*packages.lock.json|*gradle.lockfile) return 0 ;;
    *.min.js|*.min.css|*.map|*.svg) return 0 ;;
  esac
  return 1
}

# Same list as an awk regex (no interval expressions, so any POSIX awk works).
NOISE_RE='(package-lock[.]json|npm-shrinkwrap[.]json|yarn[.]lock|pnpm-lock[.]yaml|bun[.]lockb?|poetry[.]lock|uv[.]lock|Pipfile[.]lock|pdm[.]lock|Cargo[.]lock|go[.]sum|Gemfile[.]lock|composer[.]lock|mix[.]lock|Package[.]resolved|pubspec[.]lock|packages[.]lock[.]json|gradle[.]lockfile|[.]min[.]js|[.]min[.]css|[.]map|[.]svg)$'

# Files that configure a check (lint, types, tests, coverage, hooks, CI).
# Editing one is fine; editing one to switch a check off is not. No trailing
# anchor: callers add "$" (path lists) or a TAB (the added-lines table).
CHECK_CFG_RE='(^|/)([.]eslintrc[^/]*|eslint[.]config[.][^/]*|[.]eslintignore|biome[.]jsonc?|tsconfig[^/]*[.]json|jsconfig[.]json|package[.]json|pyproject[.]toml|setup[.]cfg|tox[.]ini|pytest[.]ini|[.]coveragerc|[.]nycrc[^/]*|[.]?codecov[.]ya?ml|jest[.]config[.][^/]*|vitest[.]config[.][^/]*|vitest[.]workspace[.][^/]*|[.]mocharc[^/]*|karma[.]conf[.][^/]*|playwright[.]config[.][^/]*|ruff[.]toml|[.]ruff[.]toml|mypy[.]ini|[.]mypy[.]ini|[.]flake8|[.]?pylintrc|pyrightconfig[.]json|[.]golangci[.][^/]*|clippy[.]toml|[.]clippy[.]toml|rustfmt[.]toml|[.]rubocop[^/]*[.]yml|phpunit[.]xml(\.dist)?|phpstan[^/]*[.]neon(\.dist)?|psalm[.]xml(\.dist)?|[.]prettierrc[^/]*|[.]prettierignore|[.]stylelintrc[^/]*|[.]swiftlint[.]yml|analysis_options[.]yaml|detekt[^/]*[.]yml|checkstyle[^/]*[.]xml|[.]editorconfig|[.]pre-commit-config[.]yaml|[.]?lefthook[.]ya?ml|Makefile|GNUmakefile|justfile|Taskfile[.]ya?ml|Jenkinsfile|[.]gitlab-ci[.]yml|azure-pipelines[.]ya?ml|bitbucket-pipelines[.]yml|[.]gitleaks[.]toml|[.]gitleaksignore|[.]secrets[.]baseline)|(^|/)[.]github/workflows/[^/]+|(^|/)[.]github/actions/.+|(^|/)[.]circleci/config[.]yml|(^|/)[.]buildkite/[^/]+|(^|/)[.]husky/[^/]+'

# Test files, by common naming conventions.
TEST_PATH_RE='(^|/)(tests?|__tests__|specs?|e2e)/|(^|/)test_[^/]*[.]py$|_test[.](py|go|rb|exs|dart)$|[._-](test|spec|e2e)[.][A-Za-z0-9]+$|Tests?[.](java|kt|kts|cs|swift|php|scala|groovy)$|_spec[.]rb$'

# Lines that state a test or an assertion.
ASSERT_RE='assert|expect[(]|[.]should|(^|[^A-Za-z0-9_.])(it|test|describe|scenario)([.]each)?[(]|def test_|func Test|@Test|#[[]test[]]|t[.](Error|Fatal)f?[(]'

# ------------------------------------------------- collect added lines -------
$GIT diff -U0 --no-color --no-ext-diff --src-prefix=a/ --dst-prefix=b/ "$BASE" -- 2>/dev/null |
  awk -v OFS="$TAB" -v NOISE="$NOISE_RE" '
    /^diff --git / { hdr = 1; next }
    hdr && /^\+\+\+ / {
      f = substr($0, 5)
      sub(/\t$/, "", f)   # git appends a TAB to header paths that contain spaces
      if (f == "/dev/null") { f = "" } else { sub(/^b\//, "", f) }
      next
    }
    /^@@ / {
      hdr = 0
      s = $0
      sub(/^@@ -[0-9,]+ \+/, "", s)
      sub(/[ ,].*$/, "", s)
      ln = s + 0
      next
    }
    /^\+/ {
      if (f != "" && f !~ NOISE) print f, ln, substr($0, 2)
      ln++
      next
    }
  ' >>"$ADDED"

UNTRACKED="$WORK/untracked.txt"
$GIT ls-files --others --exclude-standard >"$UNTRACKED" 2>/dev/null
while IFS= read -r f; do
  [ -f "$f" ] || continue
  is_noise_path "$f" && continue
  size=$(wc -c <"$f" | tr -d ' ')
  [ "$size" -gt "$LARGE_FILE_BYTES" ] && continue   # reported under FILES instead
  grep -Iq . "$f" 2>/dev/null || continue            # skip binary and empty files
  awk -v OFS="$TAB" -v p="$f" '{ print p, NR, $0 }' "$f" >>"$ADDED"
done <"$UNTRACKED"

# ------------------------------------------------------------- matching ------
# Match PATTERN (ERE) anywhere in the content column. The TAB before the content
# is left unconsumed so a "not preceded by an identifier" guard can match it.
content_grep() { grep -E -- "^[^$TAB]*${TAB}[0-9]+.*($1)" "$ADDED" 2>/dev/null; }
content_grep_i() { grep -iE -- "^[^$TAB]*${TAB}[0-9]+.*($1)" "$ADDED" 2>/dev/null; }
# Same, restricted to files whose path matches PATHRE (an ERE anchored at the
# end of the path column).
content_grep_in() { grep -E -- "^[^$TAB]*($1)${TAB}[0-9]+.*($2)" "$ADDED" 2>/dev/null; }
content_grep_in_i() { grep -iE -- "^[^$TAB]*($1)${TAB}[0-9]+.*($2)" "$ADDED" 2>/dev/null; }
# Match PATTERN at the very start of the content.
start_grep() { grep -E -- "^[^$TAB]*${TAB}[0-9]+$TAB($1)" "$ADDED" 2>/dev/null; }
start_grep_in() { grep -E -- "^[^$TAB]*($1)${TAB}[0-9]+$TAB($2)" "$ADDED" 2>/dev/null; }

NB='[^A-Za-z0-9_]'    # "not preceded by an identifier character"
NBD='[^A-Za-z0-9_.]'  # ... nor by a dot (excludes obj.method calls)
Q="[\"']"

# ------------------------------------------- secrets (computed first) --------
# Computed before anything is printed so that every section can hide the
# content of a line that also looks like a secret.
SECRET_RULES="
private-key|-----BEGIN ([A-Z0-9]+ )*PRIVATE KEY-----
aws-access-key-id|(AKIA|ASIA)[A-Z0-9]{16}
github-token|(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}
gitlab-token|glpat-[A-Za-z0-9_-]{20,}
npm-token|${NB}npm_[A-Za-z0-9]{36}
slack-token|xox[abposr]-[A-Za-z0-9-]{10,}
slack-webhook|hooks[.]slack[.]com/services/[A-Za-z0-9/_-]{20,}
stripe-live-key|(sk|rk)_live_[A-Za-z0-9]{20,}
ai-provider-key|${NB}sk-((proj|ant|svcacct|admin)-[A-Za-z0-9_-]{20,}|[A-Za-z0-9]{40,})
google-api-key|AIza[0-9A-Za-z_-]{35}
jwt|eyJ[A-Za-z0-9_-]{10,}[.]eyJ[A-Za-z0-9_-]{10,}[.][A-Za-z0-9_-]{10,}
bearer-token|[Bb]earer[[:space:]]+[A-Za-z0-9._~+/-]{20,}
credentials-in-url|[A-Za-z][A-Za-z0-9+.-]*://[^/[:space:]:@]+:[^/[:space:]:@\$]+@
"
# Quoted value assigned to a credential-like name, in any file.
SECRET_KEYS='password|passwd|pwd|secret|secret[_-]?key|api[_-]?key|access[_-]?key|auth[_-]?token|access[_-]?token|client[_-]?secret|private[_-]?key'
GENERIC_SECRET="($SECRET_KEYS)[A-Za-z0-9_]*$Q?[[:space:]]*[:=]+[[:space:]]*${Q}[^\"'[:space:]]{8,}$Q"
GENERIC_TOKEN="token([_-][A-Za-z0-9_]*)?$Q?[[:space:]]*[:=]+[[:space:]]*${Q}[^\"'[:space:]]{8,}$Q"
# Unquoted value in config-like files (YAML, INI, properties, TOML, .env,
# compose files, Dockerfiles, shell). Values that start with $ < { % / . [ ! #
# are references, templates, paths, or comments and are skipped.
CONFIG_PATH_RE='[.](ya?ml|ini|properties|toml|conf|cfg|env|envrc|sh|bash)|(^|/)[.]env[^/]*|(^|/)(docker-)?compose[^/]*|(^|/)Dockerfile[^/]*'
UNQUOTED_SECRET="($SECRET_KEYS|token)([_-][A-Za-z0-9_-]*)?[[:space:]]*[:=][[:space:]]*[^[:space:]\"'\$<{%/.[!#][^[:space:]]{7,}"
{
  printf '%s\n' "$SECRET_RULES" | while IFS= read -r rule; do
    [ -z "$rule" ] && continue
    name=${rule%%|*}
    re=${rule#*|}
    content_grep "$re" | awk -F"$TAB" -v OFS="$TAB" -v r="$name" '{ print $1, $2, r }'
  done
  content_grep_i "$GENERIC_SECRET|$GENERIC_TOKEN" |
    awk -F"$TAB" -v OFS="$TAB" '{ print $1, $2, "hardcoded-credential-assignment" }'
  content_grep_in_i "$CONFIG_PATH_RE" "$UNQUOTED_SECRET" |
    grep -viE -- "[:=][[:space:]]*(https?://|(true|false|null|none|changeme|example)([[:space:]]|$))" |
    awk -F"$TAB" -v OFS="$TAB" '{ print $1, $2, "credential-in-config" }'
} | sort -t "$TAB" -k1,1 -k2,2n -u >"$SECRET_HITS"
# Keep one rule name per location.
awk -F"$TAB" -v OFS="$TAB" '!seen[$1 FS $2]++' "$SECRET_HITS" >"$WORK/secrets.dedup" &&
  mv "$WORK/secrets.dedup" "$SECRET_HITS"

# ------------------------------------------------------------- reporting -----
FLAG_FILE="$WORK/flagged"   # sections run in pipeline subshells, so flag via a file

# print_hits TITLE NOTE [show_content]  (reads matching TSV rows on stdin)
# show_content: "yes" prints the line content (hidden if the same location is
# a secret hit); "rule" prints column 3 as-is (used for secret rule names and
# file reasons).
print_hits() {
  title=$1; note=$2; show=${3:-yes}
  hits="$WORK/hits"
  cat >"$hits"
  n=$(wc -l <"$hits" | tr -d ' ')
  [ "$n" -eq 0 ] && return 0
  : >"$FLAG_FILE"
  printf '\n## %s (%s)\n%s\n' "$title" "$n" "$note"
  head -n "$MAX_PER_SECTION" "$hits" | awk -F"$TAB" -v show="$show" -v sf="$SECRET_HITS" '
    FILENAME == sf { secret[$1 FS $2] = 1; next }
    {
      c = ""
      for (i = 3; i <= NF; i++) c = c (i > 3 ? "\t" : "") $i
      sub(/^[ \t]+/, "", c)
      if (show == "yes" && (($1 FS $2) in secret)) c = "[content hidden: this line also matched a secret rule]"
      if (length(c) > 160) c = substr(c, 1, 157) "..."
      if ($2 == "-") printf "  %s: %s\n", $1, c
      else printf "  %s:%s: %s\n", $1, $2, c
    }' "$SECRET_HITS" -
  [ "$n" -gt "$MAX_PER_SECTION" ] && printf '  ... and %s more\n' "$((n - MAX_PER_SECTION))"
  return 0
}

echo "scan-diff: comparing working tree against $BASE_LABEL ($(printf '%.12s' "$BASE"))"
echo "added lines scanned: $(wc -l <"$ADDED" | tr -d ' ')   untracked files: $(wc -l <"$UNTRACKED" | tr -d ' ')"

# 1. Merge-conflict markers.
start_grep '<<<<<<< |>>>>>>> ' |
  print_hits "CONFLICT MARKERS" "Unresolved merge conflict. Must be fixed."

# 2. Secret-like values (location + rule name only).
print_hits "POSSIBLE SECRETS" "Values not shown. Confirm each is a fake/test value or move it to config/secret storage. A real credential that was ever committed must be rotated, not just deleted." rule <"$SECRET_HITS"

# 3. Focused or skipped tests.
FOCUS_RE="${NB}(it|test|describe|context|suite)\.(only|skip)\(|${NBD}(fit|fdescribe|fcontext|xit|xdescribe|xcontext|xtest)\(|@pytest\.mark\.(skip|skipif|xfail)|pytest\.skip\(|@unittest\.skip|${NB}t\.Skip(f|Now)?\(|#\[ignore\]|@Disabled|@Ignore([^A-Za-z]|$)|markTestSkipped\(|markTestIncomplete\(|[,[:space:]]focus:[[:space:]]*true|[[:space:]]:focus[[:space:]]*(do|,|$)|[{,][[:space:]]*(skip|todo|only):[[:space:]]*true"
content_grep "$FOCUS_RE" |
  print_hits "FOCUSED / SKIPPED TESTS" "A focused test silently disables the rest of the suite; a new skip hides a failure. Remove, or justify in the report."

# 4. Debugger statements and debug dumps.
DEBUG_RE="console\.(log|debug|trace|dir|table)\(|${NBD}debugger([[:space:];]|$)|i?pdb\.set_trace\(|import i?pdb|${NBD}breakpoint\(\)|binding\.(pry|irb|break)|${NB}byebug([^A-Za-z0-9_]|$)|var_dump\(|print_r\(|${NBD}dd\(|dbg!\(|\.printStackTrace\(\)|System\.(out|err)\.print"
content_grep "$DEBUG_RE" |
  print_hits "DEBUG STATEMENTS" "Leftover debugging. Remove unless it is intentional, structured logging."

# 5. Bare prints (often legitimate in CLIs and scripts).
PRINT_RE="print\(|fmt\.Print(ln|f)?\(|e?println!\(|puts[[:space:]]"
start_grep_in '\.(py|go|rs|rb)' "[[:space:]]*($PRINT_RE)" |
  print_hits "BARE PRINTS (low confidence)" "Fine in a CLI or script; suspicious in library, server, or test code. Use the project logger if this is meant to stay."

# 6. New lint/type/coverage suppressions.
SUPPRESS_RE="eslint-disable|biome-ignore|@ts-ignore|@ts-nocheck|@ts-expect-error|#[[:space:]]*type:[[:space:]]*ignore|#[[:space:]]*noqa|pylint:[[:space:]]*disable|//[[:space:]]*nolint|@SuppressWarnings|#!?\[allow\(|@phpstan-ignore|@psalm-suppress|rubocop:disable|NOSONAR|(istanbul|c8|v8) ignore|pragma: no cover|#[[:space:]]*nosec|swiftlint:disable|stylelint-disable"
content_grep "$SUPPRESS_RE" |
  print_hits "NEW SUPPRESSIONS" "Each one switches a check off. Keep only if narrowly scoped and explained; mention it in the report."

# 7. Weakened checks: flags and config values that make a check pass by not checking.
WEAKEN_ANY_RE="continue-on-error:[[:space:]]*true|allow_failure:[[:space:]]*true|--passWithNoTests|--pass-with-no-tests|--no-verify|--exit-zero|--no-fail-on-empty"
WEAKEN_CFG_RE="\"(strict[A-Za-z]*|noImplicit[A-Za-z]*|noUnused[A-Za-z]*|noFallthroughCasesInSwitch|alwaysStrict)\"[[:space:]]*:[[:space:]]*false|\"skipLibCheck\"[[:space:]]*:[[:space:]]*true|fail[_-]under|coverageThreshold|minimum_coverage|ignore_errors[[:space:]]*=[[:space:]]*[Tt]rue|[:=][[:space:]]*[\"']?(off|warn)[\"']?[[:space:]]*[,;]?[[:space:]]*$|\|\|[[:space:]]*(true|:|exit 0)([[:space:]]|;|\"|$)|(^|[[:space:]])set \+e"
{
  content_grep "$WEAKEN_ANY_RE"
  content_grep_in "$CHECK_CFG_RE" "$WEAKEN_CFG_RE"
} | sort -t "$TAB" -k1,1 -k2,2n -u |
  print_hits "WEAKENED-CHECK PATTERNS" "A check made non-blocking, a rule turned off or to warn, strictness relaxed, or a threshold changed. Confirm it is intended, not a way to get green; say so in the report."

# 8. New TODO-style markers.
content_grep "${NB}(TODO|FIXME|XXX|HACK)([^A-Za-z0-9_]|$)" |
  print_hits "NEW TODO / FIXME" "Unfinished work you introduced. Finish it, ticket it, or list it under follow-ups."

# 9. Possible commented-out code (heuristic).
{
  start_grep_in '\.(js|jsx|ts|tsx|mjs|cjs|java|kt|kts|go|rs|c|h|cc|cpp|hpp|cs|swift|scala|dart|php|groovy)' \
    "[[:space:]]*//.*[;{}][[:space:]]*$"
  start_grep_in '\.(py|rb|sh|bash|zsh|ex|exs|r|R|pl)' \
    "[[:space:]]*#[[:space:]]*(import [A-Za-z_]|from [A-Za-z_.]+ import |def [A-Za-z_]+\(|class [A-Za-z_]+[(:]|print\(|[A-Za-z_][A-Za-z0-9_.]*\([^)]*\)[[:space:]]*$|[A-Za-z_][A-Za-z0-9_.]*[[:space:]]*=[[:space:]]*[A-Za-z_][A-Za-z0-9_.]*\()"
} | sort -t "$TAB" -k1,1 -k2,2n -u |
  print_hits "POSSIBLE COMMENTED-OUT CODE (heuristic)" "Delete dead code; version control keeps the history."

# 10. Files: suspicious names, large files.
{
  $GIT diff --name-only --diff-filter=AMR "$BASE" -- 2>/dev/null
  cat "$UNTRACKED"
} | sort -u >"$WORK/files.txt"
$GIT diff --name-only --diff-filter=D "$BASE" -- 2>/dev/null | sort -u >"$WORK/deleted.txt"

: >"$WORK/files_hits.tsv"
while IFS= read -r f; do
  [ -z "$f" ] && continue
  reason=""
  case "$f" in
    *.DS_Store|*Thumbs.db|*desktop.ini) reason="OS metadata file" ;;
    *.swp|*.swo|*~|*.orig|*.rej|*.bak|*.tmp) reason="editor/merge/backup artifact" ;;
    *.log) reason="log file" ;;
    *.pyc|*__pycache__/*|*.class|*.o|*.obj) reason="compiled artifact" ;;
    node_modules/*|*/node_modules/*|.venv/*|venv/*|vendor/bundle/*) reason="dependency directory" ;;
    dist/*|build/*|target/*|out/*|coverage/*|.next/*|*/dist/*|*/build/*|*/target/*|*/coverage/*) reason="build or coverage output (confirm it is meant to be committed)" ;;
    *.env.example|*.env.sample|*.env.template|*.env.dist) reason="" ;;
    .env|*/.env|.env.*|*/.env.*) reason="environment file (may contain secrets)" ;;
    *.pem|*.key|*.p12|*.pfx|*.jks|*.keystore|*id_rsa*|*id_ed25519*|*.kdbx) reason="key or certificate material" ;;
    *.sqlite|*.sqlite3|*.db|*.dump) reason="database file or dump" ;;
  esac
  if [ -z "$reason" ] && [ -f "$f" ]; then
    size=$(wc -c <"$f" | tr -d ' ')
    [ "$size" -gt "$LARGE_FILE_BYTES" ] && reason="large file ($size bytes)"
  fi
  [ -n "$reason" ] && printf '%s\t-\t%s\n' "$f" "$reason" >>"$WORK/files_hits.tsv"
done <"$WORK/files.txt"
print_hits "SUSPICIOUS FILES" "Probably should not be committed. Remove, or add to .gitignore." rule <"$WORK/files_hits.tsv"

# 11. Check configuration touched (lint, types, tests, coverage, hooks, CI).
{
  grep -E -- "($CHECK_CFG_RE)\$" "$WORK/files.txt" | awk -v OFS="$TAB" '{ print $0, "-", "changed: read every edit" }'
  grep -E -- "($CHECK_CFG_RE)\$" "$WORK/deleted.txt" | awk -v OFS="$TAB" '{ print $0, "-", "DELETED" }'
} | print_hits "CHECK CONFIGURATION CHANGED" "Fine when intended. Disabling a rule, adding an ignore or exclude path, lowering a threshold, relaxing strictness, or making a CI step non-blocking all weaken a check: undo it or justify it in the report." rule

# 12. Tests removed: deleted test files, and test files that lost assertions.
{
  grep -E -- "$TEST_PATH_RE" "$WORK/deleted.txt" | awk -v OFS="$TAB" '{ print $0, "-", "test file deleted" }'
  $GIT diff -U0 --no-color --no-ext-diff --src-prefix=a/ --dst-prefix=b/ "$BASE" -- 2>/dev/null |
    awk -v OFS="$TAB" -v T="$TEST_PATH_RE" -v A="$ASSERT_RE" '
      /^diff --git / { hdr = 1; next }
      /^@@ / { hdr = 0; next }
      hdr && /^--- / { next }
      hdr && /^\+\+\+ / {
        n = substr($0, 5); sub(/\t$/, "", n); sub(/^b\//, "", n)
        gone = (n == "/dev/null")   # deleted files are reported by name above
        p = gone ? "" : n
        if (p != "" && !(p in seen)) { seen[p] = 1; order[++k] = p }
        next
      }
      /^-/ { if (p != "" && p ~ T && substr($0, 2) ~ A) del[p]++; next }
      /^\+/ { if (p != "" && p ~ T && substr($0, 2) ~ A) add[p]++; next }
      END {
        for (i = 1; i <= k; i++) {
          p = order[i]
          if (del[p] + 0 > add[p] + 0)
            print p, "-", sprintf("%d test/assertion lines removed, %d added", del[p], add[p] + 0)
        }
      }'
} | sort -u | print_hits "TESTS REMOVED OR REDUCED" "Deleting or loosening tests makes a suite pass by checking less. Confirm each removal is intended (feature removed, test moved) and say so in the report." rule

# 13. Dependency manifests and lockfiles.
{ $GIT diff --name-only "$BASE" -- 2>/dev/null; cat "$UNTRACKED"; } | sort -u | while IFS= read -r f; do
  case "$f" in
    *package-lock.json|*npm-shrinkwrap.json|*yarn.lock|*pnpm-lock.yaml|*bun.lock|*bun.lockb|*poetry.lock|*uv.lock|*Pipfile.lock|*pdm.lock|*Cargo.lock|*go.sum|*go.mod|*Gemfile.lock|*composer.lock|*mix.lock|*Package.resolved|*pubspec.lock|*packages.lock.json|*gradle.lockfile)
      printf '%s\t-\tdependency manifest or lockfile changed\n' "$f" ;;
  esac
done | print_hits "DEPENDENCY CHANGES" "Confirm each was intended (you added/upgraded a dependency) and not incidental churn from a different tool version." rule

# 14. git's own whitespace / conflict check on tracked changes.
CHECK_OUT=$($GIT diff --check "$BASE" -- 2>/dev/null)
if [ -n "$CHECK_OUT" ]; then
  : >"$FLAG_FILE"
  n=$(printf '%s\n' "$CHECK_OUT" | grep -c '^[^+]' || true)
  printf '\n## git diff --check (%s)\n%s\n' "$n" "Whitespace errors or conflict markers in tracked changes."
  printf '%s\n' "$CHECK_OUT" | grep -v '^+' | head -n "$MAX_PER_SECTION" | sed 's/^/  /'
fi

echo
if [ ! -e "$FLAG_FILE" ]; then
  echo "Nothing flagged. This is a pattern scan, not proof: still read the diff yourself."
  exit 0
fi
echo "Review every item above. Patterns are heuristics: decide each one, do not bulk-dismiss."
exit 1
