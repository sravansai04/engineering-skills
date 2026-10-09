#!/usr/bin/env bash
# wt-preflight.sh - decide whether a linked worktree can be removed without
# losing anything, and whether its branch can be deleted afterwards.
#
# Usage:
#   wt-preflight.sh [--base <ref>] [--fetch] <worktree-path>
#   wt-preflight.sh --selftest
#
#   <worktree-path>  Path of the linked worktree to inspect.
#   --base <ref>     Branch the work was meant to land in (default: the remote's
#                    default branch, e.g. origin/main). Used for the
#                    "is this branch integrated?" check.
#   --fetch          Fetch the branch's remote (or the base's) BEFORE the upstream
#                    and integration checks, so both use current remote refs.
#   --selftest       Run the built-in checks against throwaway repositories in a
#                    new temporary directory (removed afterwards); exit 0 when
#                    they all pass. Never touches the current repository.
#   -h, --help       Show this help.
#
# `git worktree remove` refuses modified/untracked files, locked worktrees, and
# worktrees with populated submodules - but it silently DELETES ignored files (.env,
# local databases, notes) and does not look at in-progress rebases/merges,
# commits reachable only from a detached HEAD, or local-only submodule commits.
# This script checks all of those.
#
# Exit codes / verdicts:
#   0  SAFE     nothing would be lost; the remove command is printed
#   2  REVIEW   a human must look first: ignored files that may be hand-made, or
#               the folder is missing (deleted and moved look the same from here)
#   1  BLOCKED  removing now would lose work, or the worktree is locked/main
#   64 usage error
#   (--selftest: 0 when every self-test passed, 1 otherwise)
#
# Branch deletion: `git branch -d` compares the branch with its UPSTREAM when it
# has one (after `push -u`, that is just its own pushed copy), otherwise with the
# HEAD of the checkout you run it in. So -d succeeding means "pushed", not
# "landed". The integration check below compares with the base instead.
#
# Changes no files, refs, or worktrees (except --fetch, which updates remote-tracking
# refs). The squash-merge content check needs git >= 2.38 and may leave unreferenced
# objects that gc cleans up. Portable to bash 3.2 (macOS default) and GNU/Linux.

set -u

usage(){ awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"; exit "${1:-0}"; }

# ---- Self-test: run this script against throwaway repositories ---------------
selftest() {
  SELF="$(cd "$(dirname "$0")" && pwd -P)/$(basename "$0")"
  ST=$(mktemp -d "${TMPDIR:-/tmp}/wt-preflight-selftest.XXXXXX") || { echo "selftest: mktemp failed" >&2; return 1; }
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
  g() { git -C "$R" "$@"; }

  R="$ST/repo"
  git init -q -b main "$R" && printf 'one\n' >"$R/a.txt" && printf '.env\nnode_modules/\n' >"$R/.gitignore" &&
    g add a.txt .gitignore && g commit -qm init && git init -q --bare -b main "$ST/origin.git" &&
    g remote add origin "$ST/origin.git" && g push -q origin main && g remote set-head origin main ||
    { echo "selftest: could not build the fixture repository" >&2; return 1; }

  g worktree add -q --no-track -b clean "$ST/wt-clean" origin/main
  st_run "$ST/wt-clean"
  ok=1; [ "$RC" -eq 0 ] && has "VERDICT: SAFE" && has "already in origin/main" && ok=0
  check "a clean worktree whose branch is in the base is SAFE" "$ok"

  g worktree lock "$ST/wt-clean"
  st_run "$ST/wt-clean"
  ok=1; [ "$RC" -eq 1 ] && has "locked" && ok=0
  check "a locked worktree is BLOCKED" "$ok"
  g worktree unlock "$ST/wt-clean"

  g worktree add -q --no-track -b dirty "$ST/wt-dirty" origin/main && : >"$ST/wt-dirty/notes.txt"
  st_run "$ST/wt-dirty"
  ok=1; [ "$RC" -eq 1 ] && has "VERDICT: BLOCKED" && has "notes.txt" && ok=0
  check "an untracked file makes the verdict BLOCKED" "$ok"

  g worktree add -q --no-track -b env "$ST/wt-env" origin/main && printf 'TOKEN=example-not-a-real-key-0000\n' >"$ST/wt-env/.env"
  st_run "$ST/wt-env"
  ok=1; [ "$RC" -eq 2 ] && has "VERDICT: REVIEW" && has ".env" && ok=0
  check "a hand-made ignored file (.env) that remove would delete silently is REVIEW" "$ok"

  g worktree add -q --no-track -b deps "$ST/wt-deps" origin/main && mkdir -p "$ST/wt-deps/node_modules/pkg" &&
    : >"$ST/wt-deps/node_modules/pkg/index.js"
  st_run "$ST/wt-deps"
  ok=1; [ "$RC" -eq 0 ] && has "regenerable" && ok=0
  check "ignored dependency folders alone are regenerable and stay SAFE" "$ok"

  g worktree add -q --detach "$ST/wt-detached" origin/main && git -C "$ST/wt-detached" commit -q --allow-empty -m orphan
  st_run "$ST/wt-detached"
  ok=1; [ "$RC" -eq 1 ] && has "rescue/" && ok=0
  check "a commit reachable only from a detached HEAD is BLOCKED with a rescue command" "$ok"

  g worktree add -q --no-track -b pushed "$ST/wt-pushed" origin/main && printf 'two\n' >"$ST/wt-pushed/a.txt" &&
    git -C "$ST/wt-pushed" commit -qam "unmerged change" && git -C "$ST/wt-pushed" push -q -u origin pushed
  st_run "$ST/wt-pushed"
  ok=1; [ "$RC" -eq 0 ] && ! has "Then:         git branch -d" && ok=0
  check "a pushed but unmerged branch is never offered for deletion (pushed is not landed)" "$ok"

  g worktree add -q --no-track -b gone "$ST/wt-gone" origin/main && rm -rf "$ST/wt-gone"
  st_run "$ST/wt-gone"
  ok=1; [ "$RC" -eq 2 ] && has "cannot tell a deleted folder from a moved one" && has "worktree repair" && ok=0
  check "a missing folder is REVIEW (deleted and moved look the same), never SAFE" "$ok"

  g worktree add -q --detach "$ST/wt-gone-detached" origin/main &&
    git -C "$ST/wt-gone-detached" commit -q --allow-empty -m "orphan in a missing folder" && rm -rf "$ST/wt-gone-detached"
  st_run "$ST/wt-gone-detached"
  ok=1; [ "$RC" -eq 1 ] && has "rescue/" && ok=0
  check "a missing folder whose detached HEAD holds unreachable commits is BLOCKED before prune" "$ok"

  g worktree add -q --no-track -b op "$ST/wt-op" origin/main && git -C "$ST/wt-op" merge -q --no-commit --no-ff pushed >/dev/null 2>&1
  st_run "$ST/wt-op"
  ok=1; [ "$RC" -eq 1 ] && has "operation is in progress (MERGE_HEAD)" && ok=0
  check "an in-progress merge is BLOCKED" "$ok"

  st_run "$R"
  ok=1; [ "$RC" -eq 1 ] && has "main worktree" && ok=0
  check "the main worktree is BLOCKED" "$ok"

  # Squash-merge content check: needs git >= 2.38 (merge-tree --write-tree).
  if g merge-tree --write-tree HEAD HEAD >/dev/null 2>&1; then
    g worktree add -q --no-track -b squashed "$ST/wt-squashed" origin/main && printf 'b\n' >"$ST/wt-squashed/b.txt" &&
      git -C "$ST/wt-squashed" add b.txt && git -C "$ST/wt-squashed" commit -qm "add b" &&
      g merge -q --squash squashed >/dev/null && g commit -qm "add b (squashed)" && g push -q origin main
    st_run "$ST/wt-squashed"
    ok=1; [ "$RC" -eq 0 ] && has "squash/rebase merge" && has "Then:         git branch -d squashed" && ok=0
    check "a squash-merged branch is recognised as landed by content" "$ok"
  else
    echo "skip a squash-merged branch is recognised as landed by content (needs git >= 2.38)"
  fi

  st_run --help
  ok=1; [ "$RC" -eq 0 ] && has "Usage:" && ok=0
  check "--help prints usage and exits 0" "$ok"
  st_run
  ok=1; [ "$RC" -eq 64 ] && ok=0
  check "a missing <worktree-path> is a usage error (exit 64)" "$ok"

  echo "$PASSED/$((PASSED + FAILED)) self-tests passed"
  [ "$FAILED" -eq 0 ]
}

BASE=""; FETCH=0; WT_ARG=""
while [ $# -gt 0 ]; do
  case $1 in
    --base)   [ $# -ge 2 ] || usage 64; BASE=$2; shift 2 ;;
    --base=*) BASE=${1#--base=}; shift ;;
    --fetch)  FETCH=1; shift ;;
    --selftest) selftest; exit $? ;;
    -h|--help) usage 0 ;;
    -*) printf 'wt-preflight: unknown option %s\n' "$1" >&2; usage 64 ;;
    *)  [ -z "$WT_ARG" ] || usage 64; WT_ARG=$1; shift ;;
  esac
done
[ -n "$WT_ARG" ] || usage 64

# Needs git >= 2.31 (rev-parse --path-format); older git echoes the flag back silently.
read -r GIT_MAJ GIT_MIN <<GITVER
$(git --version | sed -n 's/^git version \([0-9]*\)\.\([0-9]*\).*/\1 \2/p')
GITVER
if [ "${GIT_MAJ:-0}" -lt 2 ] || { [ "${GIT_MAJ:-0}" -eq 2 ] && [ "${GIT_MIN:-0}" -lt 31 ]; }; then
  echo "wt-preflight: needs git >= 2.31 (found: $(git --version))" >&2; exit 1
fi

BLOCK=0; REVIEW=0
block()  { BLOCK=1;  printf '  [BLOCK]  %s\n' "$*"; }
review() { REVIEW=1; printf '  [REVIEW] %s\n' "$*"; }
ok()     { printf '  [OK]     %s\n' "$*"; }
info()   { printf '  [INFO]   %s\n' "$*"; }
indent() { sed 's/^/             /'; }

# Physical absolute path, so it matches what `git worktree list` prints.
if [ -d "$WT_ARG" ]; then
  WT=$(cd "$WT_ARG" && pwd -P)
  CTX=$WT
else
  case $WT_ARG in /*) WT=$WT_ARG ;; *) WT="$PWD/$WT_ARG" ;; esac
  d=$(dirname "$WT"); [ -d "$d" ] && WT="$(cd "$d" && pwd -P)/$(basename "$WT")"
  CTX=.
fi
git -C "$CTX" rev-parse --git-dir >/dev/null 2>&1 || { echo "wt-preflight: not inside a git repository" >&2; exit 1; }

# ---- Locate the entry in `git worktree list --porcelain` ---------------------
LIST=$(git -C "$CTX" worktree list --porcelain)
MAIN=$(printf '%s\n' "$LIST" | sed -n '1s/^worktree //p')
MAIN_IS_BARE=0
printf '%s\n' "$LIST" | sed -n '2p' | grep -qx bare && MAIN_IS_BARE=1
ENTRY=$(printf '%s\n' "$LIST" | awk -v p="worktree $WT" '$0==p{f=1} f&&/^$/{exit} f{print}')

echo "Preflight: $WT"
if [ -z "$ENTRY" ]; then
  echo "  not a registered worktree of this repository (see: git worktree list)" >&2
  exit 1
fi
if [ "$WT" = "$MAIN" ]; then
  block "this is the main worktree; it cannot be removed (only linked worktrees can)"
  echo "VERDICT: BLOCKED"; exit 1
fi

LOCKED=$(printf '%s\n' "$ENTRY" | sed -n 's/^locked *//p' | head -n 1)
if printf '%s\n' "$ENTRY" | grep -q '^locked'; then
  block "worktree is locked: ${LOCKED:-no reason given}. Someone locked it on purpose; confirm, then 'git worktree unlock' before removing"
fi

if [ ! -d "$WT" ]; then
  # The folder is gone from where git expects it. A DELETED folder and a folder
  # MOVED by hand (or on an unplugged drive) look identical from here, and
  # pruning breaks a moved one. Never answer SAFE for a state we cannot see.
  E_SHA=$(printf '%s\n' "$ENTRY" | sed -n 's/^HEAD //p' | head -n 1)
  E_BRANCH=$(printf '%s\n' "$ENTRY" | sed -n 's|^branch refs/heads/||p' | head -n 1)
  if [ -n "$E_BRANCH" ]; then
    info "entry holds branch $E_BRANCH; the branch and its commits survive a prune"
  elif printf '%s\n' "$ENTRY" | grep -qx detached && [ -n "$E_SHA" ] &&
       git -C "$CTX" rev-parse --verify --quiet "$E_SHA^{commit}" >/dev/null; then
    ORPH=$(git -C "$CTX" log --oneline "$E_SHA" --not --branches --remotes --tags 2>/dev/null)
    if [ -n "$ORPH" ]; then
      block "commits reachable only from this entry's detached HEAD (pruning makes them unreachable) - save first with: git -C \"$MAIN\" branch rescue/$(basename "$WT") $E_SHA"
      printf '%s\n' "$ORPH" | head -n 10 | indent
    else
      ok "detached HEAD $(printf '%.7s' "$E_SHA") is reachable from an existing ref"
    fi
  fi
  if printf '%s\n' "$ENTRY" | grep -q '^locked'; then
    info "directory is missing but the entry is locked (e.g. unmounted drive); prune skips it, so leave it until the drive is back"
  fi
  review "the folder is missing; uncommitted and ignored files, wherever they are now, cannot be inspected from here"
  echo
  if [ "$BLOCK" -eq 1 ]; then
    echo "VERDICT: BLOCKED - resolve the [BLOCK] items above before pruning this entry"
  else
    echo "VERDICT: REVIEW - this script cannot tell a deleted folder from a moved one"
  fi
  echo "If it was DELETED:               git -C \"$MAIN\" worktree prune -v"
  echo "If it was MOVED or is unplugged: do NOT prune. Run: git -C \"$MAIN\" worktree repair <new-path>"
  printf '%s\n' "$ENTRY" | grep -q '^locked' ||
    echo "                                 (or keep it registered while unplugged: git -C \"$MAIN\" worktree lock --reason \"external drive\" \"$WT\")"
  [ "$BLOCK" -eq 1 ] && exit 1
  exit 2
fi

# ---- Branch / HEAD ------------------------------------------------------------
BRANCH=$(git -C "$WT" symbolic-ref --quiet --short HEAD 2>/dev/null || true)
HEAD_SHA=$(git -C "$WT" rev-parse --short HEAD 2>/dev/null || echo "(unborn)")
if [ -n "$BRANCH" ]; then
  info "branch $BRANCH at $HEAD_SHA"
else
  info "detached HEAD at $HEAD_SHA"
fi

# ---- 1. In-progress operations (their state lives in the worktree's private gitdir)
for op in rebase-merge rebase-apply MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD BISECT_LOG; do
  if [ -e "$(git -C "$WT" rev-parse --path-format=absolute --git-path "$op")" ]; then
    block "an operation is in progress ($op); finish or abort it first"
  fi
done

# ---- 2. Modified / untracked (what `remove` itself refuses) -------------------
DIRTY=$(git -C "$WT" status --porcelain=v1 --untracked-files=all 2>/dev/null)
if [ -n "$DIRTY" ]; then
  n=$(printf '%s\n' "$DIRTY" | wc -l | tr -d ' ')
  block "$n modified or untracked path(s) - commit, stash, or move them:"
  printf '%s\n' "$DIRTY" | head -n 15 | indent
  [ "$n" -gt 15 ] && echo "             ... and $((n - 15)) more"
else
  ok "no modified or untracked files"
fi

# ---- 3. Ignored files (what `remove` deletes WITHOUT asking) ------------------
# Clearly regenerable dependency/build/cache output. Editor folders (.idea,
# .vscode) and bin/ or vendor/ are NOT in this list: they often hold hand-made
# run configurations or helper scripts, so they go to REVIEW unless a manifest
# beside them shows they are tool output (vendor/ + composer.json/go.mod/Gemfile,
# bin/ + a .NET project file).
REGEN='(^|/)(node_modules|\.venv|venv|target|dist|build|out|coverage|__pycache__|\.next|\.nuxt|\.svelte-kit|\.angular|\.turbo|\.parcel-cache|\.gradle|\.pytest_cache|\.mypy_cache|\.ruff_cache|\.tox|\.nox|\.cache|obj|[^/]*\.egg-info)/?$|\.(pyc|pyo|class|o|log)$|(^|/)\.DS_Store$'
EDITOR='(^|/)(\.idea|\.vscode|\.fleet|\.zed)/?$'
tool_output_dir() {  # $1 = ignored path; true if it is vendor/ or bin/ next to the manifest that generates it
  d=${1%/}; parent=$(dirname "$d"); base=$(basename "$d")
  case $base in
    vendor) for m in composer.json go.mod Gemfile; do [ -f "$WT/$parent/$m" ] && return 0; done ;;
    bin)    for m in "$WT/$parent"/*.csproj "$WT/$parent"/*.fsproj "$WT/$parent"/*.vbproj; do [ -f "$m" ] && return 0; done ;;
  esac
  return 1
}
IGN=$(git -C "$WT" status --porcelain=v1 --ignored=traditional 2>/dev/null | sed -n 's/^!! //p' | sed 's/^"\(.*\)"$/\1/')
HANDMADE=""; COPIES=""; EDITORS=""; NREGEN=0
if [ -n "$IGN" ]; then
  OLDIFS=$IFS; IFS='
'
  set -f   # ignored names may contain glob characters; do not expand them
  for path in $IGN; do
    if printf '%s\n' "$path" | grep -Eq "$REGEN" || tool_output_dir "$path"; then
      NREGEN=$((NREGEN + 1))
    elif printf '%s\n' "$path" | grep -Eq "$EDITOR"; then
      EDITORS="$EDITORS$path
"
    elif [ "$MAIN_IS_BARE" -eq 0 ] && [ -f "$WT/$path" ] && [ -f "$MAIN/$path" ] && cmp -s "$WT/$path" "$MAIN/$path"; then
      COPIES="$COPIES$path
"
    else
      HANDMADE="$HANDMADE$path
"
    fi
  done
  set +f
  IFS=$OLDIFS
fi
[ "$NREGEN" -gt 0 ] && ok "$NREGEN ignored dependency/build/cache path(s) - regenerable, will be deleted"
[ -n "$COPIES" ] && { ok "ignored files identical to the main worktree's copy (safe to lose):"; printf '%s' "$COPIES" | indent; }
if [ -n "$EDITORS" ]; then
  review "ignored editor folders - usually regenerable, but may hold hand-made run/launch configurations; glance first:"
  printf '%s' "$EDITORS" | indent
fi
if [ -n "$HANDMADE" ]; then
  review "ignored files that 'git worktree remove' would delete silently - check each (secrets, local DBs, notes, edited env, helper scripts):"
  printf '%s' "$HANDMADE" | head -n 20 | indent
  nh=$(printf '%s' "$HANDMADE" | wc -l | tr -d ' ')
  [ "$nh" -gt 20 ] && echo "             ... and $((nh - 20)) more"
fi

# ---- 4. Commits reachable only from a detached HEAD ---------------------------
if [ -z "$BRANCH" ] && git -C "$WT" rev-parse --verify --quiet HEAD >/dev/null; then
  ORPHANS=$(git -C "$WT" log --oneline HEAD --not --branches --remotes --tags 2>/dev/null)
  if [ -n "$ORPHANS" ]; then
    block "commits reachable only from this detached HEAD (lost on removal) - save with: git -C \"$WT\" branch rescue/$(basename "$WT") HEAD"
    printf '%s\n' "$ORPHANS" | head -n 10 | indent
  else
    ok "detached HEAD is reachable from an existing ref"
  fi
fi

# ---- 5. Submodules (their repositories live inside this worktree's private gitdir)
FORCE_NOTE=""
if [ -f "$WT/.gitmodules" ]; then
  # git refuses a plain remove only when submodules are actually populated: the
  # worktree's private gitdir has a modules/ folder, or a submodule is checked
  # out ('git submodule status' prefixes unpopulated ones with '-').
  WT_GITDIR=$(git -C "$WT" rev-parse --path-format=absolute --git-dir)
  SUBPOP=0
  [ -d "$WT_GITDIR/modules" ] && SUBPOP=1
  if [ "$SUBPOP" -eq 0 ] && git -C "$WT" submodule status --recursive 2>/dev/null | grep -q '^[^-]'; then SUBPOP=1; fi
  if [ "$SUBPOP" -eq 1 ]; then
    SUBDIRTY=$(git -C "$WT" submodule foreach --recursive --quiet \
      'git status --porcelain=v1 | sed "s|^|$displaypath: |"' 2>/dev/null)
    # --tags: a commit reachable from a tag (e.g. a pinned release) is not local-only.
    SUBLOCAL=$(git -C "$WT" submodule foreach --recursive --quiet \
      'git log --oneline HEAD --not --remotes --tags 2>/dev/null | sed "s|^|$displaypath: |"' 2>/dev/null)
    [ -n "$SUBDIRTY" ] && { block "uncommitted changes inside submodules:"; printf '%s\n' "$SUBDIRTY" | head -n 10 | indent; }
    [ -n "$SUBLOCAL" ] && { block "submodule commits not on any remote or tag (the submodule repo is deleted with the worktree):"; printf '%s\n' "$SUBLOCAL" | head -n 10 | indent; }
    [ -z "$SUBDIRTY$SUBLOCAL" ] && ok "submodules clean and pushed (removal needs --force because they are populated)"
    info "ignored files inside submodules are not inspected; look in them yourself if they may hold anything hand-made"
    FORCE_NOTE=" --force"
  else
    ok ".gitmodules present but no submodule is populated here; a plain remove works"
  fi
fi

# ---- 6. Upstream, base integration, stashes (branch survives removal) ---------
INTEGRATED=unknown; REMOTE=""
if [ -n "$BRANCH" ]; then
  REMOTE=$(git -C "$WT" config "branch.$BRANCH.remote" 2>/dev/null || true)
  [ "$REMOTE" = "." ] && REMOTE=""   # upstream is a local branch
  if [ -z "$REMOTE" ]; then
    if git -C "$WT" remote | grep -qx origin; then REMOTE=origin; else REMOTE=$(git -C "$WT" remote | head -n 1); fi
  fi
  # Fetch FIRST, so the upstream and integration checks below use current refs.
  if [ "$FETCH" -eq 1 ] && [ -n "$REMOTE" ]; then
    git -C "$WT" fetch --quiet "$REMOTE" || info "fetch from $REMOTE failed; using local refs"
  fi
  if [ -z "$BASE" ] && [ -n "$REMOTE" ]; then
    BASE=$(git -C "$WT" symbolic-ref --quiet --short "refs/remotes/$REMOTE/HEAD" 2>/dev/null || true)
    if [ -z "$BASE" ]; then
      for b in main master trunk develop; do
        git -C "$WT" show-ref --verify --quiet "refs/remotes/$REMOTE/$b" && { BASE="$REMOTE/$b"; break; }
      done
    fi
  fi

  # for-each-ref reports a configured-but-deleted upstream as [gone]; rev-parse
  # '@{u}' would instead print the literal '@{u}' and look like success.
  UP=$(git -C "$WT" for-each-ref --format='%(upstream:short)' "refs/heads/$BRANCH")
  UPTRACK=$(git -C "$WT" for-each-ref --format='%(upstream:track)' "refs/heads/$BRANCH")
  if [ -z "$UP" ]; then
    info "branch has no upstream - its commits exist only locally until pushed"
  elif [ "$UPTRACK" = "[gone]" ]; then
    info "upstream $UP is configured but gone (deleted on the remote, often after a merge); that alone does not prove the work landed - see the integration check"
  else
    read -r BEHIND AHEAD_UP <<EOF
$(git -C "$WT" rev-list --left-right --count "$UP...HEAD" 2>/dev/null || echo "0 0")
EOF
    if [ "${AHEAD_UP:-0}" -gt 0 ]; then
      info "$AHEAD_UP commit(s) not pushed to $UP - they stay on branch $BRANCH after removal; push before deleting the branch"
    else
      ok "branch is pushed to $UP (behind by ${BEHIND:-0}); pushed is not the same as merged"
    fi
  fi

  if [ -n "$BASE" ] && git -C "$WT" rev-parse --verify --quiet "$BASE^{commit}" >/dev/null; then
    AHEAD=$(git -C "$WT" rev-list --count "$BASE..HEAD")
    if [ "$AHEAD" -eq 0 ]; then
      INTEGRATED=yes; ok "every commit on $BRANCH is already in $BASE"
    else
      # Squash and rebase merges rewrite commits, so ancestry says "not merged".
      # Compare content instead: if merging the branch into the base would not
      # change the base's tree, the work is already there. Needs git >= 2.38.
      # Exit status: 0 clean merge, 1 conflicts, anything else = unsupported/error.
      MT_OUT=$(git -C "$WT" merge-tree --write-tree "$BASE" HEAD 2>/dev/null); MT_RC=$?
      MT=$(printf '%s\n' "$MT_OUT" | head -n 1)
      if [ "$MT_RC" -gt 1 ]; then
        info "$AHEAD commit(s) on $BRANCH not in $BASE by ancestry; content check unavailable (needs git >= 2.38) - verify the merge on your code host before deleting the branch"
      elif [ "$MT_RC" -eq 0 ] && [ "$MT" = "$(git -C "$WT" rev-parse "$BASE^{tree}")" ]; then
        INTEGRATED=yes; ok "$AHEAD commit(s) not in $BASE by ancestry, but their changes are already in $BASE's content (squash/rebase merge)"
      else
        INTEGRATED=no; info "$AHEAD commit(s) on $BRANCH whose changes are NOT in $BASE - keep the branch (or push it) unless you mean to discard them"
      fi
    fi
  else
    info "no base ref found to check integration against (pass --base <ref>)"
  fi

  NSTASH=$(git -C "$WT" stash list 2>/dev/null | grep -cF "n $BRANCH:" || true)
  [ "${NSTASH:-0}" -gt 0 ] && info "$NSTASH stash entr(ies) were made on $BRANCH - stashes are shared and survive removal, but are easy to forget (git stash list)"
fi

# ---- 7. Are we standing in it? -----------------------------------------------
case "$(pwd -P)/" in "$WT"/*) info "your shell is inside this worktree - cd to $MAIN (or anywhere else) before removing" ;; esac

# ---- Verdict -----------------------------------------------------------------
echo
if [ "$BLOCK" -eq 1 ]; then
  echo "VERDICT: BLOCKED - removing now would lose work or override a deliberate lock"
  exit 1
fi
if [ "$REVIEW" -eq 1 ]; then
  echo "VERDICT: REVIEW - only the ignored files listed above would be lost; save any you need, then remove"
else
  echo "VERDICT: SAFE"
fi
echo "Remove with:  git worktree remove$FORCE_NOTE \"$WT\"   (run from outside it)"
if [ -n "$BRANCH" ]; then
  case $INTEGRATED in
    yes)
      echo "Then:         git branch -d $BRANCH"
      echo "              -d checks the upstream (or HEAD), not $BASE; if it refuses, -D is justified because the check above found the work in $BASE"
      if [ -n "$REMOTE" ] && { [ -n "$UP" ] || git -C "$WT" show-ref --verify --quiet "refs/remotes/$REMOTE/$BRANCH"; }; then
        echo "Remote copy:  git push $REMOTE --delete $BRANCH   (only if the host has not deleted it already)"
      fi ;;
    no)
      echo "Branch:       keep $BRANCH - it holds work that is not in ${BASE:-the base}."
      echo "              Do not delete it locally or on the remote; a successful 'git branch -d' here would only mean it was pushed." ;;
    *)
      echo "Branch:       confirm $BRANCH landed (merged PR on the host, or rerun with --base <ref>) before deleting it locally or on the remote."
      echo "              A successful 'git branch -d' is not that confirmation: with an upstream set it only proves the branch was pushed." ;;
  esac
fi
[ "$REVIEW" -eq 1 ] && exit 2
exit 0
