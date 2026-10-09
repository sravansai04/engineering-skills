#!/usr/bin/env bash
# Create or update this repository's issue and pull request labels with the GitHub CLI.
#
# Safe to run any number of times: `gh label create --force` updates the color and
# description of a label that already exists. Labels not listed here are left alone.
# The issue forms in .github/ISSUE_TEMPLATE and .github/dependabot.yml apply some of these
# labels; GitHub silently skips a label that does not exist, so run this once per new repo.
#
# Works with bash 3.2 (the bash macOS ships) and later.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/setup_labels.sh [--repo OWNER/REPO] [--dry-run]

Create or update the repository's labels with `gh label create --force`.

Options:
  -R, --repo OWNER/REPO  repository to label (default: the repository gh resolves
                         from the current directory)
  -n, --dry-run          print the gh commands without running them; needs no gh
                         login and makes no network calls
  -h, --help             show this help and exit

Requires the GitHub CLI (gh), logged in with permission to manage labels, unless
--dry-run is given. Exit status: 0 on success, 1 if any label failed, 2 on a usage error.
EOF
}

# name|color (hex, no #)|description (GitHub allows at most 100 characters)
LABELS='type:bug|D73A4A|A skill or script gives wrong results or fails
type:skill-request|A2EEEF|Proposal for a new skill
type:skill-improvement|7057FF|Improve an existing skill: guidance, triggers or coverage
type:docs|0075CA|Documentation changes
type:ci|EDEDED|CI workflows, validators and repository tooling
type:evals|BFD4F2|New or better trigger or behavior evals
type:security|B60205|Public hardening work; report vulnerabilities privately (SECURITY.md)
plugin:implementation|C5DEF5|Concerns the implementation plugin
plugin:review-suite|C5DEF5|Concerns the review-suite plugin
plugin:data-api|C5DEF5|Concerns the data-api plugin
plugin:workflow|C5DEF5|Concerns the workflow plugin
plugin:frontend|C5DEF5|Concerns the frontend plugin
plugin:skill-dev|C5DEF5|Concerns the skill-dev plugin
status:needs-triage|FBCA04|Waiting for a maintainer to review
status:needs-info|D876E3|Waiting on more information from the reporter
status:accepted|0E8A16|Confirmed and ready to be worked on
status:in-progress|1D76DB|Someone is working on it; see the linked pull request
status:blocked|B60205|Waiting on something outside this issue or pull request
good first issue|7057FF|A small, well-scoped task for a first contribution
help wanted|008672|Maintainers would welcome a contribution here
dependencies|0366D6|Updates a dependency, such as a GitHub Action'

repo=""
dry_run=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    -n|--dry-run)
      dry_run=true
      ;;
    -R|--repo)
      if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        echo "setup_labels.sh: $1 needs a value (OWNER/REPO)" >&2
        exit 2
      fi
      repo="$2"
      shift
      ;;
    --repo=*)
      repo="${1#--repo=}"
      ;;
    *)
      echo "setup_labels.sh: unknown argument: $1 (try --help)" >&2
      exit 2
      ;;
  esac
  shift
done

if [ -n "$repo" ]; then
  case "$repo" in
    */*) ;;
    *)
      echo "setup_labels.sh: --repo must look like OWNER/REPO, got: $repo" >&2
      exit 2
      ;;
  esac
fi

# Check the table before touching anything, so a typo fails here and not halfway through.
table_ok=true
seen="
"
while IFS='|' read -r name color description; do
  if [ -z "$name" ] || [ -z "$description" ]; then
    echo "setup_labels.sh: incomplete label entry: $name|$color|$description" >&2
    table_ok=false
    continue
  fi
  case "$color" in
    [0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]) ;;
    *)
      echo "setup_labels.sh: '$name' has an invalid color: $color" >&2
      table_ok=false
      ;;
  esac
  if [ "${#description}" -gt 100 ]; then
    echo "setup_labels.sh: '$name' has a description over 100 characters" >&2
    table_ok=false
  fi
  case "$seen" in
    *"
$name
"*)
      echo "setup_labels.sh: '$name' is listed twice" >&2
      table_ok=false
      ;;
  esac
  seen="$seen$name
"
done <<EOF
$LABELS
EOF
if [ "$table_ok" != true ]; then
  exit 1
fi

if [ "$dry_run" != true ]; then
  if ! command -v gh > /dev/null 2>&1; then
    echo "setup_labels.sh: the GitHub CLI (gh) is not installed: https://cli.github.com" >&2
    exit 1
  fi
  if ! gh auth status > /dev/null 2>&1; then
    echo "setup_labels.sh: gh is not logged in; run 'gh auth login' first" >&2
    exit 1
  fi
fi

# Run (or, with --dry-run, print) one gh label create call.
create_label() {
  if [ -n "$repo" ]; then
    set -- gh label create "$1" --color "$2" --description "$3" --force --repo "$repo"
  else
    set -- gh label create "$1" --color "$2" --description "$3" --force
  fi
  if [ "$dry_run" = true ]; then
    printf '%q ' "$@"
    printf '\n'
    return 0
  fi
  "$@" < /dev/null
}

total=0
failed=0
while IFS='|' read -r name color description; do
  total=$((total + 1))
  if create_label "$name" "$color" "$description"; then
    if [ "$dry_run" != true ]; then
      echo "ok      $name"
    fi
  else
    echo "failed  $name" >&2
    failed=$((failed + 1))
  fi
done <<EOF
$LABELS
EOF

if [ "$dry_run" = true ]; then
  echo "Dry run: $total labels checked, nothing changed."
elif [ "$failed" -gt 0 ]; then
  echo "$failed of $total labels failed." >&2
  exit 1
else
  echo "All $total labels are in place."
fi
