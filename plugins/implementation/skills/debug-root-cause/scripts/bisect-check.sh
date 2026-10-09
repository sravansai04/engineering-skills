#!/usr/bin/env bash
# bisect-check.sh - adapter for `git bisect run`.
#
# `git bisect run` reads its verdict from the exit code: 0 = good,
# 1-127 except 125 = bad, 125 = skip (untestable), 128 and above aborts the
# whole bisect. Real test commands do not respect that contract: a crash by
# signal exits 128+N (aborts bisect), a mistyped command exits 127 (counted
# as bad), some runners exit 125 for their own reasons (silently skips), and
# a broken build or an unrelated failure looks exactly like "bad". This
# script turns every outcome into a verdict bisect can trust.
#
# Usage (from inside the repository being bisected):
#   git bisect run /path/to/bisect-check.sh [options] -- TEST [ARGS...]
#
#   -b BUILD  shell command that prepares this revision (install deps, compile).
#             If it fails, the revision is skipped (exit 125), not marked bad.
#   -n RUNS   run TEST this many times; a failing run marks the revision bad
#             (default: 1). Use more than 1 for intermittent bugs.
#   -s CODES  comma-separated TEST exit codes meaning "could not test this
#             revision". These skip the revision instead of marking it bad.
#             pytest: 2 interrupted or collection error (e.g. ImportError),
#             3 internal error, 4 usage error, 5 no tests collected.
#   -m REGEX  extended regex matching output that only THIS bug produces (its
#             assertion message or error text). A failing run whose output
#             does not match skips the revision: a different failure is not
#             evidence of this bug.
#   -t SECS   kill a TEST run, and its child processes, after SECS seconds and
#             treat it as a failure with exit 124. Set it well above a normal
#             run's duration, unless the hang is the bug you are bisecting.
#   -h        show this help (also --help)
#   --selftest  check the verdict mapping with throwaway commands and exit
#
# Verdict for a failing run, in order: exit code listed in -s -> skip;
# exit 126 or 127 (TEST not executable or not found) -> abort; -m given and
# the output does not match -> skip; otherwise -> bad. A crash by signal
# (exit 128 and up) is bad, not an abort. The tail of each failing run's
# output is printed, so every verdict can be audited from the bisect log.
#
# TEST runs as-is, without a shell. Wrap pipelines in `sh -c '...'`.
# Keep TEST (and any repro script it calls) OUTSIDE the repository, so every
# checked-out revision runs the same check.
#
# Exit status: 0 good, 1 bad, 125 skip, 255 abort (usage error, or TEST could
# not be run). Git aborts the bisect on any status of 128 or more, so a typo
# stops the search instead of quietly blaming an innocent commit.

set -u

usage() {
  sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
}

abort() {
  echo "bisect-check: $* -> abort (255)" >&2
  exit 255
}

# Runs this script against throwaway commands and checks every verdict path.
# Needs only POSIX tools; no git repository and no network.
selftest() {
  self="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
  work="$(mktemp -d "${TMPDIR:-/tmp}/bisect-check-selftest.XXXXXX")" || return 1
  fails=0
  expect() {  # expect WANT LABEL ARGS...
    want="$1"; label="$2"; shift 2
    (cd "$work" && bash "$self" "$@" >"$work/out" 2>&1 </dev/null)
    got=$?
    if [ "$got" -eq "$want" ]; then
      echo "ok   $label (exit $got)"
    else
      echo "FAIL $label: want exit $want, got $got"
      sed 's/^/     | /' "$work/out"
      fails=$((fails + 1))
    fi
  }
  expect 0   "passing test -> good" -- true
  expect 1   "failing test -> bad" -- false
  expect 1   "test's own exit 125 -> bad, not a silent skip" -- sh -c 'exit 125'
  expect 1   "crash by signal (128+N) -> bad, not an abort" -- sh -c 'kill -9 $$'
  expect 255 "command not found (127) -> abort" -- ./no-such-test-command
  expect 125 "exit code listed in -s -> skip" -s 4,5 -- sh -c 'exit 5'
  expect 125 "failed build (-b) -> skip" -b 'exit 1' -- true
  expect 125 "failure without the -m text -> skip" -m 'KeyError' -- sh -c 'echo other failure; exit 1'
  expect 1   "failure with the -m text -> bad" -m 'KeyError' -- sh -c 'echo KeyError: user; exit 1'
  : >"$work/count"
  # shellcheck disable=SC2016  # the counter command is expanded by the inner sh, on purpose
  expect 1   "-n 3 catches a failure on the second run" -n 3 -- sh -c 'echo x >>count; [ "$(wc -l <count)" -ne 2 ]'
  expect 0   "-n 3 with three passing runs -> good" -n 3 -- true
  expect 1   "-t timeout kills a hang -> bad" -t 1 -- sleep 30
  expect 255 "no TEST command -> abort" -n 2
  expect 255 "bad -n value -> abort" -n x -- true
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

build_cmd=""
runs=1
skip_codes=""
match=""
match_set=0
timeout=0
grace=5

# Accept the long form too; getopts only parses single-letter options.
for arg in "$@"; do
  case "$arg" in
    --help) usage; exit 0 ;;
    --selftest) selftest; exit $? ;;
    --) break ;;
  esac
done

while getopts ":b:n:s:m:t:h" opt; do
  case "$opt" in
    b) build_cmd="$OPTARG" ;;
    n) runs="$OPTARG" ;;
    s) skip_codes="$OPTARG" ;;
    m) match="$OPTARG"; match_set=1 ;;
    t) timeout="$OPTARG" ;;
    h) usage; exit 0 ;;
    :) abort "option -$OPTARG needs a value" ;;
    *) abort "unknown option -$OPTARG (try -h or --help)" ;;
  esac
done
shift $((OPTIND - 1))

[ "$#" -gt 0 ] || abort "no test command given. Usage: bisect-check.sh [options] -- TEST [ARGS...]"
case "$runs" in
  ''|*[!0-9]*) abort "-n must be a positive integer" ;;
esac
[ "$runs" -ge 1 ] || abort "-n must be at least 1"
case "$timeout" in
  ''|*[!0-9]*) abort "-t must be a whole number of seconds" ;;
esac
case "$skip_codes" in
  *[!0-9,]*) abort "-s takes comma-separated exit codes, e.g. 4,5" ;;
esac
if [ "$match_set" -eq 1 ]; then
  [ -n "$match" ] || abort "-m needs a non-empty pattern"
  grep -Eq -e "$match" /dev/null 2>/dev/null
  [ "$?" -ne 2 ] || abort "-m pattern is not a valid extended regex: $match"
fi

rev="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

log="$(mktemp "${TMPDIR:-/tmp}/bisect-check.XXXXXX")" || abort "cannot create a temporary file"
flag="$log.timed-out"
pid=""
wd=""

# shellcheck disable=SC2329  # called by the EXIT trap
cleanup() {
  if [ -n "$pid" ]; then kill -KILL -- "-$pid" 2>/dev/null; fi
  if [ -n "$wd" ]; then kill -TERM "$wd" 2>/dev/null; fi
  rm -f "$log" "$flag"
}
trap cleanup EXIT
trap 'exit 255' INT TERM

if [ -n "$build_cmd" ]; then
  if ! sh -c "$build_cmd"; then
    echo "bisect-check: [$rev] build failed -> skip (125)"
    exit 125
  fi
fi

is_skip_code() {
  code="$1"
  old_ifs=$IFS
  IFS=','
  for c in $skip_codes; do
    if [ "$c" = "$code" ]; then
      IFS=$old_ifs
      return 0
    fi
  done
  IFS=$old_ifs
  return 1
}

# Runs in the background: after $timeout seconds, if the test is still
# running, mark the run as timed out and TERM its process group, then KILL
# it after a grace period.
watchdog() {
  sp=""
  trap 'if [ -n "$sp" ]; then kill "$sp" 2>/dev/null; fi; exit 0' TERM
  sleep "$timeout" & sp=$!
  wait "$sp"
  kill -0 "$1" 2>/dev/null || exit 0
  : >"$flag"
  kill -TERM -- "-$1" 2>/dev/null
  sleep "$grace" & sp=$!
  wait "$sp"
  kill -KILL -- "-$1" 2>/dev/null
}

# Runs TEST once with output captured in $log; sets $status (124 on timeout).
run_test() {
  : >"$log"
  if [ "$timeout" -eq 0 ]; then
    "$@" </dev/null >>"$log" 2>&1
    status=$?
    return
  fi
  rm -f "$flag"
  set -m                        # own process group, so a timeout reaches child processes too
  "$@" </dev/null >>"$log" 2>&1 &
  pid=$!
  set +m
  watchdog "$pid" &
  wd=$!
  wait "$pid" 2>/dev/null
  status=$?
  kill -TERM "$wd" 2>/dev/null
  wait "$wd" 2>/dev/null
  if [ -e "$flag" ]; then
    kill -KILL -- "-$pid" 2>/dev/null
    printf '\n[bisect-check: killed after %ss timeout]\n' "$timeout" >>"$log"
    status=124
  fi
  pid=""
  wd=""
}

show_tail() {
  echo "bisect-check: [$rev] last lines of run $1 output:" >&2
  tail -n 40 "$log" | sed 's/^/  | /' >&2
}

i=1
while [ "$i" -le "$runs" ]; do
  run_test "$@"
  if [ "$status" -ne 0 ]; then
    show_tail "$i"
    what="exit $status"
    [ "$status" -ne 124 ] || [ "$timeout" -eq 0 ] || what="timed out after ${timeout}s, exit 124"
    if [ -n "$skip_codes" ] && is_skip_code "$status"; then
      echo "bisect-check: [$rev] run $i/$runs: $what is listed in -s -> skip (125)"
      exit 125
    fi
    if [ "$status" -eq 126 ] || [ "$status" -eq 127 ]; then
      abort "[$rev] TEST could not be run ($what: not executable or not found). Check the path, or list the code in -s if it really means 'cannot test this revision'"
    fi
    if [ "$match_set" -eq 1 ] && ! grep -Eq -e "$match" "$log"; then
      echo "bisect-check: [$rev] run $i/$runs failed ($what) but the output does not match -m -> skip (125)"
      exit 125
    fi
    echo "bisect-check: [$rev] run $i/$runs failed ($what) -> bad (1)"
    exit 1
  fi
  i=$((i + 1))
done

echo "bisect-check: [$rev] passed $runs/$runs runs -> good (0)"
exit 0
