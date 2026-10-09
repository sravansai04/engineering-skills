#!/usr/bin/env bash
# wt-overview.sh - one line per worktree of the current repository: branch,
# uncommitted file count, position against upstream, age of the last commit,
# and flags (main, locked, prunable, detached, op = rebase/merge in progress).
#
# Usage:
#   wt-overview.sh            run from any worktree of the repository
#   wt-overview.sh --stale N  also mark worktrees whose last commit is N or
#                             more days old as cleanup candidates (STALE)
#   wt-overview.sh --selftest run the built-in checks against throwaway
#                             repositories in a new temporary directory
#                             (removed afterwards); exit 0 when all pass
#   wt-overview.sh -h|--help  show this help
#
# Read-only. Use it before starting parallel work (what already exists?),
# while coordinating agents (who is dirty or behind?), and before cleanup
# (what is stale?). Feed each cleanup candidate to wt-preflight.sh.
# Exit codes: 0 listed (or self-tests passed), 1 not in a repository, git too
# old, or a self-test failed, 64 usage error.
# Portable to bash 3.2 (macOS default) and GNU/Linux.

set -u

# ---- Self-test: run this script against throwaway repositories ---------------
selftest() {
  SELF="$(cd "$(dirname "$0")" && pwd -P)/$(basename "$0")"
  ST=$(mktemp -d "${TMPDIR:-/tmp}/wt-overview-selftest.XXXXXX") || { echo "selftest: mktemp failed" >&2; return 1; }
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
  row() { grep -F -- "$1 " "$ST/out" | head -n 1; }   # the line for one worktree path
  g() { git -C "$R" "$@"; }

  R="$ST/repo"
  git init -q -b main "$R" && printf 'one\n' >"$R/a.txt" && g add a.txt && g commit -qm init &&
    git init -q --bare -b main "$ST/origin.git" && g remote add origin "$ST/origin.git" &&
    g push -q origin main && g remote set-head origin main ||
    { echo "selftest: could not build the fixture repository" >&2; return 1; }

  g worktree add -q --no-track -b gone-up "$ST/wt-gone-up" origin/main &&
    git -C "$ST/wt-gone-up" push -q -u origin gone-up && g push -q origin --delete gone-up
  g worktree add -q --detach "$ST/wt-detached" origin/main
  g worktree add -q --no-track -b locked "$ST/wt-locked" origin/main && g worktree lock "$ST/wt-locked"
  g worktree add -q --no-track -b missing "$ST/wt-missing" origin/main && rm -rf "$ST/wt-missing"
  g worktree add -q --no-track -b dirty "$ST/wt-dirty" origin/main && : >"$ST/wt-dirty/new.txt"
  g worktree add -q --no-track -b merging "$ST/wt-merging" origin/main &&
    git -C "$ST/wt-merging" commit -q --allow-empty -m side && g branch -q side-tip merging &&
    git -C "$ST/wt-merging" reset -q --hard origin/main &&
    git -C "$ST/wt-merging" merge -q --no-commit --no-ff side-tip >/dev/null 2>&1

  st_run
  ok=1; [ "$RC" -eq 0 ] && sed -n 2p "$ST/out" | grep -qF "$R " && row "$R" | grep -q 'main' && ok=0
  check "the main worktree is listed first and flagged main" "$ok"
  ok=1; row "$ST/wt-gone-up" | grep -qF "(upstream gone)" && ok=0
  check "a branch whose upstream was deleted on the remote shows (upstream gone)" "$ok"
  ok=1; row "$ST/wt-detached" | grep -q detached && ok=0
  check "a detached worktree is flagged detached" "$ok"
  ok=1; row "$ST/wt-locked" | grep -q locked && ok=0
  check "a locked worktree is flagged locked" "$ok"
  ok=1; row "$ST/wt-missing" | grep -q prunable && row "$ST/wt-missing" | grep -q missing && ok=0
  check "a hand-deleted worktree folder is flagged prunable and missing" "$ok"
  ok=1; [ "$(row "$ST/wt-dirty" | awk '{print $3}')" = 1 ] && ok=0
  check "the dirty count reports one untracked file" "$ok"
  ok=1; row "$ST/wt-merging" | grep -qF "op:MERGE_HEAD" && ok=0
  check "an in-progress merge is flagged op:MERGE_HEAD" "$ok"

  st_run --stale 0
  ok=1; [ "$RC" -eq 0 ] && row "$ST/wt-dirty" | grep -q STALE && ! row "$R" | grep -q STALE && ok=0
  check "--stale flags linked worktrees but never the main one" "$ok"
  st_run --stale soon
  ok=1; [ "$RC" -eq 64 ] && ok=0
  check "a non-numeric --stale value is a usage error (exit 64)" "$ok"

  st_run --help
  ok=1; [ "$RC" -eq 0 ] && grep -qF "Usage:" "$ST/out" && ok=0
  check "--help prints usage and exits 0" "$ok"
  st_run --no-such-option
  ok=1; [ "$RC" -eq 64 ] && ok=0
  check "an unknown option is a usage error (exit 64)" "$ok"

  echo "$PASSED/$((PASSED + FAILED)) self-tests passed"
  [ "$FAILED" -eq 0 ]
}

STALE_DAYS=""
while [ $# -gt 0 ]; do
  case $1 in
    --stale) [ $# -ge 2 ] || { echo "usage: wt-overview.sh [--stale DAYS]" >&2; exit 64; }; STALE_DAYS=$2; shift 2
             case $STALE_DAYS in ''|*[!0-9]*) echo "wt-overview: --stale needs a whole number of days" >&2; exit 64 ;; esac ;;
    --selftest) selftest; exit $? ;;
    -h|--help) awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"; exit 0 ;;
    *) echo "usage: wt-overview.sh [--stale DAYS] | --selftest | --help" >&2; exit 64 ;;
  esac
done

git rev-parse --git-dir >/dev/null 2>&1 || { echo "wt-overview: not inside a git repository" >&2; exit 1; }
NOW=$(date +%s)

# Needs git >= 2.31 (rev-parse --path-format); older git echoes the flag back silently.
read -r GIT_MAJ GIT_MIN <<GITVER
$(git --version | sed -n 's/^git version \([0-9]*\)\.\([0-9]*\).*/\1 \2/p')
GITVER
if [ "${GIT_MAJ:-0}" -lt 2 ] || { [ "${GIT_MAJ:-0}" -eq 2 ] && [ "${GIT_MIN:-0}" -lt 31 ]; }; then
  echo "wt-overview: needs git >= 2.31 (found: $(git --version))" >&2; exit 1
fi

ROWS=""
emit() { ROWS="$ROWS$1	$2	$3	$4	$5	$6
"; }

flush_entry() {
  [ -n "$path" ] || return 0
  flags=$extra
  if [ "$bare" -eq 1 ]; then emit "$path" "(bare)" "-" "-" "-" "main,bare"; return 0; fi
  if [ ! -d "$path" ]; then emit "$path" "${branch:-?}" "-" "-" "-" "${flags:+$flags,}missing"; return 0; fi
  # for-each-ref, not rev-parse '@{u}': the latter prints a literal '@{u}' when
  # the upstream was deleted on the remote, which looks like a real upstream.
  up=""; uptrack=""
  if [ -n "$branch" ]; then
    up=$(git -C "$path" for-each-ref --format='%(upstream:short)' "refs/heads/$branch" 2>/dev/null)
    uptrack=$(git -C "$path" for-each-ref --format='%(upstream:track)' "refs/heads/$branch" 2>/dev/null)
  fi
  [ -z "$branch" ] && { branch="(detached $(git -C "$path" rev-parse --short HEAD 2>/dev/null))"; flags="${flags:+$flags,}detached"; }
  dirty=$(git -C "$path" status --porcelain=v1 2>/dev/null | wc -l | tr -d ' ')
  if [ -n "$up" ] && [ "$uptrack" = "[gone]" ]; then
    pos="(upstream gone) $up"
  elif [ -n "$up" ]; then
    read -r behind ahead <<EOF2
$(git -C "$path" rev-list --left-right --count "$up...HEAD" 2>/dev/null || echo "? ?")
EOF2
    pos="+$ahead/-$behind $up"
  else
    pos="(no upstream)"
  fi
  ts=$(git -C "$path" log -1 --format=%ct 2>/dev/null || echo "")
  if [ -n "$ts" ]; then
    days=$(( (NOW - ts) / 86400 )); age="${days}d"
    if [ -n "$STALE_DAYS" ] && [ "$days" -ge "$STALE_DAYS" ] && [ "$is_main" -eq 0 ]; then flags="${flags:+$flags,}STALE"; fi
  else
    age="-"
  fi
  for op in rebase-merge rebase-apply MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD BISECT_LOG; do
    if [ -e "$(git -C "$path" rev-parse --path-format=absolute --git-path "$op" 2>/dev/null)" ]; then
      flags="${flags:+$flags,}op:$op"; break
    fi
  done
  emit "$path" "$branch" "$dirty" "$pos" "$age" "${flags:--}"
}

path=""; branch=""; extra=""; bare=0; is_main=0; n=0
while IFS= read -r line; do
  case $line in
    "worktree "*) flush_entry; path=${line#worktree }; branch=""; bare=0; n=$((n + 1))
                  if [ "$n" -eq 1 ]; then is_main=1; extra="main"; else is_main=0; extra=""; fi ;;
    "branch refs/heads/"*) branch=${line#branch refs/heads/} ;;
    bare) bare=1 ;;
    locked*) extra="${extra:+$extra,}locked" ;;
    prunable*) extra="${extra:+$extra,}prunable" ;;
  esac
done <<EOF
$(git worktree list --porcelain)
EOF
flush_entry

{
  printf 'PATH\tBRANCH\tDIRTY\tAHEAD/BEHIND UPSTREAM\tLAST COMMIT\tFLAGS\n'
  printf '%s' "$ROWS"
} | awk -F'\t' '
  { for (i = 1; i <= NF; i++) { cell[NR, i] = $i; if (length($i) > w[i]) w[i] = length($i) } rows = NR; cols = (NF > cols ? NF : cols) }
  END { for (r = 1; r <= rows; r++) { line = ""; for (i = 1; i <= cols; i++) line = line sprintf("%-" w[i] + 2 "s", cell[r, i]); sub(/ +$/, "", line); print line } }'
