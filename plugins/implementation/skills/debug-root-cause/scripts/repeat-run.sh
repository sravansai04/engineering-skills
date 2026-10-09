#!/usr/bin/env bash
# repeat-run.sh - run one command many times to measure how often it fails,
# or to stop at the first failure and keep its output.
#
# Use it to:
#   - measure the reproduction rate of an intermittent bug before fixing it
#   - capture the full output of a rare failing run, or a dump of a hung one
#   - check a fix: enough consecutive passes to trust it (see the summary line)
#
# Usage:
#   repeat-run.sh [-n RUNS] [-u] [-k] [-o DIR] [-t SECS [-d CMD]] -- COMMAND [ARGS...]
#
#   -n RUNS  how many times to run COMMAND (default: 20)
#   -u       stop at the first failure ("until fail")
#   -k       keep logs of passing runs too (default: keep failing runs only)
#   -o DIR   where to write run logs (default: a new temporary directory)
#   -t SECS  per-run timeout. A run still going after SECS seconds counts as a
#            failure (TIMEOUT, exit 124); it and its child processes then get
#            TERM and, 5 seconds later, KILL. Use it whenever COMMAND can hang,
#            or the first hung run blocks the loop forever.
#   -d CMD   with -t: shell command run just before the kill, with $PID set to
#            the stuck command's process ID (also its process group ID), so a
#            hang leaves evidence. Its output is appended to that run's log.
#            Single-quote it so your shell does not expand $PID. Examples:
#            'jcmd $PID Thread.print', 'py-spy dump --pid $PID', or
#            'kill -QUIT $PID' (Go prints every goroutine and exits; a JVM
#            prints a thread dump). If COMMAND is a wrapper (sh -c, a build
#            tool, a test launcher), `pgrep -g $PID` lists its processes.
#   -h       show this help (also --help)
#   --selftest  check counting, -u, -t, -d, log keeping and usage errors with
#            throwaway commands, then exit
#
# COMMAND runs as-is, without a shell. To run a pipeline or chain commands,
# pass it through a shell explicitly:
#   repeat-run.sh -n 200 -u -- sh -c 'make build && ./bin/app --selftest'
#
# The summary turns the observed failures into a conservative failure rate
# (the 95% Wilson lower bound) and the number of consecutive passes a fix
# needs before you can trust it at about 95% confidence.
#
# Exit status: 0 if every run passed, 1 if at least one run failed or timed
#              out, 2 on a usage error.

set -u

usage() {
  sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
}

# Runs this script against throwaway commands and checks its contract.
# Needs only POSIX tools; no network.
selftest() {
  self="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
  work="$(mktemp -d "${TMPDIR:-/tmp}/repeat-run-selftest.XXXXXX")" || return 1
  fails=0
  # A command that fails on every second run, counting in $work/count.
  # shellcheck disable=SC2016  # expanded by the inner sh, on purpose
  alt='echo x >>count; [ $(( $(wc -l <count) % 2 )) -eq 1 ]'
  check() {  # check LABEL WANT_EXIT NEEDLE ARGS...
    label="$1"; want="$2"; needle="$3"; shift 3
    : >"$work/count"
    (cd "$work" && bash "$self" "$@" >"$work/out" 2>&1 </dev/null)
    got=$?
    if [ "$got" -eq "$want" ] && grep -q -- "$needle" "$work/out"; then
      echo "ok   $label"
    else
      echo "FAIL $label: want exit $want and '$needle', got exit $got"
      sed 's/^/     | /' "$work/out"
      fails=$((fails + 1))
    fi
  }
  check "all passing runs exit 0" 0 "0/5 failed" -n 5 -- true
  check "alternate failures are counted" 1 "2/4 failed" -n 4 -o "$work/logs" -- sh -c "$alt"
  if [ ! -e "$work/logs/run-1.log" ] && [ -e "$work/logs/run-2.log" ]; then
    echo "ok   only failing runs keep their logs"
  else
    echo "FAIL log keeping: run-1.log should be gone and run-2.log kept"; fails=$((fails + 1))
  fi
  check "-u stops at the first failure" 1 "stopped at the first failure (run 2" -n 10 -u -- sh -c "$alt"
  check "-t turns a hang into a TIMEOUT" 1 "TIMEOUT after 1s" -n 1 -t 1 -o "$work/hang" -- sleep 30
  # shellcheck disable=SC2016  # $PID is set by the script when the hook runs
  check "-d runs the dump hook before the kill" 1 "TIMEOUT" -n 1 -t 1 -o "$work/dump" -d 'echo dumped pid $PID' -- sleep 30
  if grep -q 'dumped pid [0-9]' "$work/dump/run-1.log" 2>/dev/null; then
    echo "ok   the dump output lands in the run log"
  else
    echo "FAIL the dump output is missing from the run log"; fails=$((fails + 1))
  fi
  check "no command is a usage error" 2 "no command given" -n 3
  check "-d without -t is a usage error" 2 "-d needs -t" -d 'true' -- true
  check "-n 0 is a usage error" 2 "-n must be at least 1" -n 0 -- true
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

runs=20
until_fail=0
keep_all=0
out_dir=""
timeout=0
dump_cmd=""
grace=5

# Accept the long form too; getopts only parses single-letter options.
for arg in "$@"; do
  case "$arg" in
    --help) usage; exit 0 ;;
    --selftest) selftest; exit $? ;;
    --) break ;;
  esac
done

while getopts ":n:uko:t:d:h" opt; do
  case "$opt" in
    n) runs="$OPTARG" ;;
    u) until_fail=1 ;;
    k) keep_all=1 ;;
    o) out_dir="$OPTARG" ;;
    t) timeout="$OPTARG" ;;
    d) dump_cmd="$OPTARG" ;;
    h) usage; exit 0 ;;
    :) echo "repeat-run: option -$OPTARG needs a value" >&2; exit 2 ;;
    *) echo "repeat-run: unknown option -$OPTARG (try -h or --help)" >&2; exit 2 ;;
  esac
done
shift $((OPTIND - 1))

if [ "$#" -eq 0 ]; then
  echo "repeat-run: no command given. Usage: repeat-run.sh [options] -- COMMAND [ARGS...]" >&2
  exit 2
fi

case "$runs" in
  ''|*[!0-9]*) echo "repeat-run: -n must be a positive integer" >&2; exit 2 ;;
esac
if [ "$runs" -lt 1 ]; then
  echo "repeat-run: -n must be at least 1" >&2
  exit 2
fi
case "$timeout" in
  ''|*[!0-9]*) echo "repeat-run: -t must be a whole number of seconds" >&2; exit 2 ;;
esac
if [ -n "$dump_cmd" ] && [ "$timeout" -eq 0 ]; then
  echo "repeat-run: -d needs -t (the dump runs when a run times out)" >&2
  exit 2
fi

if [ -z "$out_dir" ]; then
  tmp_base="${TMPDIR:-/tmp}"
  out_dir="$(mktemp -d "${tmp_base%/}/repeat-run.XXXXXX")" || exit 2
else
  mkdir -p "$out_dir" || exit 2
fi

flag="$out_dir/.timed-out"
pid=""
wd=""
log=""

# shellcheck disable=SC2329  # called by the EXIT trap
cleanup() {
  if [ -n "$pid" ]; then kill -KILL -- "-$pid" 2>/dev/null; fi
  if [ -n "$wd" ]; then kill -TERM "$wd" 2>/dev/null; fi
  rm -f "$flag"
}
trap cleanup EXIT
trap 'echo "repeat-run: interrupted; logs are in $out_dir" >&2; exit 130' INT TERM

# Runs in the background: after $timeout seconds, if the command is still
# running, mark the run as timed out, run the dump hook, then TERM the
# command's process group and KILL it after a grace period.
watchdog() {
  sp=""
  trap 'if [ -n "$sp" ]; then kill "$sp" 2>/dev/null; fi; exit 0' TERM
  sleep "$timeout" & sp=$!
  wait "$sp"
  kill -0 "$1" 2>/dev/null || exit 0
  : >"$flag"
  if [ -n "$dump_cmd" ]; then
    printf '\n--- repeat-run: timed out after %ss; dump hook: %s\n' "$timeout" "$dump_cmd" >>"$log"
    PID="$1" sh -c "$dump_cmd" </dev/null >>"$log" 2>&1 &
    dp=$!
    n=0
    while kill -0 "$dp" 2>/dev/null && [ "$n" -lt 30 ]; do
      sleep 1
      n=$((n + 1))
    done
    kill -KILL "$dp" 2>/dev/null
    sleep 1   # let the stuck process flush a dump it writes to its own output
  fi
  kill -TERM -- "-$1" 2>/dev/null
  sleep "$grace" & sp=$!
  wait "$sp"
  kill -KILL -- "-$1" 2>/dev/null
}

# Runs COMMAND once with output in $log; sets $status (124 on timeout).
run_command() {
  : >"$log"
  if [ "$timeout" -eq 0 ]; then
    "$@" </dev/null >>"$log" 2>&1
    status=$?
    return
  fi
  rm -f "$flag"
  set -m                        # own process group, so the timeout reaches child processes too
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
    printf '\n--- repeat-run: killed after %ss timeout\n' "$timeout" >>"$log"
    status=124
    rm -f "$flag"
  fi
  pid=""
  wd=""
}

echo "repeat-run: command: $*"
echo "repeat-run: logs:    $out_dir"

failures=0
timeouts=0
completed=0
first_failure=""
i=1
while [ "$i" -le "$runs" ]; do
  log="$out_dir/run-$i.log"
  timed_out=0
  start=$(date +%s)
  run_command "$@"
  elapsed=$(( $(date +%s) - start ))
  completed=$i
  if [ "$timeout" -gt 0 ] && [ "$status" -eq 124 ]; then
    timed_out=1
  fi

  if [ "$status" -eq 0 ]; then
    [ "$keep_all" -eq 1 ] || rm -f "$log"
    printf 'run %d/%d: pass (%ss)\n' "$i" "$runs" "$elapsed"
  else
    failures=$((failures + 1))
    [ -n "$first_failure" ] || first_failure=$i
    if [ "$timed_out" -eq 1 ]; then
      timeouts=$((timeouts + 1))
      printf 'run %d/%d: TIMEOUT after %ss log=%s\n' "$i" "$runs" "$timeout" "$log"
    else
      printf 'run %d/%d: FAIL exit=%d (%ss) log=%s\n' "$i" "$runs" "$status" "$elapsed" "$log"
    fi
    if [ "$until_fail" -eq 1 ]; then
      break
    fi
  fi
  i=$((i + 1))
done

echo "----"
if [ "$failures" -eq 0 ]; then
  # Zero failures in n runs bounds the true failure rate below about 3/n at
  # 95% confidence ("rule of three").
  awk -v n="$completed" 'BEGIN {
    bound = 300 / n
    if (bound >= 100) {
      printf "repeat-run: 0/%d failed. Too few runs to bound the failure rate; use 30 or more.\n", n
    } else {
      printf "repeat-run: 0/%d failed. At ~95%% confidence the true failure rate is below %.2f%%.\n", n, bound
    }
  }'
  exit 0
fi

if [ "$timeouts" -gt 0 ]; then
  echo "repeat-run: timeouts among the failures: $timeouts."
fi

if [ "$until_fail" -eq 1 ]; then
  echo "repeat-run: stopped at the first failure (run $first_failure of up to $runs)."
  echo "repeat-run: for a failure-rate estimate, rerun without -u."
  exit 1
fi

# The raw ratio f/n overstates a rate seen only a few times, and a pass count
# derived from it is too small. Use the 95% Wilson lower bound instead, then
# ask how many consecutive passes would have shown at least one failure with
# 95% probability if the bug were still there at that rate.
awk -v f="$failures" -v n="$completed" 'BEGIN {
  p = f / n
  z = 1.96
  low = (p + z*z/(2*n) - z * sqrt(p*(1-p)/n + z*z/(4*n*n))) / (1 + z*z/n)
  need = log(0.05) / log(1 - low)
  printf "repeat-run: %d/%d failed (%.1f%%). Conservative rate (95%% lower bound): %.1f%%.\n", f, n, 100 * p, 100 * low
  printf "repeat-run: to trust a fix at ~95%% confidence, expect about %d consecutive passes under the same conditions.\n", int(need + 0.999)
  if (f < 10) {
    print "repeat-run: fewer than 10 failures observed; the rate is rough. More runs tighten it and usually lower the pass count needed."
  }
}'
exit 1
