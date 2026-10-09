#!/usr/bin/env bash
# wt-create.sh - create a git worktree with the safety checks done up front.
#
# Usage:
#   wt-create.sh [options] <path> <branch> [<base>]
#   wt-create.sh [options] --detach <path> <commit-ish>
#
#   <path>    Where the worktree goes. Absolute, or relative to the current dir.
#   <branch>  Branch to check out. Reused if it exists locally, tracked if it
#             exists only on the remote, otherwise created from <base>. A tag,
#             remote-tracking ref, or commit ID is refused here (use --detach,
#             or pass a new branch name with that ref as <base>).
#   <base>    Start point for a NEW branch. Default: the remote's default branch
#             (e.g. origin/main), falling back to the current HEAD.
#
# Options:
#   --remote NAME  Remote to fetch from / look up branches on (default: origin,
#                  or the only remote if there is exactly one).
#   --no-fetch     Do not fetch before creating (offline, or you just fetched).
#   --exclude      If <path> lands inside an existing working tree and is not
#                  ignored there, add the top-level directory to .git/info/exclude
#                  (local-only, never committed) instead of refusing.
#   --detach       Check out <commit-ish> with a detached HEAD (review, bisect,
#                  building an old release). No branch is created. FETCH_HEAD is
#                  resolved BEFORE any fetch and the automatic fetch is skipped,
#                  because a fetch would overwrite it.
#   -n, --dry-run  Print the git commands that would run; change nothing.
#   --selftest     Run the built-in checks against throwaway repositories in a
#                  new temporary directory (removed afterwards); exit 0 when
#                  they all pass. Never touches the current repository.
#   -h, --help     Show this help.
#
# Example, someone's pull request (GitHub ref; GitLab: merge-requests/<n>/head):
#   git fetch origin pull/123/head && wt-create.sh --no-fetch --detach ../pr-123 FETCH_HEAD
#
# Hooks: `git worktree add` runs the shared post-checkout hook. If that hook
# fails (often because the tools it calls are not installed in the new tree
# yet), git exits non-zero AFTER creating the worktree. This script detects
# that, warns, and continues instead of reporting a failure for a tree that
# exists.
#
# What it does NOT do: install dependencies or copy env files. Those are project
# decisions; the script prints what it found so you can do them deliberately.
#
# Exit codes: 0 created (or dry run, or --selftest passed; also when only a
# hook or submodule init failed after creation, with a warning), 1 refused,
# failed, or a self-test failed, 64 usage error.
# Portable to bash 3.2 (macOS default) and GNU/Linux.

set -u

die()  { printf 'wt-create: %s\n' "$*" >&2; exit 1; }
usage(){ awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"; exit "${1:-0}"; }
run()  {
  printf '+ %s\n' "$*"
  if [ "$DRY_RUN" -eq 0 ]; then "$@" || die "command failed: $*"; fi
}
# Like run(), for `git worktree add`: a non-zero exit with the worktree already
# registered and checked out means a post-checkout hook failed, not the add.
HOOK_FAILED=0
add_worktree() {
  printf '+ %s\n' "$*"
  [ "$DRY_RUN" -eq 1 ] && return 0
  "$@" && return 0
  if git worktree list --porcelain | grep -qxF "worktree $TARGET" &&
     git -C "$TARGET" rev-parse --verify --quiet HEAD >/dev/null 2>&1; then
    HOOK_FAILED=1
    printf '%s\n' "wt-create: warning: 'git worktree add' exited non-zero, but $TARGET was created and checked out." \
      "  Most likely a post-checkout hook failed; hooks are shared, and the tools they call" \
      "  may not be installed in this tree yet. Continuing. After setup, re-run whatever the" \
      "  hook does if it matters. Do NOT retry the add: the path and branch now exist." >&2
    return 0
  fi
  die "command failed: $*"
}

# Resolve a path that may not exist yet: resolve the deepest existing ancestor
# physically (symlinks, /tmp -> /private/tmp) and re-append the rest, so it can
# be compared with the physical paths git prints in `worktree list`.
abspath() {
  p=$1; rest=""
  case $p in /*) ;; *) p="$PWD/$p" ;; esac
  while [ ! -d "$p" ]; do
    rest="/$(basename "$p")$rest"
    p=$(dirname "$p")
  done
  printf '%s%s\n' "$(cd "$p" && pwd -P)" "$rest"
}

# ---- Self-test: run this script against throwaway repositories ---------------
selftest() {
  SELF="$(cd "$(dirname "$0")" && pwd -P)/$(basename "$0")"
  ST=$(mktemp -d "${TMPDIR:-/tmp}/wt-create-selftest.XXXXXX") || { echo "selftest: mktemp failed" >&2; return 1; }
  ST=$(cd "$ST" && pwd -P)
  trap 'rm -rf "$ST"' EXIT
  # Isolate from the user's config, hooks, and any repository in the environment.
  export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0
  export GIT_AUTHOR_NAME=selftest GIT_AUTHOR_EMAIL=selftest@example.com
  export GIT_COMMITTER_NAME=selftest GIT_COMMITTER_EMAIL=selftest@example.com
  unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY
  PASSED=0; FAILED=0
  check() {  # $1 = description; $2 = 0 if the expectation held
    if [ "$2" -eq 0 ]; then PASSED=$((PASSED + 1)); echo "ok   $1"
    else FAILED=$((FAILED + 1)); echo "FAIL $1"; sed 's/^/     | /' "$ST/out"; fi
  }
  st_run() { ( cd "$R" && bash "$SELF" "$@" ) >"$ST/out" 2>&1; RC=$?; }
  has() { grep -qF -- "$1" "$ST/out"; }

  R="$ST/repo"
  git init -q -b main "$R" && printf 'one\n' >"$R/a.txt" && git -C "$R" add a.txt &&
    git -C "$R" commit -qm init && git init -q --bare -b main "$ST/origin.git" &&
    git -C "$R" remote add origin "$ST/origin.git" && git -C "$R" push -q origin main &&
    git -C "$R" remote set-head origin main && git -C "$R" tag v1 &&
    git -C "$R" push -q origin main:refs/heads/remote-only && git -C "$R" fetch -q origin ||
    { echo "selftest: could not build the fixture repository" >&2; return 1; }
  BASE_SHA=$(git -C "$R" rev-parse origin/main)

  st_run "$ST/wt-new" feat/new
  ok=1
  [ "$RC" -eq 0 ] && [ "$(git -C "$ST/wt-new" branch --show-current 2>/dev/null)" = feat/new ] &&
    [ "$(git -C "$R" rev-parse feat/new)" = "$BASE_SHA" ] &&
    [ -z "$(git -C "$R" for-each-ref --format='%(upstream)' refs/heads/feat/new)" ] && ok=0
  check "new branch is created from origin/main with no upstream (--no-track)" "$ok"

  st_run "$ST/wt-dup" feat/new
  ok=1; [ "$RC" -eq 1 ] && has "already checked out" && [ ! -e "$ST/wt-dup" ] && ok=0
  check "a branch already checked out in another worktree is refused" "$ok"

  mkdir "$ST/occupied" && : >"$ST/occupied/keep.txt"
  st_run "$ST/occupied" feat/occupied
  ok=1; [ "$RC" -eq 1 ] && ! git -C "$R" show-ref --verify --quiet refs/heads/feat/occupied && ok=0
  check "an occupied path is refused before any branch is created" "$ok"

  st_run "$R/.worktrees/in" feat/in
  ok=1; [ "$RC" -eq 1 ] && has "is not ignored" && ok=0
  check "an in-repository path that is not ignored is refused" "$ok"
  st_run --exclude "$R/.worktrees/in" feat/in
  ok=1; [ "$RC" -eq 0 ] && git -C "$R" check-ignore -q .worktrees/in && [ -z "$(git -C "$R" status --porcelain)" ] && ok=0
  check "--exclude ignores the folder locally and the outer checkout stays clean" "$ok"

  st_run "$ST/wt-tag" v1
  ok=1; [ "$RC" -eq 1 ] && has "is a tag" && ok=0
  check "a tag given as <branch> is refused" "$ok"

  st_run "$ST/wt-remote" remote-only
  ok=1
  [ "$RC" -eq 0 ] && [ "$(git -C "$R" for-each-ref --format='%(upstream:short)' refs/heads/remote-only)" = origin/remote-only ] && ok=0
  check "a branch that exists only on the remote is created tracking it" "$ok"

  st_run --dry-run "$ST/wt-dry" feat/dry
  ok=1; [ "$RC" -eq 0 ] && [ ! -e "$ST/wt-dry" ] && ! git -C "$R" show-ref --verify --quiet refs/heads/feat/dry && ok=0
  check "--dry-run creates neither the folder nor the branch" "$ok"

  git -C "$R" switch -q -c pr-src && git -C "$R" commit -q --allow-empty -m "pr commit" &&
    git -C "$R" push -q origin pr-src:refs/pull/7/head && PR_SHA=$(git -C "$R" rev-parse HEAD) &&
    git -C "$R" switch -q main && git -C "$R" branch -q -D pr-src &&
    git -C "$R" fetch -q origin refs/pull/7/head
  st_run --detach "$ST/wt-pr" FETCH_HEAD
  ok=1; [ "$RC" -eq 0 ] && has "not fetching" && [ "$(git -C "$ST/wt-pr" rev-parse HEAD 2>/dev/null)" = "$PR_SHA" ] && ok=0
  check "--detach FETCH_HEAD pins the fetched commit and skips the automatic fetch" "$ok"

  HOOKS=$(git -C "$R" rev-parse --path-format=absolute --git-path hooks)
  mkdir -p "$HOOKS" && printf '#!/bin/sh\necho "selftest hook failing" >&2\nexit 1\n' >"$HOOKS/post-checkout" &&
    chmod +x "$HOOKS/post-checkout"
  st_run "$ST/wt-hook" feat/hook
  ok=1; [ "$RC" -eq 0 ] && has "post-checkout hook failed" && [ "$(git -C "$ST/wt-hook" branch --show-current 2>/dev/null)" = feat/hook ] && ok=0
  check "a failing post-checkout hook is reported as a warning, not a failed create" "$ok"
  rm -f "$HOOKS/post-checkout"

  st_run --help
  ok=1; [ "$RC" -eq 0 ] && has "Usage:" && ok=0
  check "--help prints usage and exits 0" "$ok"
  st_run --no-such-option
  ok=1; [ "$RC" -eq 64 ] && ok=0
  check "an unknown option is a usage error (exit 64)" "$ok"

  echo "$PASSED/$((PASSED + FAILED)) self-tests passed"
  [ "$FAILED" -eq 0 ]
}

REMOTE=""; FETCH=1; EXCLUDE=0; DETACH=0; DRY_RUN=0
POS=()
while [ $# -gt 0 ]; do
  case $1 in
    --remote)   [ $# -ge 2 ] || usage 64; REMOTE=$2; shift 2 ;;
    --remote=*) REMOTE=${1#--remote=}; shift ;;
    --no-fetch) FETCH=0; shift ;;
    --exclude)  EXCLUDE=1; shift ;;
    --detach)   DETACH=1; shift ;;
    -n|--dry-run) DRY_RUN=1; shift ;;
    --selftest) selftest; exit $? ;;
    -h|--help)  usage 0 ;;
    --) shift; while [ $# -gt 0 ]; do POS+=("$1"); shift; done ;;
    -*) printf 'wt-create: unknown option %s\n' "$1" >&2; usage 64 ;;
    *)  POS+=("$1"); shift ;;
  esac
done
[ ${#POS[@]} -ge 2 ] && [ ${#POS[@]} -le 3 ] || usage 64

git rev-parse --git-dir >/dev/null 2>&1 || die "not inside a git repository"

# Needs git >= 2.31 (rev-parse --path-format); older git echoes the flag back silently.
read -r GIT_MAJ GIT_MIN <<GITVER
$(git --version | sed -n 's/^git version \([0-9]*\)\.\([0-9]*\).*/\1 \2/p')
GITVER
if [ "${GIT_MAJ:-0}" -lt 2 ] || { [ "${GIT_MAJ:-0}" -eq 2 ] && [ "${GIT_MIN:-0}" -lt 31 ]; }; then
  echo "wt-create: needs git >= 2.31 (found: $(git --version))" >&2; exit 1
fi

TARGET=$(abspath "${POS[0]}")
REF=${POS[1]}
BASE=${POS[2]:-}

# ---- 1. Target path must be free -------------------------------------------
# Checked BEFORE `git worktree add -b`, because when add fails on an occupied
# path git may already have created the branch, which then breaks a retry.
if [ -e "$TARGET" ]; then
  if [ -d "$TARGET" ] && [ -z "$(ls -A "$TARGET" 2>/dev/null)" ]; then
    : # empty directory is accepted by git
  else
    die "$TARGET already exists and is not an empty directory"
  fi
fi

# A path still registered as a worktree (folder deleted or moved by hand) makes
# `add` fail, possibly after creating the -b branch. Stop with the real cause.
if git worktree list --porcelain | grep -qxF "worktree $TARGET"; then
  die "$TARGET is already registered as a worktree whose folder is missing (deleted or moved by hand).
  Check it first with wt-preflight.sh $TARGET, then 'git worktree prune -v' if it was deleted,
  or 'git worktree repair <new-path>' if it was moved. Or choose another path."
fi

# ---- 2. If the target is inside an existing working tree, it must be ignored -
# Otherwise the outer checkout sees it as untracked and `git add -A` stages it
# as an embedded repository.
WT_ROOTS=$(git worktree list --porcelain | sed -n 's/^worktree //p')
OLDIFS=$IFS; IFS='
'
for root in $WT_ROOTS; do
  [ "$root" = "$TARGET" ] && continue
  case $TARGET/ in
    "$root"/*)
      rel=${TARGET#"$root"/}
      top=${rel%%/*}
      if git -C "$root" check-ignore -q -- "$rel/probe" 2>/dev/null; then
        echo "ok: $rel is ignored inside $root"
      elif [ "$EXCLUDE" -eq 1 ]; then
        excl="$(git -C "$root" rev-parse --path-format=absolute --git-common-dir)/info/exclude"
        echo "adding /$top/ to $excl (local-only ignore)"
        if [ "$DRY_RUN" -eq 0 ]; then
          mkdir -p "$(dirname "$excl")" && printf '/%s/\n' "$top" >> "$excl" || die "could not write $excl"
          git -C "$root" check-ignore -q -- "$rel/probe" || die "still not ignored after editing $excl"
        fi
      else
        die "$TARGET is inside the working tree $root but '$top/' is not ignored there.
  Fix: add '/$top/' to .gitignore (shared) or .git/info/exclude (local), or rerun with --exclude,
  or put the worktree outside the repository."
      fi
      ;;
  esac
done
IFS=$OLDIFS

# ---- 3. One branch, one worktree: fail before doing anything else ------------
if [ "$DETACH" -eq 0 ] && git show-ref --verify --quiet "refs/heads/$REF"; then
  holder=$(git worktree list --porcelain | awk -v b="branch refs/heads/$REF" '
    /^worktree /{wt=substr($0,10)} $0==b {print wt}')
  [ -z "$holder" ] || die "branch '$REF' is already checked out in $holder.
  A branch can be checked out in only one worktree. Work there, branch off it
  (git worktree add -b <new> <path> $REF), or use --detach for a read-only look."
fi

# ---- 4. Pick the remote and the default base ---------------------------------
# A fetch rewrites FETCH_HEAD, so pin it to a commit first and skip the fetch.
REF_SHA=""
if [ "$DETACH" -eq 1 ] && [ "$REF" = FETCH_HEAD ]; then
  REF_SHA=$(git rev-parse --verify --quiet 'FETCH_HEAD^{commit}') ||
    die "FETCH_HEAD does not name a commit; fetch the ref you want first (e.g. git fetch origin pull/123/head)"
  if [ "$FETCH" -eq 1 ]; then
    echo "not fetching: a fetch would overwrite FETCH_HEAD (pinned to $(git rev-parse --short "$REF_SHA"))"
    FETCH=0
  fi
fi
if [ -z "$REMOTE" ]; then
  if git remote | grep -qx origin; then REMOTE=origin
  elif [ "$(git remote | wc -l | tr -d ' ')" = 1 ]; then REMOTE=$(git remote)
  fi
fi
if [ -n "$REMOTE" ] && [ "$FETCH" -eq 1 ]; then
  run git fetch --quiet "$REMOTE"
fi
if [ -z "$BASE" ] && [ "$DETACH" -eq 0 ]; then
  if [ -n "$REMOTE" ]; then
    BASE=$(git symbolic-ref --quiet --short "refs/remotes/$REMOTE/HEAD" 2>/dev/null || true)
    if [ -z "$BASE" ]; then
      for b in main master trunk develop; do
        if git show-ref --verify --quiet "refs/remotes/$REMOTE/$b"; then BASE="$REMOTE/$b"; break; fi
      done
    fi
  fi
  [ -n "$BASE" ] || BASE=HEAD
fi

# ---- 5. Decide how to create it ----------------------------------------------
if [ "$DETACH" -eq 1 ]; then
  # Pass a SHA, not the name, so what is checked out is what was resolved here.
  [ -n "$REF_SHA" ] || REF_SHA=$(git rev-parse --verify --quiet "$REF^{commit}") || die "'$REF' is not a commit"
  echo "detached at $REF ($(git rev-parse --short "$REF_SHA"))"
  add_worktree git worktree add --detach "$TARGET" "$REF_SHA"
elif git show-ref --verify --quiet "refs/heads/$REF"; then
  echo "reusing existing local branch '$REF'"
  add_worktree git worktree add "$TARGET" "$REF"
elif [ -n "$REMOTE" ] && git show-ref --verify --quiet "refs/remotes/$REMOTE/$REF"; then
  echo "branch '$REF' exists only on $REMOTE; creating a local branch that tracks it"
  add_worktree git worktree add --track -b "$REF" "$TARGET" "$REMOTE/$REF"
elif git show-ref --verify --quiet "refs/tags/$REF"; then
  die "'$REF' is a tag, not a branch. Use --detach to look at it, or pass a new branch name and '$REF' as <base>."
elif git show-ref --verify --quiet "refs/remotes/$REF"; then
  die "'$REF' is a remote-tracking branch, not a local branch name. Pass '${REF#*/}' to track it, or a new branch name with '$REF' as <base>."
elif printf '%s\n' "$REF" | grep -Eq '^[0-9a-fA-F]{7,40}$' && git rev-parse --verify --quiet "$REF^{commit}" >/dev/null; then
  die "'$REF' is a commit ID, not a branch. Use --detach to look at it, or pass a new branch name and '$REF' as <base>."
else
  git rev-parse --verify --quiet "$BASE^{commit}" >/dev/null || die "base '$BASE' is not a commit"
  # --no-track: a new topic branch should not have the base as its upstream,
  # or `git push` refuses (name mismatch) and `git pull` merges the base.
  echo "creating new branch '$REF' from $BASE ($(git rev-parse --short "$BASE"))"
  add_worktree git worktree add --no-track -b "$REF" "$TARGET" "$BASE"
fi

[ "$DRY_RUN" -eq 1 ] && { echo "dry run: nothing changed"; exit 0; }

# ---- 6. Submodules are not populated by `worktree add` -----------------------
# The worktree exists at this point, so a failure here is reported, not fatal.
SUB_FAILED=0
if [ -f "$TARGET/.gitmodules" ]; then
  printf '+ %s\n' "git -C $TARGET submodule update --init --recursive"
  if ! git -C "$TARGET" submodule update --init --recursive; then
    SUB_FAILED=1
    echo "wt-create: warning: the worktree was created, but submodule init failed (see above)." >&2
    echo "  Fix the cause (access, network, URL), then: git -C \"$TARGET\" submodule update --init --recursive" >&2
  fi
fi

# ---- 7. Report ---------------------------------------------------------------
SRC_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
echo
echo "Worktree : $TARGET"
echo "HEAD     : $(git -C "$TARGET" rev-parse --short HEAD) $(git -C "$TARGET" log -1 --format=%s)"
CUR=$(git -C "$TARGET" branch --show-current 2>/dev/null)
echo "Branch   : ${CUR:-(detached)}"
# for-each-ref, not rev-parse '@{u}', which prints a literal '@{u}' for a deleted upstream.
UPS=""; UPT=""
if [ -n "$CUR" ]; then
  UPS=$(git -C "$TARGET" for-each-ref --format='%(upstream:short)' "refs/heads/$CUR")
  UPT=$(git -C "$TARGET" for-each-ref --format='%(upstream:track)' "refs/heads/$CUR")
fi
if [ -z "$CUR" ]; then
  echo "Upstream : n/a (detached HEAD; commits made here belong to no branch until you create one)"
elif [ -z "$UPS" ]; then
  echo "Upstream : (none - set on first push with: git push -u <remote> <branch>)"
elif [ "$UPT" = "[gone]" ]; then
  echo "Upstream : $UPS is configured but gone on the remote (deleted, often after a merge); check before building on this branch"
else
  echo "Upstream : $UPS"
fi

echo
echo "Dependency manifests at the worktree root (install before running anything):"
found=0
for f in package-lock.json pnpm-lock.yaml yarn.lock bun.lock bun.lockb uv.lock poetry.lock \
         Pipfile.lock requirements.txt pyproject.toml Gemfile.lock Cargo.lock go.sum composer.lock \
         pom.xml build.gradle build.gradle.kts mix.lock pubspec.lock global.json; do
  if [ -e "$TARGET/$f" ]; then echo "  - $f"; found=1; fi
done
ls "$TARGET"/*.sln >/dev/null 2>&1 && { echo "  - *.sln"; found=1; }
[ "$found" -eq 1 ] || echo "  (none found at the root; check subprojects)"

if [ -n "$SRC_ROOT" ] && [ "$SRC_ROOT" != "$TARGET" ]; then
  echo
  echo "Local-only files in $SRC_ROOT that the new worktree does NOT have"
  echo "(copy only what this task needs; dependency and build dirs omitted):"
  git -C "$SRC_ROOT" ls-files --others --ignored --exclude-standard --directory 2>/dev/null \
    | grep -Ev '(^|/)(node_modules|\.venv|venv|env|target|dist|build|out|vendor|coverage|__pycache__|\.next|\.nuxt|\.turbo|\.gradle|\.pytest_cache|\.mypy_cache|\.ruff_cache|\.cache|\.idea|\.vscode|\.worktrees|\.DS_Store)(/|$)' \
    | grep -Ev '\.(pyc|log|tmp)$' \
    | head -n 25 | sed 's/^/  - /'
fi
echo
if [ "$SUB_FAILED" -eq 1 ]; then
  echo "Warning: submodules are NOT initialized; builds and tests will fail until they are."
fi
if [ "$HOOK_FAILED" -eq 1 ]; then
  echo "Warning: a post-checkout hook failed during creation (see above). The worktree is usable;"
  echo "re-run the hook's job after installing dependencies if the project relies on it."
fi
echo "Next: install dependencies, copy any needed env files, then run the baseline checks."
