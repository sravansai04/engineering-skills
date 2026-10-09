# Branch Situations

Read this from step 1 of SKILL.md when the branch isn't a plain topic branch off `origin`'s default branch. Each case describes how to spot it, what to diff, and what to tell the user. As in SKILL.md, `<remote>`, `<base>`, `<branch>` and `<n>` stand for literal values you have already resolved.

Contents:
1. Work committed on the base branch
2. Forks: the base repository is not `origin`
3. Resolving the base offline
4. A reused branch name
5. Update mode when local HEAD is not the PR's head
6. Stacked branches

## 1. Work committed on the base branch

Signs: `git branch --show-current` prints the base or default branch name, or nothing (detached HEAD), and `git log <remote>/<base>..HEAD` lists the user's commits.

- Drafting a description is fine. The range `<remote>/<base>..HEAD` is still correct.
- Never push from here. `git push -u origin HEAD` on the default branch sends the commits straight to it, skipping review, and with continuous deployment it may ship them.
- Propose `git switch -c <topic-branch>`. The commits come along, and pushing and `gh pr create` then work normally.
- Tell the user that their local base branch still holds the commits. After the PR is open they can reset it to the remote (for example `git branch -f <base> <remote>/<base>` while on the topic branch). That command moves a branch, so leave it to them or run it only with explicit approval.

## 2. Forks: the base repository is not `origin`

Signs: `gh repo view --json nameWithOwner,isFork,parent` reports `isFork: true`, or `git remote -v` shows both `origin` and `upstream`.

- The base repository is the parent. `gh repo set-default --view` shows which repository gh will target. In a clone with several remotes, gh may already target the upstream, and then `isFork` reads false for it.
- Use the remote whose URL matches the base repository as `<remote>` for every fetch, log and diff, and for the scans in `risk-signals.md`. Never measure against `origin/<base>` in a fork: the fork's default branch is usually behind, so the range pulls in every upstream commit since the last sync.
- If no remote points at the base repository, ask the user to add one (`git remote add upstream <url>`) or to sync the fork. Don't add remotes yourself without approval.
- Push to the fork's remote (usually `origin`), then create the PR against the base repository: `gh pr create --repo <base-owner>/<repo> --base <base> --head <fork-owner>:<branch> ...`. gh can't use an organization as the `--head` owner.
- If gh can't reach the host and an `upstream` remote exists, assume `upstream` is the base and say so in Notes.

## 3. Resolving the base offline

`git rev-parse --abbrev-ref <remote>/HEAD` prints `<remote>/main`, not `main`. The base is the part after the slash. If the command fails, `<remote>/HEAD` was never recorded, which is common when a remote was added to an existing clone. `git remote set-head <remote> --auto` repairs it but needs network access. Otherwise ask the user for the base.

## 4. A reused branch name

Without an argument, `gh pr view` searches PRs in every state for the current branch and prefers an open one. If the only match is `MERGED` or `CLOSED`, the branch name was reused or the earlier PR is finished. Treat that as "no open PR":

- Don't reuse its base without checking, and don't rewrite a merged PR's description.
- In Create mode, create a new PR. Mention the earlier PR in Notes, and link it in the body if it's related.

## 5. Update mode when local HEAD is not the PR's head

Compare `git rev-parse HEAD` with the PR's `headRefOid` (from `gh pr view <n> --json headRefOid,headRefName,isCrossRepository`).

- **Local commits not yet pushed** (`headRefOid` is an ancestor of HEAD): ask whether to push first. Pushing needs approval. Otherwise describe only what is on the PR and say in Notes that local commits aren't included.
- **Another branch is checked out**: don't switch branches, since that could disturb the user's working tree. Read the PR's real head instead:
  - `gh pr diff <n>` and `gh pr diff <n> --name-only` for the change, and `gh pr view <n> --json commits` for the history.
  - Or `git fetch <remote> pull/<n>/head`, then `git log <remote>/<base>..FETCH_HEAD` and `git diff <remote>/<base>...FETCH_HEAD`. On GitHub, `pull/<n>/head` lives on the base repository, so in a fork use the upstream remote.
- **The PR was force-pushed since the body was written**: describe the current head. Sections that describe an earlier revision are the ones to rewrite.

## 6. Stacked branches

Signs: `git log --oneline <remote>/<base>..HEAD` lists commits that aren't part of this work, so the branch was cut from another feature branch.

- The base is the parent branch. Ask, or pick the parent and say so in the description (the stacked variant in `pr-body-template.md` shows the wording).
- Closing keywords in a PR that targets a feature branch don't fire. See "Links" in `pr-body-template.md`.
- **The parent's PR already merged.** Check with `gh pr list --state merged --head <parent-branch>`. After a squash or rebase merge, the parent's original commits are still on this branch, and both the three-dot diff and the Files tab show them again. The usual remedy, "use the parent as the base", no longer works, because the parent branch is merged and often deleted.
  - Find the old parent tip: the last commit on this branch that belongs to the parent's work.
  - Propose `git rebase --onto <remote>/<base> <old-parent-tip>`. This rewrites history and needs a force-push, so get the user's approval first.
  - Until then, describe only `git diff <old-parent-tip>...HEAD` and `git log <old-parent-tip>..HEAD`, and say in Notes that the Files tab will show extra changes until the rebase.
- Hosts with built-in stacking support can rebase the rest of the stack automatically after a merge. If the repository uses that, follow its flow instead.
