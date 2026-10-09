# Splitting and Staging Without Interactive Prompts

Interactive commands like `git add -p`, `git reset -p`, and plain `git rebase -i` wait for
keyboard input, so an agent's shell usually can't drive them. Don't script answers into
`git add -p` either: the sequence of prompts depends on how git splits the hunks, so a script
of `y`/`n` answers breaks easily. The recipes below avoid those commands and were checked
against a scratch repository.

**Prompts that can still appear.** Watch for these in every recipe:

- **Editors.** `git rebase --continue`, `git cherry-pick --continue`, `git merge --continue`,
  and a `git commit` without `-m` or `-F` open the message editor even with no terminal
  attached, and a terminal editor then hangs the shell. Prefix them with `GIT_EDITOR=true` to
  keep the message git prepared.
- **Signing.** With `commit.gpgsign` set, any commit can wait on a passphrase or security-key
  prompt. If one blocks, stop and tell the user. Don't bypass it with `--no-gpg-sign` or
  `-c commit.gpgsign=false` unless they ask.
- **Credentials.** `git fetch` and `git push` can ask for a username or password. Setting
  `GIT_TERMINAL_PROMPT=0` makes them fail at once instead of waiting.

## Contents

1. Choosing a method
2. Stage whole paths
3. Stage selected hunks from a patch
4. Changes that share a hunk
5. Changes on the same line: the temporary-edit method
6. Mechanical changes: regenerate, don't pick
7. New, deleted, renamed, and binary files
8. Check that each commit stands alone
9. Split the last commit (unpushed)
10. Split or reword an older commit (unpushed)
11. Fixup commits during review
12. Safety net
13. Resolving conflicts when updating a branch

---

## 1. Choosing a method

| Situation | Method |
|---|---|
| Each file belongs to exactly one commit | Section 2 (paths) |
| A file has separate hunks for different commits | Section 3 (patch hunks) |
| Changes for different commits are close enough to share a hunk | Section 4 (`-U1`, or edit the patch) |
| One line changed for two reasons, or the edits interleave too much to separate | Section 5 (temporary edit) |
| A formatter, codemod, or automated rename touched the same lines as hand-written logic | Section 6 (regenerate) |
| The mixed commit already exists | Sections 9 and 10 |

Work on one file at a time, from the repository's top-level directory. Check
`git diff --cached` and `git diff` after each step.

## 2. Stage whole paths

```bash
git add -- src/cart/total.py tests/test_total.py
git add -- ':(glob)src/cart/*.py'           # this directory only; see the note on patterns
git diff --cached --name-only               # always confirm what a pattern picked up
git restore --staged -- src/cart/debug.py   # unstage (Git 2.23+; older: git reset -- path)
```

Quote patterns so git matches them, not the shell, and know that git's matching differs from
the shell's. In a plain pathspec, `*` also matches `/`, so `'src/cart/*.py'` stages
`src/cart/deep/b.py` too. The `:(glob)` prefix gives shell-like matching, where `*` stays
inside one directory and `**` crosses directories. Listing the paths explicitly is the safest
choice of all.

`git commit -- path1 path2` is a shortcut that commits the working-tree contents of just those
paths. It ignores anything staged for other paths, and that staged content stays staged for
the next commit. It takes the whole file, so use it only when the whole file belongs in this
commit.

## 3. Stage selected hunks from a patch

```bash
f=src/billing/invoice.ts
tmp=$(mktemp -d)
git diff --no-color --no-ext-diff --src-prefix=a/ --dst-prefix=b/ -- "$f" > "$tmp/full.patch"
grep -n '^@@' "$tmp/full.patch"          # list the hunks in order: 1, 2, 3, ...

# Keep the file header (everything before the first @@) plus hunks 1 and 3:
awk -v keep=' 1 3 ' '/^@@/{n++} n==0 || index(keep, " " n " ")' "$tmp/full.patch" > "$tmp/part.patch"

git apply --cached --check --recount "$tmp/part.patch" && git apply --cached --recount "$tmp/part.patch"
git diff --cached -- "$f"                # the staged hunks
git diff -- "$f"                         # what remains for later commits
```

The `git diff` flags make the patch independent of the user's configuration. `color.ui=always`
would fill it with color codes ("No valid patches in input"). `diff.noprefix` would drop the
`a/` and `b/` that `git apply` expects to strip, so it would look for the wrong path. An
external diff tool would replace the format entirely. On Git 2.41+, `--default-prefix` can
stand in for the two prefix flags. Use the same flags everywhere this file produces a patch.

This works because every hunk in a `git diff` carries its own context, so any subset of hunks
still applies to the index. The awk filter assumes a single-file diff. In a multi-file patch,
the hunk count runs across files and the later file headers get dropped, which is why the
recipe runs per file.

## 4. Changes that share a hunk

There are two ways to separate changes that sit in the same hunk.

**Shrink the context.** Adding `-U1` to the `git diff` command in section 3 keeps one line of
context instead of three, so changes a few lines apart usually come out as separate hunks.
Don't go to `-U0`. A patch with no context needs `git apply --unidiff-zero` and loses the
safety check that the patch lands where you expect.

**Edit the patch.** Open the extracted patch and change only `+` and `-` lines:

- To leave out an added line, delete that `+` line.
- To leave out a removed line, change its leading `-` to a single space so it becomes context.
- Don't touch context lines, which start with a space.

Then apply it with `--recount`, on both the check and the apply, so git recomputes the line
counts in the hunk header:

```bash
git apply --cached --check --recount "$tmp/part.patch" && git apply --cached --recount "$tmp/part.patch"
```

## 5. Changes on the same line: the temporary-edit method

A patch can't split one line between two commits. Instead, stage an intermediate version of
the file:

```bash
tmp=$(mktemp -d)
cp src/cart/total.py "$tmp/total.py.final"   # 1. save the finished version
# 2. edit src/cart/total.py down to the state the FIRST commit should contain
git add -- src/cart/total.py                  # 3. stage that intermediate state
cp "$tmp/total.py.final" src/cart/total.py    # 4. restore the finished version
git diff --cached -- src/cart/total.py        # first commit's change only
git diff -- src/cart/total.py                 # the rest, still unstaged
```

Do step 2 with a precise file-edit tool, not a broad regex replace. If step 4 is missed, work
is lost, so check that the restored file matches the saved copy
(`cmp "$tmp/total.py.final" src/cart/total.py`).

## 6. Mechanical changes: regenerate, don't pick

A formatter run usually touches the same lines as the logic you changed, so its hunks rarely
come apart cleanly. Don't pick them out. Re-run the tool on the committed version of the file,
and commit its output on its own. The same works for a codemod or an automated rename. Do this
when the mechanical commit comes first in the plan:

```bash
f=src/api/handlers.ts
tmp=$(mktemp -d)
cp "$f" "$tmp/final"                            # 1. save the finished file
git restore --source=HEAD --worktree -- "$f"    # 2. put back the committed version (Git 2.23+)
npx prettier --write "$f"                       # 3. run ONLY the mechanical tool (the project's
                                                #    own formatter or codemod, at its pinned version)
git add -- "$f"                                 # 4. stage the tool's output, then commit it
                                                #    as style/refactor, naming the tool and command
cp "$tmp/final" "$f"                            # 5. restore the finished file
cmp "$tmp/final" "$f" && git diff -- "$f"       # 6. what's left is the hand-written change
```

If the finished file was formatted with the same tool, the remaining diff holds only the logic
change. If it wasn't, run the tool on the finished file too, and check that the diff now
contains nothing but the intended change. For a tool that touches many files, repeat steps 1,
2 and 5 for each file, keeping each saved copy under its own path in `$tmp`.

## 7. New, deleted, renamed, and binary files

- **Whole new file:** `git add -- path`.
- **Part of a new file:** run `git add --intent-to-add -- path` first, so `git diff` shows the
  file as additions. Then use section 3 or 4. The temporary-edit method also works.
- **Deleted file:** `git add -- path` (or `git rm -- path`) stages the deletion.
- **Rename:** `git mv old new`, or stage the deletion and the new path in the same commit. Git
  detects renames by content similarity, so a move commit with few edits keeps `git log
  --follow` and review diffs readable. Make heavy edits in the next commit.
- **Binary files** can only be staged whole.

## 8. Check that each commit stands alone

**Before committing**, test the staged state by itself:

```bash
git stash push --keep-index --include-untracked -m "verify staged"
git stash list -n 1      # must show "verify staged"; if not, nothing was stashed, so stop here
# run the project's build/test commands here
git reset --hard         # drop the staged copy and anything the build changed in tracked files
git stash pop --index    # bring back the staged and the unstaged state exactly as they were
```

`--keep-index` leaves the staged changes in the working tree and stashes everything else, so
the build sees only the next commit's content.

Don't finish with a plain `git stash pop`. It merges the stashed working tree onto a tree that
already holds the staged part. When a file has staged and unstaged hunks close together, which
is the usual reason to run this check, that merge conflicts and leaves conflict markers in
the file. `git reset --hard` is safe at this point only because the stash holds both the index
and the working tree, so never run it if the stash list check failed. If the pop then refuses
because the build created an untracked file the stash also holds, delete the build's copy and
pop again. A failed pop keeps the stash.

**After committing a series**, replay it and run a check at every commit:

```bash
default=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/main)
base=$(git merge-base "$default" HEAD)       # the branch point, so the base doesn't move
git rebase --exec "make test" --reschedule-failed-exec "$base"   # substitute the real test command
```

Set `default` to the branch you will merge into if that isn't the remote's default branch.
The rebase stops at the first commit where the command fails. Fix that commit while stopped
(amend it), then run `GIT_EDITOR=true git rebase --continue`. `--reschedule-failed-exec` (Git
2.22+) re-runs the failed check on the fixed commit. Without it, git moves on, and the fix is
never tested. When every check passes, the commits keep their SHAs, because rebasing onto the
existing branch point leaves them unchanged. Passing the default branch directly instead of
`$base` would also move the branch onto its latest commit, which is a real rewrite. Fixing a
failing commit does rewrite history, so do that only on unpushed commits or on a branch only
you use.

Find the real build and test commands in the README, CONTRIBUTING, Makefile, `package.json`
scripts, or the CI config. Don't guess at a toolchain.

## 9. Split the last commit (unpushed)

Create the backup branch from section 12 first.

```bash
orig=$(git rev-parse HEAD)                 # remember it; also your way back
git reset HEAD~1                           # undo the commit, keep its changes unstaged
# stage and commit piece by piece using sections 2-6
git log -1 --format=%B "$orig"             # the original message, to reuse or adapt
```

To recover, run `git reset --hard "$orig"`. That restores the original commit and discards
everything made since. Run it only if nothing else uncommitted is in the working tree.

## 10. Split or reword an older commit (unpushed)

Create the backup branch from section 12 first. If the range from the target to `HEAD`
contains merge commits, stop and ask, because this kind of rebase flattens them.

Stop the rebase at the target commit by rewriting the generated todo list through
`GIT_SEQUENCE_EDITOR`, which makes it non-interactive. The pattern accepts both `pick` and the
short `p` that `rebase.abbreviateCommands` produces. `sed -E -i.bak` works with both GNU and
BSD sed.

```bash
full=$(git rev-parse abc1234)
target=$(git rev-parse --short "$full")
GIT_SEQUENCE_EDITOR="sed -E -i.bak 's/^(p|pick) $target/edit $target/'" git rebase -i "$target~1"

# Confirm the rebase really stopped at the target before changing anything:
test -d "$(git rev-parse --git-path rebase-merge)" && [ "$(git rev-parse HEAD)" = "$full" ] \
  && echo "stopped at target" || echo "STOP: not at the target"
```

If the check prints STOP, change nothing. Run `git rebase --abort` if a rebase is still in
progress, then find out why the todo line didn't match: usually a wrong SHA, or the target
isn't in the range.

Once it has stopped there, do one of the following:

- **To split it,** run `git reset HEAD~1`, commit the pieces as in section 9, then run
  `GIT_EDITOR=true git rebase --continue`.
- **To reword only,** run `git commit --amend --only -F -` with a heredoc, then
  `GIT_EDITOR=true git rebase --continue`. `--only` keeps anything staged out of the amended
  commit.

If a conflict appears in a later commit, resolve it, stage the result, and run
`GIT_EDITOR=true git rebase --continue`, or run `git rebase --abort` to put everything back.

To reword the most recent commit, no rebase is needed:
`git commit --amend --only -F - <<'EOF' ... EOF`.

## 11. Fixup commits during review

```bash
git commit --fixup=abc1234                 # records "fixup! <subject of abc1234>"
default=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/main)
base=$(git merge-base "$default" HEAD)     # fold fixups in without moving the branch
git rebase --autosquash "$base"                           # Git 2.44+: works without -i
GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash "$base"  # older Git: accept the todo as generated
```

A `fixup!` commit changes the target's content and keeps the target's message. Some teams
review fixups as they are and autosquash only right before merge. Others squash on merge
anyway, which makes this step unnecessary. Follow the house style. Autosquashing rewrites the
branch, so the rules in SKILL.md's "Amend or new commit" apply before you push the result.

## 12. Safety net

Before any history rewrite (sections 9, 10, and 11), create a backup branch. It costs nothing:

```bash
git branch "backup/before-split-$(date +%Y%m%d%H%M%S)"
```

`git reflog` lists every recent position of `HEAD`, even after a reset or rebase, so a
"lost" commit can almost always be found there. Delete the backup branch once the user is
satisfied with the new history.

## 13. Resolving conflicts when updating a branch

When `git merge`, `git rebase` or `git pull` stops on conflicts, resolve each file for what
it is, then prove the result before going on.

1. **List the conflicted files.** `git diff --name-only --diff-filter=U` prints exactly the
   paths still unresolved; `git status --short` marks them `UU`, `AA`, `DU` and so on.
2. **Know which side is which.** In a merge, "ours" is your branch and "theirs" is the branch
   being merged in. In a rebase it is the other way round: "ours" is the branch you are
   rebasing onto, and "theirs" is your own commit being replayed.
3. **Regenerate lockfiles and generated files; don't hand-merge them.** Resolve the manifest
   (`package.json`, `pyproject.toml`, `Gemfile`) by hand first. Then take the lockfile from
   the branch you are updating onto (`git checkout --theirs -- package-lock.json` in a merge,
   `--ours` in a rebase) and rerun the package manager's own command so your manifest changes
   land on top of it: `npm install` (not `npm ci`, which refuses a lockfile that disagrees
   with the manifest), `pnpm install`, `yarn install`, `bundle install`, `uv lock`, or
   `poetry lock` (Poetry 1.x needs `--no-update` to keep the other pins). Do the same for
   generated clients, compiled assets and snapshots: regenerate them from source.
4. **Resolve source files hunk by hunk.** Never take one side wholesale with
   `git checkout --ours/--theirs` on a source file, or with `-X ours` / `-X theirs` for the
   whole operation: each silently drops the other side's change in every hunk. Keep both
   sides' intent. `git show :1:path`, `:2:path` and `:3:path` print the common ancestor,
   ours and theirs, which is often clearer than the conflict markers.
5. **Prove the result.** Check that no conflict markers remain (`git diff --check` reports
   "leftover conflict marker" lines, and `git diff --cached --check` does the same once the
   files are staged), `git add` each resolved file, and run the tests before
   `git rebase --continue` or the merge commit. A merge with no textual conflict can still
   break the build.
6. **Know the exit.** `git rebase --abort` or `git merge --abort` returns the branch to where
   it was before you started. In a rebase, the same conflict can come back for each replayed
   commit; resolve each one the same way.

Pushing a rebased branch that was already pushed rewrites shared history: ask first, and use
`git push --force-with-lease`.
