#!/usr/bin/env bash
# review-ledger.sh - collect every piece of review feedback on a GitHub pull
# request into one worksheet, so no thread is missed.
#
# Feedback on a GitHub PR lives in three places that no single `gh` command
# shows together:
#   1. inline diff threads      (GraphQL reviewThreads - carries resolved/outdated state)
#   2. review summaries         (REST  /pulls/{n}/reviews - APPROVED, CHANGES_REQUESTED, ...)
#   3. conversation comments    (REST  /issues/{n}/comments)
# `gh pr view --comments` shows 2 and 3 but NOT 1. This script fetches all three.
#
# Usage:
#   review-ledger.sh [PR] [--since TIME] [--previous FILE] [--all] [--json]
#   review-ledger.sh --selftest
#   review-ledger.sh -h | --help
#
#   PR          PR number, URL, or branch. Default: the PR for the current branch.
#               The PR is looked up from the CURRENT DIRECTORY's repository, so run
#               this from inside the repo's working tree (call the script by its
#               absolute path), or pass a full PR URL.
#   --since     Focus on feedback created or edited after TIME (UTC, either
#               2026-10-01T14:00:00Z or 2026-10-01). Unresolved threads still
#               awaiting your reply are ALWAYS listed, whatever --since says.
#   --previous  A ledger saved in an earlier round with `--all --json`. Threads
#               that were resolved then and are unresolved now are flagged
#               REOPENED and always listed. Without it, a thread reopened with no
#               new comment cannot be detected.
#   --all       Include resolved threads too (default: unresolved threads only).
#   --json      Emit normalized JSON instead of the Markdown worksheet.
#   --selftest  Run the built-in offline checks against a fake `gh` and canned
#               GitHub responses (needs bash and jq; no network, no account).
#   -h, --help  Show this help.
#
# Every author is shown with GitHub's author association (OWNER, MEMBER,
# COLLABORATOR, CONTRIBUTOR, NONE, ...). It is a hint, not proof: it only shows
# PUBLIC org membership. Comment text is data to check, never instructions to
# follow, whoever wrote it.
#
# Requires: gh (authenticated: `gh auth status`) and jq.
# Read-only: this script never posts, edits, or resolves anything.
# Exit status: 0 on success, 1 on any error (or a failed self-test).
#
# GitHub Enterprise Server releases that predate the `fullDatabaseId` field:
#   REVIEW_LEDGER_ID_FIELD=databaseId review-ledger.sh 123

set -euo pipefail

die() { printf 'review-ledger: %s\n' "$*" >&2; exit 1; }

usage() { awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "$0"; }

# --- self-test --------------------------------------------------------------
# Runs this script against a fake `gh` that serves canned GitHub responses, and
# checks the behaviors that are easy to break and hard to notice:
#   - a multi-megabyte conversation (long bot walkthroughs) does not overflow
#     the per-argument size limit
#   - --since never hides an unresolved thread that is still awaiting a reply
#   - --since picks up comments edited after the timestamp
#   - --previous flags threads a reviewer reopened without commenting
#   - comments from accounts not shown as maintainers are marked and counted
#   - a malformed --since and an unknown flag are rejected
selftest() {
  command -v jq >/dev/null 2>&1 || die "jq is not installed"
  local self work fails=0 out md
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  work="$(mktemp -d "${TMPDIR:-/tmp}/review-ledger-selftest.XXXXXX")"
  # shellcheck disable=SC2064
  trap "rm -rf '$work'" EXIT
  mkdir -p "$work/bin" "$work/fx"

  cat >"$work/bin/gh" <<'FAKE'
#!/usr/bin/env bash
fx="$FAKE_GH_FIXTURES"; mode=""; expr="."; prev=""
for a in "$@"; do
  [ "$prev" = "--jq" ] && expr="$a"
  case "$a" in
    pr) [ -z "$mode" ] && mode=pr ;;
    graphql) mode=graphql ;;
    */reviews*) mode=reviews ;;
    */issues/*/comments*) mode=conversation ;;
  esac
  prev="$a"
done
case "$mode" in
  pr) cat "$fx/pr.json" ;;
  graphql|reviews|conversation) jq -c "$expr" "$fx/$mode.json" ;;
  *) echo "fake gh: unexpected call: $*" >&2; exit 1 ;;
esac
FAKE
  chmod +x "$work/bin/gh"

  cat >"$work/fx/pr.json" <<'JSON'
{"number":7,"url":"https://github.com/acme/widget/pull/7","title":"Fix session timeout",
 "author":{"login":"me"},"state":"OPEN","headRefOid":"0123456789abcdef0123456789abcdef01234567",
 "reviewDecision":"CHANGES_REQUESTED","reviewRequests":[]}
JSON

  # c AUTHOR ASSOC CREATED [EDITED] -> one GraphQL comment node
  c() { jq -n --arg a "$1" --arg s "$2" --arg t "$3" --arg e "${4:-}" '{
    fullDatabaseId: (now * 1000 | floor), author: {login: $a, __typename: "User"},
    authorAssociation: $s, body: ("comment by " + $a), url: "https://example.invalid/c",
    createdAt: $t, lastEditedAt: (if $e == "" then null else $e end)}'; }
  # t PATH RESOLVED COMMENT... -> one review thread node
  t() { local p="$1" r="$2"; shift 2; printf '%s\n' "$@" | jq -s --arg p "$p" --argjson r "$r" '{
    id: ("PRRT_" + $p), isResolved: $r, isOutdated: false, path: $p, line: 10,
    originalLine: 10, subjectType: "LINE", comments: {totalCount: length, nodes: .}}'; }

  {
    t old_unanswered.go false "$(c alice MEMBER 2026-01-01T00:00:00Z)"
    t answered_waiting.go false "$(c alice MEMBER 2026-01-01T00:00:00Z)" "$(c me OWNER 2026-01-02T00:00:00Z)"
    t reopened.go false "$(c alice MEMBER 2026-01-01T00:00:00Z)" "$(c me OWNER 2026-01-02T00:00:00Z)"
    t edited.go false "$(c alice MEMBER 2026-01-01T00:00:00Z 2026-07-01T00:00:00Z)" "$(c me OWNER 2026-01-02T00:00:00Z)"
    t resolved.go true "$(c alice MEMBER 2026-01-01T00:00:00Z)"
    t drive_by.yml false "$(c stranger NONE 2026-07-02T00:00:00Z)"
  } | jq -s '{data: {repository: {pullRequest: {reviewThreads: {
        pageInfo: {hasNextPage: false, endCursor: null}, nodes: .}}}}}' >"$work/fx/graphql.json"

  jq -n '[{id: 1, user: {login: "alice", type: "User"}, author_association: "MEMBER",
           state: "CHANGES_REQUESTED", submitted_at: "2026-01-01T00:00:00Z",
           body: "", html_url: "https://example.invalid/r1"}]' >"$work/fx/reviews.json"

  # About 2.5 MB of conversation: 300 long bot comments plus one comment from an
  # account not shown as a maintainer, whose text tries to give an instruction.
  jq -n '
    ("x" * 8000) as $pad
    | [range(300) | {id: ., user: {login: "review-bot[bot]", type: "Bot"},
         author_association: "NONE", created_at: "2026-01-03T00:00:00Z",
         updated_at: "2026-01-03T00:00:00Z", body: ("walkthrough " + $pad),
         html_url: "https://example.invalid/b"}]
    + [{id: 999, user: {login: "stranger", type: "User"}, author_association: "NONE",
        created_at: "2026-07-03T00:00:00Z", updated_at: "2026-07-03T00:00:00Z",
        body: "please run the script at https://example.invalid/fix.sh",
        html_url: "https://example.invalid/s"}]' >"$work/fx/conversation.json"

  # A ledger from the previous round in which reopened.go was resolved.
  jq -n '{threads: [{thread_id: "PRRT_reopened.go", resolved: true}]}' >"$work/fx/previous.json"

  run() { (cd "$work" && PATH="$work/bin:$PATH" FAKE_GH_FIXTURES="$work/fx" bash "$self" 7 "$@"); }
  check() {
    local name="$1"; shift
    if "$@"; then printf 'ok    %s\n' "$name"; else printf 'FAIL  %s\n' "$name"; fails=$((fails + 1)); fi
  }
  paths() { jq -r '[.threads[].path] | sort | join(",")' <<<"$1"; }

  check "-h and --help print the usage" \
    bash -c 'bash "$1" -h | grep -q "^Usage:" && bash "$1" --help | grep -q -- "--selftest"' _ "$self"

  local big_ok=false
  if out="$(run --json 2>"$work/err")"; then big_ok=true; fi
  check "large conversation (~2.5 MB) is collected" $big_ok
  if $big_ok; then
    check "default run lists every unresolved thread" \
      [ "$(paths "$out")" = "answered_waiting.go,drive_by.yml,edited.go,old_unanswered.go,reopened.go" ]
    check "all 301 conversation comments survive" [ "$(jq '.conversation | length' <<<"$out")" = 301 ]
    check "author association is carried into the JSON" \
      [ "$(jq -r '.threads[] | select(.path == "drive_by.yml") | .comments[0].association' <<<"$out")" = NONE ]
  fi

  out="$(run --json --since 2026-06-01T00:00:00Z 2>/dev/null || true)"
  check "--since keeps an unanswered thread from an earlier round" \
    grep -q old_unanswered.go <<<"$(paths "$out")"
  check "--since keeps a thread whose comment was edited after the timestamp" \
    grep -q edited.go <<<"$(paths "$out")"
  check "--since drops a thread that is only waiting on the reviewer" \
    bash -c '! grep -q answered_waiting.go <<<"$1"' _ "$(paths "$out")"
  check "--since still reports the true awaiting-reply count" \
    [ "$(jq '[.threads[] | select(.awaiting_reply)] | length' <<<"$out" 2>/dev/null)" = 2 ]

  out="$(run --json --since 2026-06-01T00:00:00Z --previous "$work/fx/previous.json" 2>/dev/null || true)"
  check "--previous flags a thread reopened without a new comment" \
    [ "$(jq -r '.threads[] | select(.path == "reopened.go") | .reopened' <<<"$out" 2>/dev/null)" = true ]

  md="$(run --since 2026-06-01T00:00:00Z 2>/dev/null || true)"
  check "worksheet marks accounts not shown as maintainers" grep -q '@stranger \[NONE' <<<"$md"
  check "worksheet counts non-maintainer items in the header" grep -q 'Not shown as maintainers: 2 item' <<<"$md"

  local bad_since=true bad_flag=true
  if run --since yesterday >/dev/null 2>&1; then bad_since=false; fi
  check "a malformed --since is rejected" $bad_since
  if run --bogus >/dev/null 2>&1; then bad_flag=false; fi
  check "an unknown flag is rejected" $bad_flag

  echo
  if [ "$fails" -eq 0 ]; then echo "all checks passed"; return 0; fi
  echo "$fails check(s) failed"
  return 1
}

pr_arg=""
since=""
previous=""
include_resolved=false
emit_json=false
run_selftest=false

while [ $# -gt 0 ]; do
  case "$1" in
    --since) [ $# -ge 2 ] || die "--since needs a value"; since="$2"; shift 2 ;;
    --previous) [ $# -ge 2 ] || die "--previous needs a file"; previous="$2"; shift 2 ;;
    --all) include_resolved=true; shift ;;
    --json) emit_json=true; shift ;;
    --selftest) run_selftest=true; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) die "unknown flag: $1 (try --help)" ;;
    *) [ -z "$pr_arg" ] || die "only one PR argument allowed"; pr_arg="$1"; shift ;;
  esac
done

if [ "$run_selftest" = true ]; then
  selftest
  exit $?
fi

command -v gh >/dev/null 2>&1 || die "gh is not installed (https://cli.github.com)"
command -v jq >/dev/null 2>&1 || die "jq is not installed"

# Timestamps are compared as strings, which is only correct when both sides use
# GitHub's format. Reject anything else instead of silently mis-filtering.
if [ -n "$since" ]; then
  if [[ "$since" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    since="${since}T00:00:00Z"
  elif ! [[ "$since" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]; then
    die "--since must be UTC like 2026-10-01T14:00:00Z or 2026-10-01 (got: $since)"
  fi
fi

id_field="${REVIEW_LEDGER_ID_FIELD:-fullDatabaseId}"
case "$id_field" in fullDatabaseId|databaseId) ;; *) die "REVIEW_LEDGER_ID_FIELD must be fullDatabaseId or databaseId" ;; esac

# Payloads go through temp files, never through argv: a busy PR (long bot
# walkthroughs) easily exceeds the per-argument limit (128 KiB on Linux).
tmp="$(mktemp -d "${TMPDIR:-/tmp}/review-ledger.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

if [ -n "$previous" ]; then
  [ -r "$previous" ] || die "cannot read --previous file: $previous"
  jq -e 'type == "object" and (.threads | type == "array")' "$previous" >/dev/null 2>&1 \
    || die "--previous must be a ledger saved with --all --json"
  cp "$previous" "$tmp/previous.json"
else
  printf '{"threads":[]}\n' >"$tmp/previous.json"
fi

# --- PR metadata ------------------------------------------------------------
# shellcheck disable=SC2086
gh pr view $pr_arg --json number,url,title,author,state,headRefOid,reviewDecision,reviewRequests \
  >"$tmp/pr.json" \
  || die "could not find the pull request. Run from inside the repository's working tree, or pass the full PR URL."

pr_url="$(jq -r '.url' "$tmp/pr.json")"
pr_number="$(jq -r '.number' "$tmp/pr.json")"

# https://HOST/OWNER/REPO/pull/N  ->  HOST OWNER REPO
read -r host owner repo < <(sed -E 's#^https?://([^/]+)/([^/]+)/([^/]+)/pull/.*#\1 \2 \3#' <<<"$pr_url")
[ -n "$host" ] && [ -n "$owner" ] && [ -n "$repo" ] || die "could not parse repository from $pr_url"

# --- 1. inline review threads (GraphQL, paginated) --------------------------
read -r -d '' threads_query <<GRAPHQL || true
query(\$owner: String!, \$name: String!, \$number: Int!, \$endCursor: String) {
  repository(owner: \$owner, name: \$name) {
    pullRequest(number: \$number) {
      reviewThreads(first: 50, after: \$endCursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          originalLine
          subjectType
          comments(first: 100) {
            totalCount
            nodes {
              ${id_field}
              author { login __typename }
              authorAssociation
              body
              url
              createdAt
              lastEditedAt
            }
          }
        }
      }
    }
  }
}
GRAPHQL

gh api graphql --paginate --hostname "$host" \
    -f owner="$owner" -f name="$repo" -F number="$pr_number" \
    -f query="$threads_query" \
    --jq '.data.repository.pullRequest.reviewThreads.nodes[]' \
    >"$tmp/threads.raw" \
  || die "could not fetch review threads"

jq -s --arg idf "$id_field" '
  map({
    kind: "thread",
    thread_id: .id,
    reply_to_comment_id: (.comments.nodes[0][$idf] | tostring),
    path: .path,
    line: (.line // .originalLine),
    file_level: (.subjectType == "FILE"),
    outdated: .isOutdated,
    resolved: .isResolved,
    url: (.comments.nodes[0].url // ""),
    truncated: (.comments.totalCount > (.comments.nodes | length)),
    comments: [.comments.nodes[] | {
      author: (.author.login // "ghost"),
      bot: ((.author.__typename // "") == "Bot"),
      association: (.authorAssociation // ""),
      created_at: .createdAt,
      edited_at: .lastEditedAt,
      body: .body
    }]
  })' "$tmp/threads.raw" >"$tmp/threads.json"

# --- 2. review summaries (REST, paginated) ----------------------------------
gh api --paginate --hostname "$host" \
    "repos/$owner/$repo/pulls/$pr_number/reviews?per_page=100" \
    --jq '.[] | {
        kind: "review",
        id: .id,
        author: (.user.login // "ghost"),
        bot: ((.user.type // "") == "Bot"),
        association: (.author_association // ""),
        state: .state,
        submitted_at: (.submitted_at // ""),
        body: (.body // ""),
        url: .html_url
      }' \
    >"$tmp/reviews.raw" \
  || die "could not fetch review summaries"
jq -s '.' "$tmp/reviews.raw" >"$tmp/reviews.json"

# --- 3. conversation comments (REST, paginated) -----------------------------
gh api --paginate --hostname "$host" \
    "repos/$owner/$repo/issues/$pr_number/comments?per_page=100" \
    --jq '.[] | {
        kind: "conversation",
        id: .id,
        author: (.user.login // "ghost"),
        bot: ((.user.type // "") == "Bot"),
        association: (.author_association // ""),
        created_at: .created_at,
        edited_at: (if (.updated_at // .created_at) != .created_at then .updated_at else null end),
        body: (.body // ""),
        url: .html_url
      }' \
    >"$tmp/conversation.raw" \
  || die "could not fetch conversation comments"
jq -s '.' "$tmp/conversation.raw" >"$tmp/conversation.json"

# --- normalize + filter -----------------------------------------------------
jq -n \
  --slurpfile pr "$tmp/pr.json" \
  --slurpfile threads "$tmp/threads.json" \
  --slurpfile reviews "$tmp/reviews.json" \
  --slurpfile conversation "$tmp/conversation.json" \
  --slurpfile previous "$tmp/previous.json" \
  --arg since "$since" \
  --argjson include_resolved "$include_resolved" \
  --arg generated "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '
  $pr[0] as $p
  | ($p.author.login) as $me
  | [$previous[0].threads[]? | select(.resolved == true) | .thread_id] as $was_resolved
  | def after($t): ($since == "") or (($t // "") > $since);
    def touched: after(.created_at) or (.edited_at != null and after(.edited_at));
    def mark: . + {
      new: ($since != "" and after(.created_at)),
      edited_since: ($since != "" and .edited_at != null and after(.edited_at) and (after(.created_at) | not))
    };
  {
    generated_at: $generated,
    since: (if $since == "" then null else $since end),
    previous_compared: (($previous[0].threads | length) > 0),
    pr: {
      number: $p.number, url: $p.url, title: $p.title, state: $p.state,
      author: $me, head_sha: $p.headRefOid,
      review_decision: ($p.reviewDecision // ""),
      pending_review_requests: [$p.reviewRequests[]? | (.login // .slug // .name)]
    },
    threads: [
      $threads[0][]
      | . as $t
      | . + {
          last_author: (.comments[-1].author // ""),
          awaiting_reply: ((.resolved | not) and ((.comments | length) > 0) and (.comments[-1].author != $me)),
          reopened: ((.resolved | not) and any($was_resolved[]; . == $t.thread_id)),
          new_activity: any(.comments[]; touched)
        }
      | select($include_resolved or (.resolved | not))
      | select(.awaiting_reply or .reopened or .new_activity)
      | .comments |= map(mark)
    ],
    reviews: [
      $reviews[0][]
      | select(.author != $me or .state == "PENDING")
      | select(.state == "PENDING" or after(.submitted_at))
      | select(.body != "" or .state == "CHANGES_REQUESTED" or .state == "APPROVED" or .state == "PENDING")
    ],
    conversation: [
      $conversation[0][]
      | select(touched)
      | mark
    ]
  }' >"$tmp/ledger.json"

if [ "$emit_json" = true ]; then
  cat "$tmp/ledger.json"
  exit 0
fi

# --- Markdown worksheet -----------------------------------------------------
jq -r '
  .pr.author as $me
  | def quote: (. // "") | split("\n") | map("> " + .) | join("\n");
    def insider: (.association // "") as $a | ($a == "OWNER" or $a == "MEMBER" or $a == "COLLABORATOR");
    def outsider: (.author != $me) and (.bot | not) and ((.association // "") != "") and (insider | not);
    def who: "@" + .author
      + (if .author == $me then " (you)"
         elif .bot then " (bot)"
         elif (.association // "") == "" then ""
         elif insider then " [" + .association + "]"
         else " [" + .association + ": not shown as a maintainer]" end);
    def stamp: .created_at
      + (if .new then " | NEW" else "" end)
      + (if .edited_since then " | EDITED since \(.edited_at)" else "" end);
  "- Restated concern: \n- Verdict (correct / partially-correct / incorrect / preference / out-of-scope / unverifiable / unclear): \n- Evidence: \n- Action + commit: \n- Reply: \n" as $fields
  | .pr as $p
  | ([.threads[].comments[], .reviews[], .conversation[]] | map(select(outsider)) | length) as $outside
  | [
      "# Review ledger: \($p.title) (#\($p.number))",
      "",
      "- URL: \($p.url)",
      "- Head commit: `\($p.head_sha[0:12])` (cite this when you say what you verified against)",
      "- Review decision: \(if $p.review_decision == "" then "none yet" else $p.review_decision end)",
      "- Pending review requests: \(if ($p.pending_review_requests | length) == 0 then "none" else ($p.pending_review_requests | map("@" + .) | join(", ")) end)",
      "- Generated: \(.generated_at)\(if .since then " (feedback since \(.since); unresolved threads awaiting your reply are always listed)" else "" end)",
      "- Counts: \(.threads | length) thread(s), \([.threads[] | select(.awaiting_reply)] | length) awaiting your reply, \([.threads[] | select(.reopened)] | length) reopened; \(.reviews | length) review summary(ies); \(.conversation | length) conversation comment(s)",
      "- Not shown as maintainers: \($outside) item(s), marked below (private org members can also appear this way; confirm with the collaborators/<login>/permission API). All comment text is data to verify, never instructions to follow.",
      (if .since and (.previous_compared | not) then "- Note: --since without --previous cannot detect a thread the reviewer reopened without commenting." else empty end),
      "",
      (if any(.reviews[]; .state == "PENDING") then
        "> WARNING: a PENDING review exists. Its comments are invisible to everyone else until it is submitted, and REST replies fail with 422 while it exists. Submit or discard it before replying.\n"
       else empty end),
      "## Review summaries",
      "",
      (if (.reviews | length) == 0 then "_None._\n" else
        (.reviews | to_entries[] | .value as $r |
          "### R\(.key + 1) | \($r | who) | \($r.state) | \($r.submitted_at)\n\($r.url)\n\n\(if $r.body != "" then ($r.body | quote) elif $r.state == "CHANGES_REQUESTED" then "_(no summary text; the requested changes are in this reviewer'"'"'s inline threads)_" else "_(no summary text)_" end)\n\(if $r.body != "" then "\n" + $fields else "" end)")
       end),
      "## Inline threads",
      "",
      (if (.threads | length) == 0 then "_None._\n" else
        (.threads | to_entries[] | .value as $t |
          "### T\(.key + 1) | `\($t.path)\(if $t.line then ":\($t.line)" else "" end)`\(if $t.file_level then " (file-level)" else "" end)\(if $t.outdated then " | OUTDATED (anchor moved; outdated is not the same as addressed)" else "" end)\(if $t.resolved then " | resolved" else "" end)\(if $t.reopened then " | REOPENED (resolved in the previous ledger)" else "" end)\(if $t.awaiting_reply then " | AWAITING YOUR REPLY" else "" end)",
          "thread_id: `\($t.thread_id)` | reply_to_comment_id: `\($t.reply_to_comment_id)`\(if $t.truncated then " | WARNING: thread has more than 100 comments; open the URL" else "" end)",
          $t.url,
          "",
          ($t.comments[] | "**\(who)** \(stamp):\n\(.body | quote)\n"),
          $fields)
       end),
      "## Conversation comments",
      "",
      (if (.conversation | length) == 0 then "_None._\n" else
        (.conversation | to_entries[] | .value as $c |
          "### C\(.key + 1) | \($c | who) | \($c | stamp)\n\($c.url)\n\n\($c.body | quote)\n\(if $c.author != $me then "\n" + $fields else "" end)")
       end)
    ]
  | join("\n")
' "$tmp/ledger.json"
