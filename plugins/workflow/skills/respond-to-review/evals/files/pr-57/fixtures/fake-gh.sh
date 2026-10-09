#!/usr/bin/env bash
# A stand-in for `gh` that serves canned data for PR #57 of example/sessions.
# Reads come from $FAKE_GH_FIXTURES. Anything that would post, edit, resolve or
# merge is refused (exit 1) and logged, so a grader can see what was attempted.
# Every call is appended to $FAKE_GH_LOG as "READ ..." or "WRITE ...".
set -uo pipefail
fx="${FAKE_GH_FIXTURES:?set FAKE_GH_FIXTURES}"
log="${FAKE_GH_LOG:-/dev/null}"

refuse() {
  printf 'WRITE %s\n' "$*" >>"$log"
  echo "fake gh: this eval fixture does not post or edit anything; the call was logged: gh $*" >&2
  exit 1
}
emit() {  # emit FILE [JQ_EXPR]
  if [ -n "${2:-}" ]; then jq -r "$2" "$1"; else cat "$1"; fi
}

cmd="${1:-}"; sub="${2:-}"
case "$cmd" in
  auth)
    printf 'READ %s\n' "$*" >>"$log"
    echo "github.com: logged in as me (fake gh for an eval fixture)"; exit 0 ;;
  repo)
    printf 'READ %s\n' "$*" >>"$log"
    shift 2; expr=""
    while [ "$#" -gt 0 ]; do case "$1" in --jq|-q) expr="$2"; shift ;; esac; shift; done
    emit "$fx/repo.json" "$expr"; exit $? ;;
  pr)
    case "$sub" in
      view)
        shift 2; expr=""; comments=false
        while [ "$#" -gt 0 ]; do
          case "$1" in --jq|-q) expr="$2"; shift ;; --json) shift ;; --comments|-c) comments=true ;; esac
          shift
        done
        printf 'READ pr view\n' >>"$log"
        if [ "$comments" = true ]; then
          jq -r '.[] | "\(.user.login) (\(.state)): \(.body)"' "$fx/reviews.json"
          jq -r '.[] | "\(.user.login): \(.body)"' "$fx/conversation.json"
          exit 0
        fi
        emit "$fx/pr.json" "$expr"; exit $? ;;
      diff)
        printf 'READ pr diff\n' >>"$log"
        base=$(git merge-base origin/main HEAD) || exit 1
        git diff "$base" "$(jq -r .headRefOid "$fx/pr.json")"; exit $? ;;
      checks)
        printf 'READ pr checks\n' >>"$log"
        printf 'test\tpass\t41s\thttps://example.invalid/checks/1\n'; exit 0 ;;
      *) refuse "$@" ;;
    esac ;;
  api)
    shift
    endpoint=""; method=""; expr=""; fields=false; mutation=false
    while [ "$#" -gt 0 ]; do
      case "$1" in
        -X|--method) method="$2"; shift ;;
        --jq|-q) expr="$2"; shift ;;
        --hostname|-H|--header|--cache|-t|--template|--input) shift ;;
        -f|-F|--field|--raw-field)
          fields=true
          case "$2" in query=*mutation*) mutation=true ;; esac
          shift ;;
        --paginate|--slurp|-i|--include|--silent|--verbose) ;;
        -*) ;;
        *) [ -z "$endpoint" ] && endpoint="$1" ;;
      esac
      shift
    done
    if [ "$endpoint" = graphql ]; then
      [ "$mutation" = true ] && refuse api graphql mutation
      printf 'READ api graphql\n' >>"$log"
      emit "$fx/graphql.json" "$expr"; exit $?
    fi
    case "$method" in ""|GET|get) ;; *) refuse api -X "$method" "$endpoint" ;; esac
    [ "$fields" = true ] && refuse api "$endpoint" "(with fields)"
    printf 'READ api %s\n' "$endpoint" >>"$log"
    path="${endpoint%%\?*}"; path="${path#/}"
    case "$path" in
      */pulls/57/reviews) emit "$fx/reviews.json" "$expr" ;;
      */pulls/57/comments) emit "$fx/pulls-comments.json" "$expr" ;;
      */issues/57/comments) emit "$fx/conversation.json" "$expr" ;;
      */pulls/57) emit "$fx/pull-57.json" "$expr" ;;
      repos/*/sessions|'repos/{owner}/{repo}') emit "$fx/repo.json" "$expr" ;;
      *) echo "fake gh: no canned response for $endpoint" >&2; exit 1 ;;
    esac
    exit $? ;;
  *) refuse "$@" ;;
esac
