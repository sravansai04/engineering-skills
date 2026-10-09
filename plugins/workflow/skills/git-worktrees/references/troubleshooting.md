# Worktree troubleshooting

Error messages below are quoted from git 2.55; wording varies slightly between
versions, so match on the distinctive part.

## Contents

1. Creating worktrees
2. Removing worktrees and deleting branches
3. Pushing and pulling from a new branch
4. Moved, deleted, or mounted folders
5. Recovering lost work
6. "It works in the main checkout but not in the worktree"
7. Accidental commits involving worktrees
8. Common mistakes

## 1. Creating worktrees

**`fatal: '<branch>' is already used by worktree at '<path>'`**
The branch is checked out elsewhere and git allows one checkout per branch.
Options: go work in `<path>`; create a new branch from it
(`git worktree add -b <new> <newpath> <branch>`); or look without a branch
(`git worktree add --detach <newpath> <branch>`). If `<path>` no longer exists,
the entry is stale: `git worktree prune`, then retry. Avoid `--force`; two
checkouts of one branch drift apart silently.

**`fatal: '<path>' already exists`**
The target folder exists and is not empty. Pick another path, or inspect the
folder; it may be an old worktree removed with `rm` that still has files.

**`fatal: '<path>' is a missing but already registered worktree; use 'add -f' to override, or 'prune' or 'remove' to clear`**
A previous worktree at that path was deleted by hand. Run
`git worktree prune -v` (or `git worktree remove <path>`), then retry.

**`add` printed `HEAD is now at ...`, then a hook's error, and exited non-zero**
The worktree was created; the shared post-checkout hook failed afterwards, usually
because the tools it calls are not installed in the new tree yet. `git worktree
list` shows the tree and `git branch --list <name>` the branch. Do not retry the
`add` (it would fail with `already exists` or `already used by worktree`).
Finish setup in the tree, then re-run what the hook does if the project depends
on it (often `git -C <wt> checkout` with no arguments re-triggers it).

**After any failed `add`, a branch you asked for with `-b` may already exist.**
`git branch --list <name>` shows it. Retry without `-b`
(`git worktree add <path> <name>`), or delete it with `git branch -d <name>` if it
has no commits of its own.

**`fatal: invalid reference: <ref>`**
The start point does not exist locally. Usually a missing fetch
(`git fetch origin`) or a typo in the remote/branch name (`git branch -r` lists
remote branches).

**`warning: adding embedded git repository: .worktrees/<name>`**
You ran `git add` in a checkout that contains an unignored worktree. Unstage it
with `git rm --cached .worktrees/<name>` (this does not delete files), then ignore
the folder (`/.worktrees/` in `.git/info/exclude` or `.gitignore`).

## 2. Removing worktrees and deleting branches

**`fatal: '<path>' contains modified or untracked files, use --force to delete it`**
Not an obstacle to bypass. Run `"${CLAUDE_SKILL_DIR}/scripts/wt-preflight.sh" <path>`, then
commit, move, or deliberately discard what it lists.

**`fatal: cannot remove a locked working tree, lock reason: <reason>`**
Someone locked it on purpose (removable drive, an agent still running). Confirm
the reason no longer applies, `git worktree unlock <path>`, then remove.
`remove -f -f` skips the lock and the cleanliness check together; do not use it as
a shortcut.

**`fatal: working trees containing submodules cannot be moved or removed`**
Worktrees with populated submodules always need `git worktree remove --force`. Before
forcing, check that no submodule has uncommitted changes or commits that exist
only locally (the preflight does both), because a linked worktree's submodule
repositories are deleted with it.

**`error: cannot delete branch '<b>' used by worktree at '<path>'`**
Remove that worktree first. If `<path>` no longer exists, `git worktree prune`
clears the stale entry and the delete then works.

**`error: the branch '<b>' is not fully merged`**
`-d` compares the branch with its upstream when it has one, otherwise with the
HEAD of the checkout you run it in; it never looks at your base branch directly.
A refusal therefore has three common causes: the work really is unmerged; the
PR was squash- or rebase-merged and the upstream was deleted and pruned, so `-d`
fell back to HEAD, where the rewritten commits are not ancestors; or your local
base is stale (pull it, or compare with `origin/main` instead). Confirm the
content landed (preflight content check, or the merged PR on the code host),
then `git branch -D <b>`. If the check says the changes are not in the base,
keep the branch.

**`warning: deleting branch '<b>' that has been merged to 'refs/remotes/<remote>/<b>', but not yet merged to HEAD`**
`-d` succeeded only because the branch matches its own pushed copy. That says it
was pushed, not that it landed. If it had not landed, recreate it from the tip
in the `Deleted branch <b> (was <sha>)` line (`git branch <b> <sha>`), and do not
delete the remote copy until the landing is confirmed.

**Removing the worktree you are standing in**
git allows it, and your shell is left in a deleted directory where later
commands fail with confusing errors. `cd` to the main checkout first.

## 3. Pushing and pulling from a new branch

**`fatal: The upstream branch of your current branch does not match the name of your current branch.`**
The branch was created from `origin/main` without `--no-track`, so its upstream
is `origin/main`. Fix it once:

```bash
git branch --unset-upstream
git push -u origin <branch>
```

Prevent it with `--no-track` at creation, or set `branch.autoSetupMerge=simple`
(git 2.37+).

**`git pull` in a new branch merges main unexpectedly**
Same cause and fix as above.

## 4. Moved, deleted, or mounted folders

**A worktree shows `prunable` in `git worktree list`**
Its folder is missing from where the repository expects it. The repository cannot
tell the causes apart, so neither can `wt-preflight.sh`: it answers REVIEW, or
BLOCKED when the entry's detached HEAD holds commits that no branch, tag, or
remote has (save those first with the `git branch rescue/...` command it prints).
Two very different causes:

- Deleted: `git worktree prune -v` cleans up the entry.
- Moved with `mv`: the moved folder still works from inside, but **pruning now
  breaks it**. Run `git worktree repair` from inside the moved folder (or
  `git worktree repair <new-path>` from the main checkout) instead. If it was
  already pruned, follow the rebuild steps under "pruned while unplugged" below.

Prevent both by using `git worktree move` and `git worktree remove`.

**Every linked worktree fails with `fatal: not a git repository: ...`**
The main repository folder was moved or renamed. From the new main location run
`git worktree repair <path-of-each-linked-worktree>`.

**git fails inside a container or VM that mounts the worktree**
The worktree's `.git` file holds an absolute path to the repository's
`.git/worktrees/<name>`, which does not exist at that path inside the container.
Mount the repository and worktree at identical absolute paths, use a separate
clone inside the container, or link worktrees with relative paths (git 2.48+:
`git worktree add --relative-paths`, or `worktree.useRelativePaths=true` plus
`git worktree repair`). Relative links set a repository extension that older git
and some libgit2-based tools refuse, so check every tool that reads the
repository first. Do not run `git worktree repair` inside the container to "fix"
it; that rewrites the links for the container's paths and breaks the host side.

**A worktree on an external or network drive was pruned while unplugged**
Lock such worktrees (`git worktree lock --reason "external drive" <path>`); locked
entries are never pruned. If it already happened, `repair` cannot help (the
administrative entry is gone, and git reports `.git file does not reference a
repository`). Commits on the branch are safe in the shared refs; the files on
the drive are intact. Rebuild the worktree and carry the uncommitted state over:

```bash
mv <path> <path>-old
git worktree add <path> <branch>
rsync -a --delete --exclude .git <path>-old/ <path>/   # trailing slashes matter
git -C <path> status --short                           # review what came across
rm -rf <path>-old                                      # only after reviewing
```

**Windows: `Filename too long` in a deeply nested worktree**
Shorten the worktree path, or enable long paths in Git for Windows
(`git config core.longpaths true`).

## 5. Recovering lost work

**Commits made on a detached HEAD in a removed worktree**
The worktree's HEAD reflog was deleted with it, so the commits are unreachable
but still present until garbage collection prunes them (two weeks by default).

```bash
git fsck --unreachable --no-reflogs | grep commit      # candidate commit IDs
git show --stat <sha>                                  # find yours
git branch rescue/<name> <sha>                         # make it reachable again
```

**Branch deleted with `-D` by mistake**
The deletion message printed the tip (`Deleted branch <b> (was <sha>)`). Recreate
it: `git branch <b> <sha>`. Without the message, search the HEAD reflog of the
worktree that last had it checked out (`git reflog`), or use the `fsck` command
above.

**Ignored files deleted by `git worktree remove`**
git keeps no copy of ignored files. Recovery depends on your editor's local
history, backups, or filesystem snapshots. Running the preflight before removal
is the only real protection.

**A stash entry made in a removed worktree**
Stashes are shared and survive removal: `git stash list`, then
`git stash apply stash@{n}` in any worktree.

## 6. "It works in the main checkout but not in the worktree"

Work through these in order:

1. **Dependencies resolved from the main checkout.** Node searches parent
   directories for `node_modules`, so a worktree nested inside the repository
   with no install of its own silently loads the main checkout's packages.
   Check: `node -p "require.resolve('<pkg>')"`. Python: a shared environment
   with an editable install points at whichever tree installed it; check with
   `python -c "import <pkg>; print(<pkg>.__file__)"`.
2. **Config found by walking up directories.** Linters, formatters, and `.env`
   loaders often search parent directories for their config; inside a nested
   worktree they may pick up the main checkout's files. Make sure the worktree
   has its own copies, or place worktrees outside the repository.
3. **Missing local files.** Compare
   `git -C <main> ls-files --others --ignored --exclude-standard --directory`
   with the same command in the worktree.
4. **Absolute paths.** `git -C <wt> grep -n "<main checkout path>"`, plus editor
   run configurations and environment variables (`env | grep <main path>`).
5. **Hooks missing.** `git -C <wt> config core.hooksPath`; if it points at a
   folder created during install, install dependencies in the worktree.
6. **Different branch content.** The worktree is on another commit;
   `git -C <wt> log -1` versus `git -C <main> log -1`, and diff the relevant config.
7. **Shared resource collision.** Another worktree's server holds the port or
   database; check with `lsof -i :<port>` (macOS/Linux).

## 7. Accidental commits involving worktrees

**Committed in the wrong worktree / on the wrong branch**
Move the commits to the right branch, then remove them from the wrong one:

```bash
git -C <right-wt> cherry-pick <sha1> <sha2>    # oldest first; bring them where they belong
git -C <wrong-wt> reset --keep <sha-before>     # drop them, keeping unrelated local edits
```

If the wrong branch was already pushed and shared, revert instead of resetting.

**Committed `.env` or another secret from a worktree**
Remove it from the commit before pushing (`git rm --cached .env` and amend). If it
was pushed, treat the secret as exposed: rotate it, then clean history as your
project's policy requires.

## 8. Common mistakes

| Mistake | Consequence | Do instead |
|---|---|---|
| Creating `.worktrees/` inside the repo without checking it is ignored | Outer checkout shows it untracked; `git add -A` commits an embedded repo | `git check-ignore -q .worktrees/probe`, add to `.git/info/exclude` if needed |
| `-b <branch> <path> origin/main` without `--no-track` | Upstream becomes `origin/main`; `git push` refuses, `git pull` merges main | `--no-track`, then `git push -u origin <branch>` |
| Forcing a second checkout of a branch | Two trees on one branch drift silently | Reuse that worktree, branch off it, or `--detach` |
| Installing and testing a stranger's PR in a fresh worktree | The PR's install scripts and tests run with your credentials | Trust gate first (SKILL.md step 4); read-only or a throwaway container otherwise |
| Editing before running the baseline | Pre-existing failures get blamed on your change | Baseline first, recorded with the base SHA |
| Symlinking `node_modules` or a venv from the main tree | Installs in one tree corrupt the other; venv paths break | Install per worktree; rely on global caches for speed |
| Running code in a nested worktree before installing | Node silently resolves the main checkout's `node_modules`; results reflect the wrong dependencies | Install first; check with `node -p "require.resolve('<pkg>')"` |
| Copying the whole main tree or every ignored file | Gigabytes of stale artifacts; secrets spread around | Copy named files only, then verify they are ignored |
| Same port / database / container project in two trees | Servers fail to bind, tests clobber shared data | Per-worktree slot for each shared resource |
| `rm -rf` on a worktree folder | Stale metadata; branch still reported "in use" until pruned | `git worktree remove`, or `git worktree prune` after the fact |
| Trusting `git worktree remove` to protect your work | Ignored files, detached commits, submodule commits, and in-progress rebases are lost | Run `wt-preflight.sh` first |
| Removing the worktree your shell is in | Shell left in a deleted directory; later commands fail oddly | `cd` to the main checkout first |
| `git branch -D` because `-d` refused | Unmerged work deleted | Check integration (preflight or code host) before `-D` |
| Treating a successful `git branch -d` as "merged" | With an upstream set, `-d` only checks the branch was pushed; unmerged work is deleted locally and then on the remote | Confirm landing first (preflight "already in <base>", or host shows merged), then delete both copies |
| Using `git stash` across parallel worktrees | Another tree pops your entry | WIP commits on your own branch |
| Pruning while a worktree was moved by hand | The moved tree loses its link to the repository | Preflight each `prunable` entry; `git worktree repair <new-path>` for moved ones, then prune |
| Retrying `worktree add` after it "failed" | `already exists` / `already used by worktree`, because a hook failed after the tree was created | Check `git worktree list` and `git branch --list <name>` first |
| `git clean -ffdx` or `docker build .` in a checkout with nested worktrees | Nested worktrees deleted, or shipped (with `.env` files) into the build context | Never `-ff` there; list `.worktrees/` in `.dockerignore` |
