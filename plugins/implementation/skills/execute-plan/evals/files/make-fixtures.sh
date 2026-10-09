#!/usr/bin/env bash
# Build the git repositories that the execute-plan evals run against.
#
# Usage: bash make-fixtures.sh <empty-target-dir> [scenario ...]
#        bash make-fixtures.sh -h | --help
#   Scenarios (default: all): coupons reports-api payments-retry loyalty-tiers bigger-pages
#
# Each scenario becomes <target>/<scenario>, a git repository on `main` with one initial
# commit. payments-retry additionally gets a `feat/payments-retry` branch holding T1-T4 as
# commits with `Plan-Task:` trailers, plus T5 left uncommitted in the working tree.
# Runs modify the repositories, so build a fresh copy for every run, then start the session
# with the scenario directory as its working directory.
#
# Needs git 2.32 or later and python3 (the fixtures use the standard library only).
set -euo pipefail

case "${1:-}" in
  -h|--help)
    # Print the header comment block above, without the leading "# ".
    awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"
    exit 0
    ;;
  -*)
    echo "unknown option: $1 (try --help)" >&2
    exit 2
    ;;
esac

here=$(cd "$(dirname "$0")" && pwd)
target=${1:?usage: make-fixtures.sh <empty-target-dir> [scenario ...]}
shift
if [ "$#" -gt 0 ]; then
  scenarios=("$@")
else
  scenarios=(coupons reports-api payments-retry loyalty-tiers bigger-pages)
fi

mkdir -p "$target"
target=$(cd "$target" && pwd)

commit_message() {
  case "$1" in
    T1) echo "feat(payments): add RetryPolicy" ;;
    T2) echo "feat(payments): add backoff delays" ;;
    T3) echo "feat(payments): classify retryable errors" ;;
    T4) echo "feat(payments): add retry helper" ;;
  esac
}

# set_status <repo> <task> <status>: update one row of the plan's Progress table.
set_status() {
  local plan="$1/docs/plans/payments-retry.md"
  sed -i.bak "s/^| $2 | [a-z ]* |/| $2 | $3 |/" "$plan"
  rm -f "$plan.bak"
}

for scenario in "${scenarios[@]}"; do
  src="$here/$scenario"
  repo="$target/$scenario"
  if [ ! -d "$src" ]; then
    echo "unknown scenario: $scenario" >&2
    exit 2
  fi
  if [ -e "$repo" ]; then
    echo "$repo already exists; use an empty target directory" >&2
    exit 2
  fi

  mkdir -p "$repo"
  (cd "$src" && tar cf - --exclude=_history --exclude=_uncommitted --exclude=__pycache__ .) |
    (cd "$repo" && tar xf -)
  printf '__pycache__/\n*.pyc\n' > "$repo/.gitignore"

  git -C "$repo" init -q -b main
  git -C "$repo" config user.name "Fixture Author"
  git -C "$repo" config user.email "fixture@example.invalid"
  git -C "$repo" add -A
  git -C "$repo" commit -q -m "chore: initial import"

  if [ "$scenario" = payments-retry ]; then
    git -C "$repo" switch -q -c feat/payments-retry
    for task in T1 T2 T3 T4; do
      cp -R "$src/_history/$task/." "$repo/"
      set_status "$repo" "$task" "done"
      git -C "$repo" add -A
      git -C "$repo" commit -q -m "$(commit_message "$task")" --trailer "Plan-Task: $task"
    done
    cp -R "$src/_uncommitted/." "$repo/"
    set_status "$repo" T5 "in progress"
  fi

  echo "built $repo ($(git -C "$repo" branch --show-current))"
done
