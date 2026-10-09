# Git History and Bisect

Read this when the bug is a regression ("this used to work"), when you need to know
why a line of code looks the way it does, or when you are about to run `git bisect`.

The bundled scripts live in this skill's `scripts/` directory. `${CLAUDE_SKILL_DIR}`
in the commands below is not a shell variable: replace it with the skill directory
path shown under "Reference files" in SKILL.md. Run everything else from the
repository (or the bisect worktree).

## Contents
1. Find what changed
2. Ask why a line exists
3. Manual bisect
4. Automated bisect with `git bisect run`
5. Bisecting intermittent bugs and performance regressions
6. Pitfalls that make bisect blame the wrong commit
7. After bisect: confirm the culprit

---

## 1. Find what changed

Start narrow (the files on the failing path), then widen.

```bash
# Commits touching the suspect area since the last known-good date or tag
git log --oneline --since="2 weeks ago" -- path/to/module/
git log --oneline v2.3.0..HEAD -- path/to/module/

# Commits that added or removed a string (the "pickaxe"); good for
# "when did this call / constant / flag appear or disappear?"
git log -p -S'retryCount' -- path/

# Commits whose changed lines match a regex (catches edits that keep the
# string count the same, which -S misses)
git log -p -G'timeout\s*=' -- path/

# Full history of one function, or one line range
git log -L :parse_invoice:src/billing/invoice.py
git log -L 120,160:src/billing/invoice.py

# Which merges (PRs) landed on the main line between two points.
# Drop --merges to also see commits pushed straight to the main line.
git log --oneline --first-parent --merges v2.3.0..v2.4.0

# Everything that differs between a good and a bad build
git diff --stat GOOD BAD
git diff GOOD BAD -- package-lock.json   # or poetry.lock, go.sum, Cargo.lock, Gemfile.lock ...
```

Code is only one of several things that change. Also check deploy history, configuration
and feature-flag changes, dependency or base-image updates, data migrations, and
infrastructure changes for the same time window. A regression with no relevant code
change usually came from one of those.

## 2. Ask why a line exists

Before you change a line, find out what it was protecting. The commit that introduced
it, and the issue or review linked from that commit, often describe a constraint your
fix could break.

```bash
git blame -w -C -C -C -L 120,160 src/billing/invoice.py   # ignore whitespace, follow moved/copied code
git blame --ignore-revs-file .git-blame-ignore-revs path   # skip bulk-format commits, if the repo keeps that file
git show COMMIT                                             # read the full change and its message
```

## 3. Manual bisect

Bisect does a binary search over history, so 1,000 commits take about 10 test steps.
Use it once the candidate window is more than a handful of commits and you have a
reliable pass/fail check.

```bash
git status                      # the working tree must be clean; stash or commit first
git bisect start
git bisect bad                  # current HEAD shows the bug
git bisect good v2.3.0          # a tag or SHA where it did not
# git checks out a midpoint. Build, test, then mark it:
git bisect good                 # or: git bisect bad
git bisect skip                 # this revision cannot be tested (it doesn't build, for example)
# ...repeat until git prints "<sha> is the first bad commit"
git bisect log > bisect.log     # save the session before resetting
git bisect reset                # return to where you started
```

You can pass the endpoints up front, and limit the search to commits touching certain
paths:

```bash
git bisect start BAD GOOD -- src/billing/ tests/billing/
```

A pathspec makes bisect test *only* commits that touch those paths. If the real change
is in a lockfile, configuration, a build script, or vendored code, bisect confidently
names an innocent commit. Include those files in the pathspec, or don't limit paths at
all when dependencies or configuration changed inside the range.

When you are looking for the commit that *fixed* something, or changed any property
other than "broken", use other terms so the prompts read correctly:

```bash
git bisect start --term-old=slow --term-new=fast
git bisect slow v2.3.0
git bisect fast HEAD
```

If you marked one revision wrongly, the result is wrong. Save `git bisect log` to a
file, delete the bad line, then `git bisect reset` and `git bisect replay that-file`.

## 4. Automated bisect with `git bisect run`

`git bisect run CMD ARGS...` runs CMD at each step and reads the verdict from its exit
code:

| Exit code | Meaning |
|---|---|
| 0 | good (old) |
| 1-127, except 125 | bad (new) |
| 125 | cannot test this revision, skip it |
| anything else (128 and up, including deaths by signal) | abort the bisect |

Real test commands don't follow this contract on their own. A test that crashes with
SIGSEGV exits 139 and aborts the run. A runner that exits 125 for its own reasons
silently skips. A build failure looks the same as a real failure. Wrap the check with
the bundled adapter, which turns every outcome into a verdict bisect can use:

```bash
# Keep the check OUTSIDE the repo so every revision runs the same check.
cp tests/test_invoice_regression.py /tmp/repro_test.py

git bisect start HEAD v2.3.0 --
git bisect run "${CLAUDE_SKILL_DIR}/scripts/bisect-check.sh" \
    -b 'pip install -q -e . && find . -name __pycache__ -prune -exec rm -rf {} +' \
    -s 2,3,4,5 -m 'AssertionError: totals row' \
    -- python -B -m pytest -q /tmp/repro_test.py
git bisect log > /tmp/bisect.log
git bisect reset
```

- `-b BUILD`: prepares each revision. If it fails, the revision is skipped, not
  blamed.
- `-n RUNS`: runs the check several times. Any failure marks the revision bad. Use
  this for intermittent bugs (section 5).
- `-s CODES`: test exit codes that mean "couldn't test", which skip the revision
  instead of marking it bad. pytest exits 2 when collection fails (an `ImportError`
  because the copied test imports something that doesn't exist yet at an older
  revision), 3 on an internal error, 4 on a usage error, and 5 when no tests were
  collected. Other runners have their own codes, so check the runner's docs. If the
  bug itself is an import-time failure, leave 2 out and let `-m` match its error text.
- `-m REGEX`: text that only this bug's failure prints, such as its assertion message.
  A failing run that doesn't print it is skipped rather than marked bad, because a
  different failure at an old revision is not evidence of this bug. Without `-m`,
  any non-zero exit counts as the bug.
- `-t SECS`: kills a run that takes longer and counts it as a failure. Set it well
  above a normal run, unless the hang is the bug you are bisecting.

The adapter also aborts the whole bisect, instead of returning a verdict, on a usage
error or when the test command can't be run (exit 126 or 127, such as a mistyped
path). Without that, every revision would be marked bad and bisect would name the
first commit after GOOD.

Without the adapter, the minimal form is:

```bash
git bisect run sh -c 'make || exit 125; ./run-repro.sh'
```

Why the check must live outside the repository: at older revisions a new test file
doesn't exist, or exists in an older form. The run then reports "bad" because the
file is missing, not because the bug is present, and bisect converges on the commit
that added the test. Copy the test or repro script to a temporary location, and make
it import only code that exists across the whole range.

## 5. Bisecting intermittent bugs and performance regressions

**Intermittent.** A single passing run doesn't prove a revision is good. Measure the
failure rate at the bad endpoint first, with
`"${CLAUDE_SKILL_DIR}/scripts/repeat-run.sh"`, and use its conservative (lower-bound)
rate as p. With n runs per step, a bad revision passes every run, and is wrongly
marked good, with probability (1-p)^n. That error compounds: it can happen at every
bad midpoint across the roughly log2(commits) steps, and a single false "good" sends
the search into the wrong half for good. Choose n so that
log2(commits) × (1-p)^n ≤ 0.05. For p = 0.2 over about 400 commits (9 steps), that is
n ≈ 24, not the 15 that a per-step view suggests. For anything rarer, first make the
failure more frequent (see `intermittent-and-concurrency.md`).

```bash
git bisect run "${CLAUDE_SKILL_DIR}/scripts/bisect-check.sh" -n 24 -t 600 -- /tmp/stress-repro.sh
```

When bisect finishes, the culprit's parent must pass several times n runs before you
accept the result (section 7).

**Performance.** Write a check that measures several times, takes the median, and
compares it against a threshold set midway between the known-good and known-bad
numbers. Exit 0 for fast and 1 for slow. Confirm the gap between good and bad is
much larger than run-to-run noise before trusting the result. Name the terms so the
log reads naturally: `git bisect start --term-old=fast --term-new=slow`, then
`git bisect fast GOOD` and `git bisect slow BAD`. `performance-regressions.md`
section 5 has a ready-to-use check script, and section 1 covers measurement hygiene.

## 6. Pitfalls that make bisect blame the wrong commit

- **Stale build outputs.** Untracked caches and artifacts survive checkouts:
  compiled objects, `build/`, `target/`, `dist/`, `node_modules/`, bytecode caches.
  Old revisions can then run new code, or new revisions old code. Python's default
  bytecode cache checks only the source's mtime (whole seconds) and its size, so a
  quick checkout that changes a file without changing its size can serve stale code.
  `python -B` alone doesn't help: it stops Python *writing* `.pyc` files but still
  loads existing ones. Delete the `__pycache__` directories in the build step and then
  run with `-B` (as the example in section 4 does), or point `PYTHONPYCACHEPREFIX` at
  a fresh temporary directory for each revision. Rebuild from clean when in doubt.
- **Dependencies differ per revision.** If the lockfile changes inside the range,
  reinstall in the build step (`npm ci`, `pip install -r ...`, `bundle install`, and
  so on). Otherwise you are testing every revision against one dependency set.
- **Schema or data drift.** An old revision might not run against a database migrated
  by a newer one. Use a fresh, disposable database per step, or skip those revisions.
- **Dirty or shared working tree.** Bisect checks out revisions in place. Run it in a
  separate worktree in a fresh directory (`dir="$(mktemp -d)/bisect-wt" && git worktree add --detach "$dir" HEAD`)
  so your own work, and any running dev server, stay untouched, and two sessions never
  share one path.
- **Endpoints not verified.** Before starting, run the exact check once at GOOD (it
  must exit 0) and once at BAD (it must exit 1), inside the bisect worktree after
  installing dependencies there. A wrong endpoint invalidates every step. If BAD
  passes in the clean worktree, something local (uncommitted changes, an untracked
  `.env`, local data, build outputs) is part of the bug. Find it before bisecting.
- **Merge-heavy history.** With `git bisect start --first-parent BAD GOOD`, bisect
  follows only the main line and reports the merge (the PR) that introduced the
  change. That avoids broken
  intermediate commits on feature branches. Bisect inside that branch afterwards if
  you need the exact commit.
- **Too many skips.** If many adjacent revisions can't be tested, bisect ends with
  "the first bad commit could be any of: ...". Narrow it by reading those few diffs,
  or apply a minimal build fix inside the check script and revert it after each step.

## 7. After bisect: confirm the culprit

1. Check out the culprit's parent and run the check (it should pass). Check out the
   culprit and run it again (it should fail). For an intermittent bug, the parent must
   pass several times the per-step run count (section 5), because one unlucky
   all-pass run anywhere in the search moves the answer.
2. Read the culprit's diff with the causal chain in mind. Bisect finds where the
   behavior *changed*, which isn't always where the defect *lives*. A commit that only
   changes timing, ordering, or data shape can expose a latent bug elsewhere. Root
   cause still needs the proof described in the main workflow.
3. Optionally, in a scratch worktree, run `git revert --no-commit CULPRIT` on the
   current HEAD and run the check. If the bug disappears, you have a toggle
   experiment. Discard it with `git reset --hard` (scratch worktree only) before you
   continue. The revert is evidence, not automatically the fix.
