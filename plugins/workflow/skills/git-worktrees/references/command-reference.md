# git worktree command reference

Checked against the `git-worktree`, `git-config`, and `git-rev-parse` manuals
(git 2.55) and exercised in scratch repositories. When in doubt on an older
machine, run `git worktree <subcommand> -h`; it lists exactly what that build
supports.

## Contents

1. Minimum versions
2. `add`
3. `list` and the porcelain format
4. `lock` / `unlock`
5. `move`
6. `remove`
7. `prune`
8. `repair`
9. What is shared and what is per-worktree
10. Locating things from inside any worktree
11. Branch housekeeping that interacts with worktrees
12. Checking out pull/merge requests
13. Related configuration

## 1. Minimum versions

| Feature | Git version |
|---|---|
| `git worktree` | 2.5 |
| `worktree move`, `worktree remove` | 2.17 |
| `rev-parse --path-format=absolute` | 2.31 (older builds echo the flag back and exit 0, so check the version instead of the exit code) |
| `branch.autoSetupMerge=simple` | 2.37 |
| `merge-tree --write-tree` (content-based "already merged?" check) | 2.38 (older builds exit 128) |
| `worktree add --orphan` | 2.42 |
| `--relative-paths`, `worktree.useRelativePaths` | 2.48 |

## 2. `add`

```
git worktree add [-f] [--detach] [--checkout] [--lock [--reason <string>]]
                 [--orphan] [(-b | -B) <new-branch>] <path> [<commit-ish>]
```

`<path>` is resolved against the current directory. The command fails if
`<path>` exists and is not an empty directory.

| Goal | Command |
|---|---|
| New branch from a start point | `git worktree add -b <new> <path> <start>` |
| New branch from a remote base, no upstream | `git worktree add --no-track -b <new> <path> origin/main` |
| Existing local branch | `git worktree add <path> <branch>` |
| Branch that exists only on one remote | `git worktree add <path> <branch>` (creates `<branch>` tracking `<remote>/<branch>`) |
| Detached HEAD at any commit, tag, or `FETCH_HEAD` | `git worktree add --detach <path> <commit-ish>` |
| Brand-new unborn branch with an empty tree (docs site, fresh history) | `git worktree add --orphan -b <new> <path>` |
| Create and lock in one step (removable or network drive) | `git worktree add --lock --reason "<why>" <path> <branch>` |
| Create without checking files out (to configure sparse checkout first) | `git worktree add --no-checkout <path> <branch>` |

Options:

| Option | Effect |
|---|---|
| `-b <new>` | Create `<new>` at `<commit-ish>` (default `HEAD`); refuses if it exists. |
| `-B <new>` | Same, but if `<new>` exists it is **reset** to `<commit-ish>`. Destructive for that branch's unmerged commits; avoid unless you mean it. |
| `-d`, `--detach` | Detached HEAD; no branch is checked out or created. |
| `--no-checkout` | Register the worktree but leave the files unpopulated. |
| `--lock`, `--reason <text>` | Lock immediately (no window where `prune` could remove it). |
| `--orphan` | New unborn branch, empty index and tree. Pass the branch with `-b`; a commit-ish after the path is an error. |
| `--track` / `--no-track` | Whether the new branch records `<commit-ish>` as its upstream. Default: yes when `<commit-ish>` is a remote-tracking branch. |
| `--guess-remote` | With no `<commit-ish>`: base the new branch on a remote branch whose name matches the path's basename. Config default: `worktree.guessRemote`. |
| `-f`, `--force` | Allow checking out a branch already checked out elsewhere, or reuse a registered-but-missing path. Twice to reuse a missing path that is locked. Rarely the right answer. |
| `--relative-paths` | Link the worktree with relative paths (2.48+). See section 13. |
| `-q` | Quiet. |

Implicit behavior when you leave things out:

- `<commit-ish>` names a branch that does not exist locally but exists on exactly
  one remote: git creates the local branch tracking that remote branch.
- No `<commit-ish>` and no `-b`/`-B`/`--detach`: git uses a branch named after the
  last path component, creating it from `HEAD` if needed. Convenient, but it
  silently ties the branch name to the folder name; prefer being explicit.
- If `add` fails (occupied path, registered-but-missing path), a branch requested
  with `-b` may already exist afterwards. Check with `git branch --list <new>`
  before retrying.
- `add` runs the post-checkout hook (unless `--no-checkout`). If the hook exits
  non-zero, so does `add`, even though the worktree and branch were created
  and checked out. Common in fresh trees, where the hook's tools are not
  installed yet. After a failed `add`, check `git worktree list` as well as
  `git branch --list <new>` before retrying.

Sparse checkout in a worktree (keeps the main checkout full):

```bash
git worktree add --no-checkout ../big-repo-api feat/api-change
git -C ../big-repo-api sparse-checkout set services/api libs/shared
git -C ../big-repo-api checkout          # populates only the selected directories
```

`sparse-checkout` stores its setting in the worktree's own config file
(`config.worktree`), so other worktrees are unaffected.

## 3. `list` and the porcelain format

```
git worktree list [-v | --porcelain [-z]]
```

Human output: one line per worktree, main first, with abbreviated HEAD, `[branch]`
or `(detached HEAD)`, and annotations `locked` / `prunable`. `-v` adds the lock
and prune reasons. `--expire <time>` controls which missing worktrees are
annotated as prunable.

Porcelain output (stable across versions and user config; use it in scripts):
one `label value` attribute per line, blank line between records, first
attribute always `worktree`.

```
worktree /home/dev/myrepo
HEAD 3f9c2e1d...
branch refs/heads/main

worktree /home/dev/myrepo-retry-backoff
HEAD 8a17b04c...
branch refs/heads/feat/retry-backoff
locked agent-2 running

worktree /home/dev/myrepo-v1.4
HEAD 51de0aa9...
detached
prunable gitdir file points to non-existent location
```

Attributes: `worktree <path>`, `HEAD <sha>`, `branch <full ref>` or `detached`,
`bare`, `locked` or `locked <reason>`, `prunable <reason>`. Add `-z` when paths
may contain newlines. Paths are physical (symlinks resolved), so resolve your own
path with `cd <dir> && pwd -P` before comparing.

Which worktree holds a branch:

```bash
git worktree list --porcelain |
  awk -v want="branch refs/heads/feat/retry-backoff" '/^worktree /{p=substr($0,10)} $0==want{print p}'
```

`git branch` also marks branches checked out in *other* worktrees with `+`
(the current one with `*`).

## 4. `lock` / `unlock`

```
git worktree lock [--reason <string>] <worktree>
git worktree unlock <worktree>
```

A lock makes `prune` (and the automatic prune in `git gc`) skip the entry
entirely; `prune` has no option to override that. It makes `move` and `remove`
refuse unless `--force` is given twice (`-f -f`), and `add -f` will not reuse a
missing locked path unless `-f` is given twice. Use it for worktrees on removable
or network storage, and for worktrees an agent or long job is actively using.

`<worktree>` (here and for `move`, `remove`, `repair`) is a path, relative or
absolute, or the last path component(s) when they are unique among the
worktrees. Components match whole, not as substrings: for
`~/worktrees/myrepo-retry-backoff`, `myrepo-retry-backoff` and
`worktrees/myrepo-retry-backoff` work, `retry-backoff` does not
(`fatal: 'retry-backoff' is not a working tree`).

## 5. `move`

```
git worktree move <worktree> <new-path>
```

Updates both directions of the link. Refuses the main worktree, refuses
worktrees containing submodules (`working trees containing submodules cannot be
moved or removed`), and refuses locked worktrees unless `--force` is given twice.
If a folder was moved with plain `mv`, use `repair` instead.

## 6. `remove`

```
git worktree remove [-f] <worktree>
```

| State of the worktree | Result |
|---|---|
| Clean (no modified tracked files, no untracked files) | Removed, **including every ignored file** (`.env`, `node_modules`, local DBs, notes) |
| Modified or untracked files | Refused: `contains modified or untracked files, use --force to delete it` |
| Contains populated submodules (the worktree's private `modules/` folder exists, or a submodule is checked out) | Refused even when clean; `--force` required. A `.gitmodules` file with no submodule initialized does not trigger this. |
| Locked | Refused: `cannot remove a locked working tree, lock reason: ...`; unlock, or `-f -f` |
| Main worktree | Always refused |

What `remove` never checks: ignored files, an in-progress rebase/merge/bisect,
commits reachable only from a detached HEAD (the worktree's HEAD reflog is
deleted with it), and unpushed commits in submodules (a linked worktree's
submodule repositories live under `.git/worktrees/<name>/modules/` and are deleted
too). `"${CLAUDE_SKILL_DIR}/scripts/wt-preflight.sh"` checks all of these.

The branch survives removal. Delete it separately (section 11).

## 7. `prune`

```
git worktree prune [-n] [-v] [--expire <expire>]
```

Deletes administrative entries (`.git/worktrees/<name>`) whose folders no longer
exist. `-n` shows what would go; `-v` reports it. `git gc` runs this
automatically for entries older than `gc.worktreePruneExpire` (default three
months). Locked entries are never pruned.

Caution: a worktree folder moved with plain `mv` looks missing to the main
repository and is listed as `prunable`, while still working from inside. Pruning
then breaks it. Run `repair` from the moved folder first. The same applies to a
folder on a drive that is merely unplugged. Pruning an entry whose detached HEAD
held commits no branch contains makes those commits unreachable. Because a
deleted folder and a moved one look identical from the repository,
`wt-preflight.sh` answers REVIEW (or BLOCKED for such commits) for a missing
folder, never SAFE.

## 8. `repair`

```
git worktree repair [<path>...]
```

| What happened | Run |
|---|---|
| A linked worktree folder was moved with `mv` | `git worktree repair` inside the moved folder, or `git -C <main> worktree repair <new-path>` |
| The main repository folder was moved | `git -C <new-main> worktree repair <each linked path>`; until then linked worktrees fail with `not a git repository` |
| Switching between absolute and relative links (2.48+) | `git worktree repair` after changing `worktree.useRelativePaths` |

## 9. What is shared and what is per-worktree

| Shared by all worktrees | Private to one worktree |
|---|---|
| Objects (history) | `HEAD` and other pseudo-refs (`FETCH_HEAD`, `ORIG_HEAD`, `MERGE_HEAD`) |
| `refs/heads/*`, `refs/tags/*`, `refs/remotes/*` | Index (staging area) |
| `refs/stash` (the stash) | Working files |
| Repository config (`.git/config`) | `refs/bisect/*`, `refs/worktree/*`, `refs/rewritten/*` |
| `.git/hooks`, `.git/info/exclude` | Rebase/merge/cherry-pick/bisect state |
| Reflogs of branches | HEAD reflog |
| | `config.worktree` (when `extensions.worktreeConfig` is enabled) |
| | Submodule repositories of that worktree |

Another worktree's private refs are addressable as `worktrees/<name>/HEAD` and the
main one's as `main-worktree/HEAD`.

## 10. Locating things from inside any worktree

```bash
git rev-parse --show-toplevel                           # this worktree's root
git rev-parse --path-format=absolute --git-dir          # this worktree's private dir
git rev-parse --path-format=absolute --git-common-dir   # the shared .git
git rev-parse --path-format=absolute --git-path hooks   # resolves to the shared hooks dir
git rev-parse --path-format=absolute --git-path rebase-merge   # per-worktree operation state
```

Never assume `.git` is a directory: in a linked worktree it is a one-line file
(`gitdir: /path/to/repo/.git/worktrees/<name>`). Tools and scripts that open
`.git/...` directly break there; route through `git rev-parse --git-path`.

The main worktree is the first record of `git worktree list --porcelain`. For a
normal (non-bare) repository it is also the parent of `--git-common-dir`.

## 11. Branch housekeeping that interacts with worktrees

| Command | Behavior with worktrees |
|---|---|
| `git branch -d <b>` / `-D <b>` | Refused while `<b>` is checked out in any worktree: `cannot delete branch '<b>' used by worktree at '<path>'`. Remove (or prune) the worktree first. |
| `git branch -d <b>` in general | Not a merge check against your base. `-d` compares `<b>` with **its upstream** when it has one, and only otherwise with the **HEAD of the checkout you run it in**. After `git push -u`, the upstream is the branch's own remote copy, so `-d` deletes a pushed but completely unmerged branch, printing only `warning: deleting branch '<b>' that has been merged to 'refs/remotes/origin/<b>', but not yet merged to HEAD`. |
| `git branch -d <b>` after a squash or rebase merge | Either outcome is possible. If the upstream still exists, `-d` succeeds (see above). If the host deleted it and you fetched with `--prune`, `-d` falls back to HEAD, where the rewritten commits are not ancestors, so it refuses with "not fully merged". It also refuses when your local base is stale. Confirm the content landed (below, or the host's merged state), then `-d`, or `-D` if it refuses. |
| `git branch -f <b> <x>`, `git switch <b>` | Refused while `<b>` is checked out elsewhere. |
| `git push origin --delete <b>` | Deletes the remote branch; unaffected by worktrees. |

Content-based "is this branch already in main?" check (git 2.38+), which works
after squash and rebase merges:

```bash
git fetch origin
merged_tree=$(git merge-tree --write-tree origin/main feat/retry-backoff | head -n 1)
[ "$merged_tree" = "$(git rev-parse 'origin/main^{tree}')" ] && echo "already integrated"
```

If merging the branch into `origin/main` would leave `origin/main`'s tree
unchanged, every change on the branch is already there. A conflict (exit status 1)
or a different tree means it is not.

## 12. Checking out pull/merge requests

Host-neutral: fetch the request's ref, then add a detached worktree at it.

```bash
# GitHub
git fetch origin pull/123/head && git worktree add --detach ../myrepo-pr-123 FETCH_HEAD
# GitLab
git fetch origin merge-requests/123/head && git worktree add --detach ../myrepo-mr-123 FETCH_HEAD
# Named local branch instead of detached (to push follow-up commits you need the
# PR's real branch and permission to push to it)
git fetch origin pull/123/head:pr-123 && git worktree add ../myrepo-pr-123 pr-123
```

With the GitHub CLI 2.98 or newer, one command creates the worktree and checks
the PR out into it:

```bash
gh pr checkout 123 --worktree ../myrepo-pr-123                 # local branch named after the PR's head
gh pr checkout 123 --worktree ../myrepo-pr-123 --detach        # no branch
gh pr checkout 123 --worktree ../myrepo-pr-123 --branch pr-123 # choose the local name
```

Re-running it against the same path fast-forwards that worktree; adding `--force`
there resets the worktree's branch to the PR tip, discarding local commits on it.
With older gh, create a detached worktree first, then run `gh pr checkout 123`
inside it. Either way it fails if the PR's branch is already checked out in
another worktree, for the usual one-branch-one-worktree reason.

## 13. Related configuration

| Key | Effect |
|---|---|
| `branch.autoSetupMerge=simple` (git 2.37+) | New branches get an upstream only when the start point is a remote branch **with the same name**, which removes the need for `--no-track` on topic branches. Affects `git branch`/`switch`/`checkout`/`worktree add -b`. |
| `worktree.guessRemote=true` | Make `--guess-remote` the default for `add <path>` without a commit-ish. |
| `worktree.useRelativePaths=true` | Link new worktrees with relative paths (2.48+). Helps when the repo and worktrees are mounted into a container at a different absolute path. It also sets the `extensions.relativeWorktrees` repository extension, which older git versions and some libgit2-based tools refuse to open. |
| `extensions.worktreeConfig=true` | Enables per-worktree `config.worktree`, written with `git config --worktree <key> <value>`. Older git refuses repositories with this extension. `sparse-checkout` turns it on automatically. |
| `gc.worktreePruneExpire` | How old a missing worktree's metadata must be before `git gc` prunes it (default `3.months.ago`; `never` disables). |
| `core.hooksPath` | If relative, resolved from the root of the worktree running the hook, so each worktree uses its own checked-out copy of a committed hooks folder. |
