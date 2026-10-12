---
name: commit-message
description: "Writes commit messages in the repo's convention (Conventional Commits by default) and splits a working tree into atomic commits without interactive staging, keeping secrets and junk out. Use for \"commit this\", \"write a commit message\", \"split this into separate commits\", \"reword the last commit\", \"resolve these merge conflicts\". Not for PR text or changelogs (pr-description), the pre-commit check (verify-before-done), or diagnosing CI failures (ci-failure-triage)."
# Read-only commands only. git fetch updates remote-tracking refs and nothing
# else. Staging, committing, and history rewrites still ask for permission.
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git show:*), Bash(git ls-files:*), Bash(git config --get:*), Bash(git check-ignore:*), Bash(git rev-parse:*), Bash(git merge-base:*), Bash(git branch -r --contains:*), Bash(git fetch:*)
---

# Commit Message

People bisect, revert, cherry-pick, and `git blame` through commits for years. This skill
produces commits that each hold one logical change, and gives each one a message that states
what changed and why. It handles four jobs: writing a message only, committing finished work,
splitting a mixed working tree into several commits, and rewording or amending unpushed commits.

## Ground rules

- **Do what was asked and stop.** A request for a message gets a message, with no git writes.
  Commit only when the user, or the project's instructions, ask for a commit. A request to
  commit does not mean push.
- **The repo's convention wins.** Conventional Commits is the default when history shows no
  clear style. It isn't a mandate to restyle a repo that already does something else.
- **Leave shared history alone.** Don't amend, rebase, or force-push commits that someone else
  may have pulled unless the user has agreed to it. See "Amend or new commit".
- **Let hooks and signing run.** A failing hook is telling you something. Use `--no-verify`
  only when the user asks for it by name. If signing blocks on a passphrase or security-key
  prompt, stop and tell the user rather than passing `--no-gpg-sign`.
- **Humans certify; you don't.** Never add a `Signed-off-by` trailer on your own initiative,
  invent a co-author, or set a git identity on the user's behalf.

## Workflow

### 1. Identify the deliverable

| Request | Deliverable |
|---|---|
| "write / suggest a commit message" | The message in a code block. No staging, no commit. |
| "commit this", or the project's instructions say to commit finished work | Changes staged and committed, then verified and reported |
| A task is finished but nobody asked for a commit | The proposed message or commit plan, and a question. No git writes. |
| "split this up", "atomic commits" | A commit plan, then the commits |
| "reword / fix the last commit message" | An amend if it's safe (see below), otherwise an explanation of why not |
| "is this message OK?" | A critique against the rules below, plus a rewrite |

### 2. Inspect the state

```bash
git status --short --branch     # staged / unstaged / untracked, branch, ahead/behind
git diff --cached --stat        # already staged
git diff --stat                 # modified, not staged
git log -n 20 --format='%h %s'  # recent subjects: the house style
```

Read the diffs themselves (`git diff --cached`, `git diff`) before you write anything, and read
untracked files directly, since `git diff` doesn't show them. Write the message from the
change, not from your memory of the session, which misses the stray edit that slipped in.

Settle these before any git write:

- **An operation is in progress** (merge, rebase, cherry-pick, revert). Finish it or ask
  before creating unrelated commits.
- **The user already staged something.** Treat the index as their selection. Commit what is
  staged, and say so before adding anything to it.
- **HEAD is detached** (`## HEAD (no branch)`) outside a rebase you started. Commits there
  are easy to lose, so ask or propose a branch first.
- **You're on the default or a protected branch** while history shows work lands through
  feature branches. Propose a branch and ask.
- **No identity is set.** If `git config --get user.name` or `user.email` is empty and no
  `GIT_AUTHOR_*` variables are set, stop and ask. Don't let git guess one from the hostname.

### 3. Learn the house style

Read the recent subjects plus a few full messages (`git log -n 10 --format='%B%n-----'`) and
note:

- **Subject shape.** Conventional Commits (`fix(api): ...`), a subsystem prefix (`net: ...`),
  a ticket key (`PROJ-123: ...`), or plain capitalized sentences.
- **Case and length.** The case after the prefix, the typical subject length, and whether
  bodies are normally written.
- **Trailers.** `Change-Id` means Gerrit, and the trailer must survive amends. Also look for
  `Co-authored-by`, `Assisted-by`, and issue references.
- **DCO sign-off.** `Signed-off-by` on most commits means the project requires a Developer
  Certificate of Origin sign-off, which only the human contributor can certify. Don't pass
  `-s` yourself. Tell the user the commit needs their sign-off after review, for example
  `git commit --amend --no-edit -s` while it's unpushed, unless they explicitly say they
  certify this change.
- **AI attribution.** Follow the project's AI-contribution policy (CONTRIBUTING, a policy
  file, or the trailers history uses) and your host tool's attribution instructions. If the
  project doesn't accept AI-generated contributions, stop and tell the user.
- **Merge style.** If subjects on the default branch end in `(#123)`, PRs are squash-merged.
  The PR title then becomes the permanent commit, so it matters more than branch commits
  (see `workflow:pr-description`).

Then look for enforced rules. A linter or commit-msg hook beats every default in this skill:

```bash
git ls-files | grep -iE '(commitlint|\.czrc|\.cz\.(toml|json|ya?ml)|gitlint|\.gitmessage|\.husky/|lefthook|\.pre-commit-config|\.releaserc|release\.config|release-please|cliff\.toml|CONTRIBUTING)'
grep -nE '"(commitlint|commitizen)"' package.json 2>/dev/null   # config kept inside package.json
git config --get commit.template
git config --get core.hooksPath                                 # hooks kept outside .git/hooks
ls "$(git rev-parse --git-path hooks)" 2>/dev/null | grep -v '\.sample$'   # installed hooks, e.g. Gerrit's commit-msg
```

`references/message-format.md`, section "Detecting enforced conventions", explains what each
of those files implies.

### 4. Screen the candidates

Sort every changed and untracked file into "goes in" and "stays out" before planning:

- **Secret files** stay out: `.env*`, `*.pem`, `*.key`, `id_rsa*`, `*.p12`, credential JSON,
  and configs or fixtures holding real tokens. The usual substitute is a committed template
  (such as `.env.example`) with placeholder values.
- **Generated or local junk** stays out: build output, dependency directories, coverage,
  logs, OS and editor files, large binaries. Output the project produces gets a `.gitignore`
  rule, but a rule doesn't untrack a file that's already tracked; that also needs
  `git rm --cached -- path`, which keeps the local copy. Personal OS and editor patterns go in
  `.git/info/exclude` or a global `core.excludesFile`, not the project's `.gitignore`.
  `git check-ignore -v path` shows which rule matches.
- **Lockfiles** are generated but usually tracked on purpose. Commit one together with the
  manifest change that produced it.

If a secret is already in a commit that no remote has (check as in "Amend or new commit"),
remove it and rewrite the local commit. If it's pushed, deleting it in a new commit leaves it
in history: tell the user the credential must be rotated. `review-suite:secure-code-review`
(if installed) can assess the exposure.

### 5. Plan atomic commits

An atomic commit holds one logical change and builds and passes tests on its own. That is
what makes history useful: `git bisect` needs every commit to build, reverting a mixed commit
undoes unrelated work too, and a reviewer can confirm a pure refactor quickly only when no
behavior change is mixed in.

**Split along these seams:**

- A refactor, rename, or move goes in a separate commit from a behavior change. Put the
  preparatory refactor first and the change it enables second (see
  `implementation:refactor-safely`, if installed).
- Formatting or whitespace goes in a separate commit from logic, and the body names the tool
  and command used. When the formatter touched the same lines as the logic, regenerate the
  formatting commit rather than picking hunks (see the splitting reference).
- Unrelated fixes noticed along the way get their own commits, or stay out entirely.
- A dependency upgrade goes in a separate commit from the code that uses it, unless that code
  can't build without it.
- Moving a file goes in a separate commit from substantial edits to it, so git still detects
  the rename.

**Keep together:**

- Code and its tests. A test that fails without a fix belongs in the same commit as the fix.
- A manifest and its lockfile. If the repo tracks generated output, the source and the
  regenerated output.
- Anything that can't compile apart. Atomic means indivisible, not tiny.

When there will be more than one commit, write the plan before staging anything:

```text
1. refactor(billing): extract proration into its own function
     src/billing/invoice.ts (hunks 1-2)
2. fix(billing): prorate from the plan change date, not cycle start
     src/billing/invoice.ts (hunk 3), test/billing/invoice.test.ts
3. chore: ignore local coverage output
     .gitignore
Excluded: .env.local (credentials)
```

### 6. Stage precisely

When a file belongs entirely to one commit, stage it by path. Name the paths explicitly. Using
`git add -A`, `git add .`, or `git commit -a` sweeps in whatever else is lying around.

```bash
git add -- src/billing/invoice.ts test/billing/invoice.test.ts
git restore --staged -- path/to/file    # unstage
```

When one file holds changes that belong in different commits, you need hunk-level staging.
`git add -p` is interactive and usually can't be driven from an agent's shell. Stage from a
patch file instead. The extra `git diff` flags keep the patch valid whatever the user's color,
path-prefix, or external-diff settings are:

```bash
f=src/billing/invoice.ts
tmp=$(mktemp -d)
git diff --no-color --no-ext-diff --src-prefix=a/ --dst-prefix=b/ -- "$f" > "$tmp/full.patch"
# copy the file header plus the wanted hunks into "$tmp/part.patch", then:
git apply --cached --check --recount "$tmp/part.patch" && git apply --cached --recount "$tmp/part.patch"
```

`references/splitting-and-staging.md` has the tested recipes: picking hunks by number, changes
that share a hunk or a line, regenerating mechanical changes, new and binary files, and
splitting a commit that already exists.

Confirm the result every time: `git diff --cached` shows exactly the planned commit, and
`git diff` shows the rest. In a multi-commit plan, check that each staged state builds on its
own; the splitting reference shows how, before each commit or by replaying the series after.

### 7. Write the message

```text
type(scope)!: imperative summary of the change

Why the change was needed: the problem, its symptom or cost, and any
constraint that shaped the fix. Then what changed, at the level a
reviewer thinks in, plus anything the diff can't tell a future reader:
trade-offs, rejected alternatives, follow-ups, migration steps.

BREAKING CHANGE: what breaks and what callers must do instead.
Refs: #123
```

**Subject line**

- **Shape.** `type(scope): summary`. The scope is optional. A `!` before the colon marks a
  breaking change.
- **Imperative mood.** Use "add", "fix", "drop", not "added", "adds", or "adding". The subject
  should complete the sentence "If applied, this commit will ...".
- **Length.** Aim for about 50 characters, and treat 72 as the hard limit: GitHub truncates
  longer subjects, and squash merges append " (#1234)". A limit configured in the repo wins.
- **Punctuation and case.** No trailing period. Lowercase after the colon is the usual
  Conventional Commits style (the widely used `@commitlint/config-conventional` rejects
  sentence-case and other capitalized subjects), but match the history.
- **Specificity.** Name the behavior, not the activity. "fix(auth): reject expired refresh
  tokens" says something. "fix: auth bug" and "update auth.ts" don't. Placeholders such as
  "WIP", "fix stuff", or "address review comments" never belong in a final message.

**Type.** Pick the type by the commit's effect on users, not by which files it touched. A bug
fix that only changes a config file is still `fix`.

| Type | Use for |
|---|---|
| `feat` | A new capability for users of the code (end users, API callers, CLI users) |
| `fix` | Behavior was wrong and is now right |
| `perf` | Faster or cheaper, with identical observable behavior |
| `refactor` | Restructured code with no behavior change |
| `test` | Tests only: added, fixed, or reorganized |
| `docs` | Documentation or comments only |
| `style` | Formatting or whitespace only. This means code style, not CSS: a visual change is `feat` or `fix` |
| `build` | Build system, packaging, dependencies |
| `ci` | CI pipeline configuration and scripts |
| `chore` | Maintenance that fits nowhere else, such as repo housekeeping or tool config |
| `revert` | Undoing an earlier commit |

Release tools map `feat` to a minor release, `fix` to a patch, and a breaking change to a
major; semantic-release's defaults also release `perf` and reverts as patches, and other types
depend on configuration. A wrong type ships a wrong version number.
`references/message-format.md` covers ambiguous cases, scopes, breaking changes, reverts, and
security fixes.

**Body**

- **Layout.** One blank line after the subject, because git treats everything up to the first
  blank line as the title. Wrap at about 72 columns; `git log` indents the body and patch
  tools don't reflow it.
- **Lead with why.** The diff already shows what changed; the message is the only place the
  reason survives. Summarize the what at reviewer level ("move retry into the HTTP client so
  every caller gets backoff"), never line by line ("change line 40 of client.go").
- **Make it self-contained.** An issue link supports the reason but can't replace it, because
  links rot. Don't write "as discussed" or "per review" without saying what was decided.
- **Skip it when there's nothing to add,** as with a typo fix or a routine version bump.

**Footers** go in the final paragraph, after a blank line, one `Token: value` per line. Keep
prose out of that paragraph, or tools may stop recognizing the trailers.

| Footer | Purpose |
|---|---|
| `BREAKING CHANGE: ...` | Explains a break and its migration path. Must be uppercase. Always write it, even with `!`: it's the marker every parser reads, while semantic-release's default (angular) preset ignores `!` headers entirely. |
| `Refs: #123` | Links related work without closing anything |
| `Closes #123` / `Fixes #123` | On GitHub and GitLab, closes the issue when the commit reaches the default branch. Use only for a complete fix, or the issue closes early. |
| `Co-authored-by: Name <email>` | Credits a co-author, one line per person. Never invent one. |
| `Signed-off-by: ...` | DCO certification, made by the human contributor. See step 3. |

The full list, including review trailers, `Assisted-by`, and `Change-Id`, is in
`references/message-format.md`.

### 8. Scan, then commit

Right before every `git commit` (each commit in a plan, and each retry after a hook failure),
check exactly what is staged. Staged new files appear here, unlike untracked ones:

```bash
git diff --cached --name-status     # the file list matches the plan
git diff --cached --check           # conflict markers and whitespace errors
git diff --cached -U0 --no-color | grep -n '^+' | grep -iE 'PRIVATE KEY-----|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_|xox[a-z]-|bearer [A-Za-z0-9._~+/-]+|://[^/ :@]+:[^/ @]+@|(api[_-]?key|secret|passw(or)?d|token)[a-z_]*"? *[:=]'
```

A hit is a lead, not proof, and a clean result proves nothing. If the repo already uses a
secret scanner (gitleaks, trufflehog, detect-secrets, often in the pre-commit config), run it
in its staged mode too. Also look for debug prints, commented-out blocks, and focused or
skipped tests. The full build, test, and behavior check belongs to
`implementation:verify-before-done` (if installed), before you reach this point.

Pass a multi-line message on stdin through a quoted heredoc. Quoting the delimiter (`'EOF'`)
stops the shell from expanding `$VARS` and backticks in the text:

```bash
git commit -F - <<'EOF'
fix(billing): prorate from the plan change date, not cycle start

Customers who upgraded mid-cycle were charged the new rate for the
whole cycle because proration started at the cycle boundary. Start
proration at the change timestamp, and round to whole cents only once,
at the invoice total, so line items still sum to the charged amount.

Closes #482
EOF
```

- **Don't put `\n` in `-m`;** the shell passes it through literally. Each separate `-m` becomes
  its own paragraph, which suits a subject plus one short body paragraph.
- **On Windows PowerShell,** write the message to a BOM-less UTF-8 file and use `-F path`.
  Windows PowerShell 5.1's defaults produce files git rejects or mangles; see
  `references/message-format.md`, "Git message-handling gotchas", for a working command.
- **Trailers can come from flags.** `--trailer "Token: value"` appends one without editing
  the text.

**When a hook fails, no commit was made.** Fix the cause and run the same `git commit` again.
Don't retry with `--amend`, which would rewrite the previous, unrelated commit. Some
formatting hooks re-stage their fixes and many leave them unstaged, so check `git status`. If
the hook changed a file you staged only partly, don't `git add` the whole file, which would
sweep in hunks meant for later commits. Re-stage just the hook's changes with the patch method
from step 6, and confirm `git diff --cached` still matches the plan.

### 9. Verify

```bash
git log -1 --format=%B   # the message exactly as stored
git show --stat HEAD     # the files that went in
git status --short       # what is left
```

If a commit-message linter is already installed in the project, run it on the new commits.
`references/message-format.md` shows how.

## Amend or new commit

`git commit --amend` replaces the last commit. Add `--no-edit` to keep the message, or
`--only -F -` to change only the message without picking up whatever is staged. Amend only when
one of these is true:

- **No remote has the commit.** Refresh the remote-tracking refs, then list commits that no
  remote branch contains:

  ```bash
  git fetch --quiet --all
  git log --oneline HEAD --not --remotes   # commits on no remote; HEAD must be listed to amend it
  git branch -r --contains HEAD            # remote branches that already hold HEAD
  ```

  To rewrite older commits, every commit from the target to `HEAD` must be listed. Don't rely
  on `git log @{upstream}..HEAD`: it checks one tracked branch, and "no upstream configured"
  means unknown, not unpushed (a branch pushed without `-u` has no upstream). If the fetch
  fails, treat the commit as pushed unless the user says otherwise.
- **The branch is yours alone.** Only you use it, the team accepts force-pushes to it, and the
  user agrees. Push with `git push --force-with-lease --force-if-includes` (Git 2.30+). A bare
  `--force-with-lease` trusts your remote-tracking ref, which a background fetch (an IDE, for
  example) can move without you ever seeing the new commits. On older Git, pin the lease:
  `--force-with-lease=<branch>:<sha you last saw>`.

In every other case, add a new commit. Rewriting a shared branch (the default branch, a release
branch, a branch a colleague has pulled) makes every other clone diverge, and their next push
can silently drop work.

To correct an earlier commit during review, record the change with `git commit --fixup=<sha>`
and fold it in with `git rebase --autosquash` before merge (details in the splitting
reference). Some teams want review fixes kept as separate commits, so check the house style.

## Report format

**Message only.** Return the message in a fenced `text` block. Follow it with at most one line
of assumptions, such as the type you chose, the scope, or an issue number you couldn't confirm.

**After committing:**

```text
Committed 2 commits on feature/proration-fix (not pushed):
  3f2a91c refactor(billing): extract proration into its own function
  8be04d7 fix(billing): prorate from the plan change date, not cycle start
Left uncommitted: scratch/notes.md (unrelated, untracked)
Checks: pre-commit hook passed; unit tests passed at each commit
Notes: excluded .env.local (contains credentials); issue #482 will close on merge
```

**Message review.** List each problem with the rule it breaks, then give the rewritten message.

## Related skills

- `workflow:pr-description` covers PR titles and bodies, release notes, and changelog entries.
- `implementation:refactor-safely` structures refactor-first changes.
- `implementation:verify-before-done` runs the full checks before work is called done.
- `workflow:ci-failure-triage` when a commit-message lint or other check fails in CI.

Skills are named here as `plugin:skill`; an agent that lists skills by bare name knows each one by the part after the colon (`review-suite:pr-review` is `pr-review`). If a skill named here isn't installed, give the short version inline and list the deeper pass as a follow-up.

## Reference files

- `references/message-format.md`: ambiguous types, breaking changes, reverts, security fixes,
  scopes, trailers, decoding a repo's commit tooling, and message-handling gotchas.
- `references/splitting-and-staging.md`: one file holding changes for several commits,
  formatting that overlaps logic, splitting, rewording, or fixing up existing commits, and
  resolving conflicts when a merge, rebase, or pull stops (section 13), including lockfiles.
- `references/examples.md`: calibrated good-versus-bad messages across stacks, for writing,
  critiquing, or rewriting a message.
