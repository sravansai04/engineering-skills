# Posting a review to the PR

Read this file only when the user has asked you to post the review. Until
then, the review lives in the conversation.

## Contents

1. Before posting
2. GitHub: one batched review with inline comments (preferred)
3. GitHub: pending (draft) reviews
4. GitHub: line and side rules
5. GitHub: suggestion blocks
6. GitHub: single comments, file-level comments, replies
7. GitHub: summary-only review
8. Common API errors
9. GitLab equivalents (reading, live comments, drafts)

---

## 1. Before posting

- **Confirm the action.** Confirm with the user whether this is a comment, an
  approval, a change request, or a pending draft. A review posted from their
  account speaks for them. Without an explicit instruction, use `COMMENT` or
  pending, never `APPROVE` or `REQUEST_CHANGES`.
- **Get the head commit** the comments anchor to:
  `HEAD_SHA=$(gh pr view 123 --json headRefOid -q .headRefOid)`. If the author
  pushed after you fetched, re-fetch and re-check your line numbers first.
- **Don't duplicate what is already there:**
  `gh api "repos/{owner}/{repo}/pulls/123/comments" --paginate --jq '.[] | {path, line, body}'`
- **Placeholders.** `gh api` fills `{owner}` and `{repo}` from the repository in
  the current directory, or from the `GH_REPO` environment variable. Outside a
  checkout, write `repos/OWNER/REPO/...` explicitly. Quote the endpoint in
  shells that treat braces specially.

## 2. GitHub: one batched review with inline comments (preferred)

A single review sends the author one notification and groups the comments
together. Posting comments one at a time sends one notification per comment.

Create the request body as a JSON file. Build it with `jq` or a short script
rather than gluing strings together, so quotes, backticks, and newlines in
comment bodies are escaped correctly.

This body posts the worked review in `example-review.md` (PR 482). Findings
#1, #3, #4, and #5 sit on lines inside the diff's hunks, so they go inline.
Finding #2 is about `jobs/nightly_export.py:22`, which the PR doesn't touch, so
it goes in the review `body` (section 4):

```json
{
  "commit_id": "3f9c2e1d0b7a6c5e4f3a2b1c0d9e8f7a6b5c4d3e",
  "event": "COMMENT",
  "body": "Fix before merge: two high (#1, #2), two medium (#3, #4), one low (#5). #2 is below because its line is outside the diff; the rest are inline.\n\n**high (#2):** `jobs/nightly_export.py:22` still calls `export_orders(db, customer_id)` with no paging, so the nightly file now holds at most one page ...",
  "comments": [
    {
      "path": "src/orders/export.py",
      "line": 11,
      "side": "RIGHT",
      "body": "**high (#1):** `page` starts at 1 ..."
    },
    {
      "path": "src/orders/export.py",
      "line": 14,
      "side": "RIGHT",
      "body": "**medium (#3):** ordering by `created_at` alone ..."
    },
    {
      "path": "tests/orders/test_export.py",
      "line": 7,
      "side": "RIGHT",
      "body": "**medium (#4):** `assert len(rows) <= 2` also passes when nothing comes back ..."
    },
    {
      "path": "src/api/orders.py",
      "start_line": 42,
      "start_side": "RIGHT",
      "line": 43,
      "side": "RIGHT",
      "body": "**low (#5):** `?page=abc` raises `ValueError` ..."
    }
  ]
}
```

The event is `COMMENT` even though the verdict is "Fix before merge". Use
`REQUEST_CHANGES` only when the user explicitly asks for it.

```bash
gh api --method POST "repos/{owner}/{repo}/pulls/123/reviews" --input review.json
```

The top-level fields are:

- `commit_id`: the head SHA. It defaults to the latest commit if you omit it.
- `event`: one of `APPROVE`, `REQUEST_CHANGES`, or `COMMENT`. If you omit it,
  the review is created as PENDING.
- `body`: the review summary. It is required when `event` is `REQUEST_CHANGES`
  or `COMMENT`.
- `comments[]`: the inline comments. Each one takes `path`, `body`, `line`,
  `side`, and, for a range, `start_line` and `start_side`.

A safe way to build the file with jq 1.6 or later, for a review that is
published at once:

```bash
jq -n --arg sha "$HEAD_SHA" --rawfile summary summary.md \
  --slurpfile comments comments.json \
  '{commit_id: $sha, event: "COMMENT", body: $summary, comments: $comments[0]}' > review.json
```

Here `comments.json` holds the array of comment objects. Don't reuse this
builder for a draft: its hard-coded `event` publishes the review. Section 3
has the draft version.

## 3. GitHub: pending (draft) reviews

Leave out `event` and GitHub creates a pending review. It is visible only to
the account that created it, and the user can edit it in the PR's Files tab
before submitting. This is the right default when the user wants to look over
your comments first.

Build the body with no `event` key, and check it before posting. If the check
prints `true`, the POST would publish the review and notify everyone watching
the PR:

```bash
jq -n --arg sha "$HEAD_SHA" --rawfile summary summary.md \
  --slurpfile comments comments.json \
  '{commit_id: $sha, body: $summary, comments: $comments[0]}' > review.json
jq 'has("event")' review.json    # must print false for a draft

REVIEW_ID=$(gh api --method POST "repos/{owner}/{repo}/pulls/123/reviews" --input review.json --jq .id)

# Submit it later (body optional here; event required):
gh api --method POST "repos/{owner}/{repo}/pulls/123/reviews/$REVIEW_ID/events" -f event=COMMENT

# Or throw it away:
gh api --method DELETE "repos/{owner}/{repo}/pulls/123/reviews/$REVIEW_ID"
```

GitHub allows one pending review per user per PR. To find an existing one:
`gh api "repos/{owner}/{repo}/pulls/123/reviews" --paginate --jq '.[] | select(.state=="PENDING") | .id'`

## 4. GitHub: line and side rules

- `side: "RIGHT"` means the head version of the file: added lines and the
  unchanged context lines shown in the diff. `line` is the line number in the
  head file. This is the same number you used for `file:line` in the report.
- `side: "LEFT"` means the base version, for commenting on a deleted line.
  `line` is then the line number in the base file.
- The line has to fall inside a hunk of this PR's diff. A hunk header
  `@@ -a,b +c,d @@` makes head lines `c` through `c+d-1` commentable on the
  RIGHT side. A finding about a line outside every hunk (an unchanged caller,
  say) belongs in the review `body`, quoted as `path:line`.
- For a multi-line comment, set `start_line` and `start_side` for the first
  line and `line` and `side` for the last. Keep the range inside one hunk.
- `position`, a line offset from the hunk header, is the older way to anchor a
  comment. GitHub's docs say it is closing down, so use `line` and `side`.

## 5. GitHub: suggestion blocks

A fenced block tagged `suggestion` inside a comment body renders a one-click
"Commit suggestion" button. Its content replaces exactly the anchored line (or
the `start_line` to `line` range), so write the complete replacement lines with
their original indentation.

For finding #1, anchored at `src/orders/export.py:11` (the `offset` line):

````markdown
**high (#1):** pages are 1-based (the handler defaults `page` to 1), so this skips the first page.

```suggestion
    offset = (page - 1) * page_size
```
````

Use suggestions for small, self-contained fixes. For anything larger, describe
the change instead. A suggestion the author can't apply cleanly is worse than
prose.

## 6. GitHub: single comments, file-level comments, replies

Each of these is a separate notification, so batch them (section 2) when
there is more than one.

```bash
# One inline comment. -F sends line as a number; -f sends strings.
gh api --method POST "repos/{owner}/{repo}/pulls/123/comments" \
  -f body='**medium (#3):** ...' -f commit_id="$HEAD_SHA" \
  -f path=src/orders/export.py -F line=14 -f side=RIGHT

# A comment on a whole file (no line):
gh api --method POST "repos/{owner}/{repo}/pulls/123/comments" \
  -f body='**low:** ...' -f commit_id="$HEAD_SHA" \
  -f path=src/orders/export.py -f subject_type=file

# A reply in an existing thread (COMMENT_ID from the comments listing):
gh api --method POST "repos/{owner}/{repo}/pulls/123/comments/COMMENT_ID/replies" \
  -f body='Thanks, that resolves it.'
```

## 7. GitHub: summary-only review

When there is nothing to anchor inline, or the user wants only the summary
posted:

```bash
gh pr review 123 --comment --body-file review.md
gh pr review 123 --request-changes --body-file review.md   # only when explicitly asked
gh pr review 123 --approve --body "..."                    # only when explicitly asked
```

## 8. Common API errors

| Symptom | Cause | Fix |
|---|---|---|
| 422, with a message that the review thread line must be part of the diff, or that the line could not be resolved | `line` is outside every hunk, or on the wrong `side` | Re-read the hunk headers, switch sides for deleted lines, or move the finding into the review body |
| 422, with a message that you can't approve or request changes on your own pull request | The authenticated user is the PR author | Use `COMMENT` |
| 422, with a message that a user can only have one pending review | A pending review already exists | Submit or delete it first (section 3) |
| 422, with a message that the body is missing | `event` is `COMMENT` or `REQUEST_CHANGES` with no `body` | Add a summary body |
| 404 on a repository you can see in the browser | The `gh` token lacks access to it | Run `gh auth status` and re-authenticate with the right scopes |
| Comments shown as "outdated" | `commit_id` is older than the current head | Re-fetch the head SHA and re-check the line numbers |

## 9. GitLab equivalents (reading, live comments, drafts)

**Reading the change.** `glab mr view 123` and `glab mr diff 123`. Don't use
`glab mr checkout`, which switches the user's branch. GitLab exposes every
MR's head as a ref, so fetch it and use the same merge-base and
`git worktree add --detach` flow as SKILL.md step 3:

```bash
git fetch origin "refs/merge-requests/123/head"
HEAD_SHA=$(git rev-parse FETCH_HEAD)
```

`glab` subcommand names have changed between releases, so check
`glab mr note --help` before relying on any of the `glab mr note` commands
below. The `glab api` calls fill `:id` from the current repository and don't
depend on the glab version.

### Draft (pending) comments

GitLab's version of a pending review is a set of draft notes: only you see
them until they are published. Use drafts by default whenever the user wants
to look before anything is posted, because a live note is published under
their name at once.

Recent glab versions:

```bash
glab mr note draft create 123 --file src/orders/export.py --line 11 -m "**high (#1):** ..."
glab mr note draft publish 123    # or the user submits the review from the MR page
```

Through the Draft Notes API (the text field is `note`, not `body`):

```bash
glab api --method POST "projects/:id/merge_requests/123/draft_notes" \
  -H "Content-Type: application/json" --input draft.json
glab api --method POST "projects/:id/merge_requests/123/draft_notes/bulk_publish"   # publishes all of yours
```

```json
{
  "note": "**high (#1):** ...",
  "position": { "position_type": "text", "base_sha": "...", "start_sha": "...", "head_sha": "...",
                "old_path": "src/orders/export.py", "new_path": "src/orders/export.py", "new_line": 11 }
}
```

The `position` object is the same one the Discussions API takes, below.

### Live comments

These are published immediately. Recent versions of `glab mr note create` can
anchor to a line:

```bash
glab mr note create 123 -m "**high (#1):** ..." --file src/orders/export.py --line 11
```

Older versions only post general MR comments (`glab mr note 123 -m "..."`).
If yours can't anchor to a line, use the Discussions API:

```bash
# 1. Diff SHAs for the position: base_commit_sha, start_commit_sha, head_commit_sha of the latest version
glab api "projects/:id/merge_requests/123/versions" | jq '.[0] | {base_commit_sha, start_commit_sha, head_commit_sha}'

# 2. Create a diff thread
glab api --method POST "projects/:id/merge_requests/123/discussions" \
  -H "Content-Type: application/json" --input discussion.json
```

```json
{
  "body": "**high (#1):** ...",
  "position": {
    "position_type": "text",
    "base_sha": "BASE_COMMIT_SHA",
    "start_sha": "START_COMMIT_SHA",
    "head_sha": "HEAD_COMMIT_SHA",
    "old_path": "src/orders/export.py",
    "new_path": "src/orders/export.py",
    "new_line": 11
  }
}
```

The line fields depend on the kind of line:

- An added line uses only `new_line`.
- A removed line uses only `old_line`.
- An unchanged context line uses both, and the two values can differ.
