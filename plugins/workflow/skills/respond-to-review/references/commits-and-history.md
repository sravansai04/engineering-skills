# Commits and history during review

How to shape and push review fixes so the reviewer's next pass is fast and nothing they did is lost. Read this during the skill's "Implement in reviewable commits" step, and before any rebase, amend, or force-push on a branch that has an open review.

## Contents

1. Why history stays append-only while a review is open
2. Commit shape for review fixes
3. Keeping history clean without rewriting mid-review
4. Bringing in changes from the base branch
5. When the push is rejected
6. If you must force-push
7. Approvals that reset on push
8. Pre-push checklist
9. Amend-based and stacked workflows

---

## 1. Why history stays append-only while a review is open

A reviewer's second pass is mostly "what changed since I last looked". Review tools compute that from the commits they already saw. Rewriting those commits (rebase, amend, squash, then force-push) causes three problems:

- **The incremental view degrades.** The reviewer can no longer reliably see only the delta, so they either re-read the whole diff or trust you blindly.
- **Comment anchors go stale at once.** Threads on rewritten commits can all show as outdated, which hides which ones you actually addressed.
- **Commits you don't have locally can be destroyed.** Reviewers who click "Commit suggestion" add commits to your branch on the server. A force-push from a local branch that lacks them deletes their work.

So: add new commits while the review is open, and clean up history (if the project wants that) after approval.

## 2. Commit shape for review fixes

- **One concern per commit,** or one tight group of identical fixes ("validate header names in all three parsers"). The reviewer can then check each thread against exactly one commit.
- **No drive-by changes.** A formatting sweep or an unrelated refactor inside a review-fix commit hides the fix. Put it in its own commit, or leave it out.
- **Reference the thread in the body,** so the history explains itself later. Use `workflow:commit-message` for format and conventions if it is installed; otherwise copy the style of `git log --oneline -20`. For example:

```text
fix(parser): reject empty header names

An empty name reached the map lookup and panicked. Return
ErrInvalidHeader instead and cover it with a test.

Review: https://github.com/<owner>/<repo>/pull/123#discussion_r<id>
```

- **Include the regression test in the same commit as the fix,** so the commit is checkable on its own.

## 3. Keeping history clean without rewriting mid-review

If the project wants each commit in the final history to be meaningful (rebase-merge or merge-commit workflows), use fixup commits now and fold them in later:

```bash
# Now: a fixup aimed at the commit that introduced the problem
git commit --fixup=<sha-of-original-commit>

# After approval: fold fixups into their targets WITHOUT moving the branch's base
base=$(gh pr view --json baseRefName -q .baseRefName)     # main, develop, a release branch, a parent in a stack
git fetch origin "$base"
git rebase --autosquash --keep-base "origin/$base"        # Git 2.44+ autosquashes without -i
# Older Git (2.24+ for --keep-base):
GIT_SEQUENCE_EDITOR=true git rebase -i --autosquash --keep-base "origin/$base"

git push --force-with-lease --force-if-includes
```

`--keep-base` replays the commits onto their current merge-base with the base branch, so the only change is the folded fixups. Without it, the same command also moves the branch onto the newest base, mixing in base changes that were never reviewed or tested with this code, and possibly new conflicts. Updating the base is a separate, deliberate step (section 4). Either way the result is new commits, so CI has to pass again before merge.

`--fixup=amend:<sha>` also rewrites the target's message, and `--fixup=reword:<sha>` changes only the message.

If the project squash-merges, skip all of this. Plain descriptive commits are better than `fixup!` commits there, because the commit list may be offered as the default squash message.

Rewriting after approval can itself reset the approval on some repositories (section 7). Ask the user and the reviewer first, or leave the cleanup to the merge strategy.

## 4. Bringing in changes from the base branch

Do it only when needed (conflicts, or a dependency on something that just landed), and follow the repository's norm:

- **Merge allowed:** `git fetch origin "$base" && git merge "origin/$base"`, with `base` from `gh pr view --json baseRefName -q .baseRefName` (it is not always `main`). History stays append-only, and the reviewer's view stays intact.
- **Linear history required:** rebase, but at a round boundary (right after you have pushed and replied, before the reviewer starts again), with the user's agreement (section 6), then announce it in the PR with the template in `reply-templates.md`.

Resolve conflicts in a commit separate from review fixes where the workflow allows it, so "conflict resolution" and "behavior change" never share a diff.

## 5. When the push is rejected

`! [rejected] ... (fetch first)` or `(non-fast-forward)` means the remote branch gained commits you do not have, usually a reviewer's "Commit suggestion" landing while you worked. Your local commits are unpublished, so rewriting them is safe:

```bash
git pull --rebase           # replay your unpushed commits on top of the remote branch
# resolve any conflicts, re-run the checks, then:
git push
```

Use `git pull --no-rebase` (a merge) instead if the repository prefers merges. Do not force-push to "win": that deletes the reviewer's commit. The rebase gives your commits new SHAs, so take the SHAs for your replies from the branch after the push.

## 6. If you must force-push

Only with the user's agreement, and only when nothing else works (for example, the repository requires a linear history and the base must be updated):

```bash
git push --force-with-lease --force-if-includes
```

- `--force-with-lease` refuses to overwrite the remote branch if it no longer matches your remote-tracking ref, which protects commits pushed by someone else since your last fetch.
- A background `git fetch` (from an IDE, for example) updates the remote-tracking ref silently and defeats the lease. `--force-if-includes` adds a check that the remote tip is actually in your local branch's history, which closes that gap.
- Never use plain `--force` on a branch under review.

Then post the force-push notice in the PR, naming which commits contain the review fixes.

## 7. Approvals that reset on push

Many repositories enable "Dismiss stale pull request approvals when new commits are pushed" (or require approval of the most recent push). On those, any push that changes the diff after approval sends the PR back for review.

- If you are approved with only nits left, ask whether the reviewer wants them in this PR or as a follow-up before pushing.
- Batch all remaining changes into one push, so the reviewer re-approves once.

## 8. Pre-push checklist

```bash
git fetch
git status -sb                                   # not behind the remote branch? (if so, section 5)
git log --oneline @{upstream}..HEAD              # exactly the commits you mean to push
git diff @{upstream}...HEAD --stat               # no stray files
```

Then run the checks CI will run (formatter, linter, type checker, affected tests). Use `implementation:verify-before-done` if it is installed; otherwise read the CI configuration (for example `.github/workflows/`) to see which commands CI runs, and run those. Pushing a red build forces the reviewer to wait or to review code that will change again.

If the PR is already approved, ask the user before pushing (section 7).

## 9. Amend-based and stacked workflows

- **Gerrit and other patch-set systems** review a single commit. There you *do* amend (`git commit --amend`) and push a new patch set; reviewers compare patch sets side by side. Section 1 does not apply, but the rest of this skill (verify, decide, reply to every comment, publish your drafts) does.
- **Stacked-diff tooling** manages restacking for you. Address feedback on the branch that owns the change and let the tool propagate it upward. Do not hand-rebase the stack.
