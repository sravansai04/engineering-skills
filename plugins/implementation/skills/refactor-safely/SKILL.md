---
name: refactor-safely
description: "Restructures code without changing behavior: pins behavior with tests, finds every usage including string and reflective ones, moves in small verified steps, and runs dependency and framework upgrades the same way. Use for \"refactor this\", \"split this class\", \"rename this everywhere\", \"delete dead code\", \"upgrade X to vN\". Not for trimming just-written code (simplify-code), new behavior or bug fixes (tdd, debug-root-cause), speed (performance-review), or renaming a column (db-migration-safety)."
---

# Refactor Safely

Refactoring changes the structure of code while keeping its observable behavior identical. The discipline that makes it safe is easy to state and easy to skip: have tests that would notice a behavior change, change one small thing, prove nothing changed, commit, repeat. The rest of this skill keeps that loop honest when the code is untested, widely used, reached through strings and reflection, or too big to change in one go.

"Observable behavior" means more than return values. It includes side effects (writes, messages, files, network calls), the errors raised, and anything another party depends on: wire formats, persisted data, public signatures, log lines that alerts match on, metric names. Private helper names, file layout and internal call structure are what you are free to change.

If the skill's arguments (in Claude Code, typed arguments appear after ARGUMENTS: at the end of this skill) or the user's request name a target and a goal, start there. Ask what to refactor and why only when neither does.

## Workflow

### 1. Frame the refactor before touching code

- **State the goal and the stop condition in one sentence.** "Move the pricing rules out of `OrderController` into a `PricingPolicy` so the discount feature touches one place" is a goal. "Clean up orders" is not, and it will sprawl.
- **Name the smell** behind it (long function, duplication, feature envy, repeated type switches, a misleading name). The smell index in `references/refactoring-catalog.md` maps each smell to its refactorings.
- **Check "When not to refactor" below.** If an item applies, say so, then stop or narrow the scope.
- **Scope it so it can be reviewed.** One intent per PR. Keep mechanical changes (a tool-driven rename across 80 files) apart from judgment changes (reshaping a class): a reviewer verifies the first by re-running the tool, but has to read the second line by line. Split an oversized diff by step or by batch of call sites (step 7).
- **Before a wide mechanical change, check open PRs on the same paths**, since it will conflict with all of them. Land it quickly at an agreed time, and publish the codemod command so other branches can re-run it instead of resolving conflicts by hand.

### 2. Discover how this project builds and tests

Don't assume a stack. CI config (`.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile` and the like) is the authority on what must pass. Task runners, manifests, README and CONTRIBUTING show how to run it locally. Sort what you find into a fast loop (compile or typecheck plus the touched module's tests), the full suite, and the static checks.

Record a baseline from a clean tree (`git status`): run the full suite and static checks once, and note pass, fail and skip counts and known flaky tests. **If anything fails, look at what.** If the failures touch the code you're about to change, stop and report: you can't tell your breakage from what was already broken. If they're pre-existing and unrelated, record the exact failing test IDs, tell the user, and make "the same failing set and no new failures" the bar in step 8.

### 3. Establish the safety net

The safety net is whatever would fail if you changed behavior by accident. Confirm it covers the specific code you will touch. "The project has tests" is not enough.

- **Test at a stable boundary** above what you'll restructure (the public entry point or module API), not on units you're about to split, merge or inline. Those tests break with the structure and stop guarding behavior.
- **Measure line and branch coverage** of the touched module (per-stack commands in `references/legacy-safety-net.md`). An uncovered branch in code you're restructuring is where silent regressions hide.
- **Probe that the tests assert something.** Break the target on purpose (flip a condition, return a constant), confirm the fast loop fails, then revert. Mutation testing does the same probe systematically.
- **If the net is thin, add characterization tests** that pin what the code does today, bugs included; a golden master covers a large untested surface fastest (`references/legacy-safety-net.md`).
- **Commit the new tests on their own**, passing against the unmodified code, which proves they describe current behavior rather than the new structure.

If characterizing turns up a bug, pin the current behavior, comment it with an issue link, and fix it in a separate change after the refactor; fixing it now turns the test into a moving target. **The exception is a security vulnerability or active data loss or corruption.** Stop and report it through the security or incident process, not a public issue or a descriptive comment. Fix it first in its own change, then refactor on top. Never commit a test that documents an unfixed exploit where you don't control who reads the repo.

### 4. Find every usage before you rename, move, change a signature, or delete

Compilers and find-references see static references. Production breaks on the ones they can't see.

1. **Start with semantic tools:** find-references, implementations and call hierarchy. They respect scope, shadowing and overloads. In a terminal, use the command-line equivalents listed in `references/finding-all-usages.md` rather than dropping to grep.
2. **Then text-search for what the type system can't see:** every spelling (`userId`, `user_id`, `UserId`, `USER_ID`, `user-id`) and the fully qualified path. Ripgrep skips dotfiles and gitignored files by default, where CI config, manifests and generated clients live: `--hidden` brings back only dotfiles, `-uu` brings back both.
3. **Walk the hidden-reference checklist** in the same file (reflection, string keys, config, templates, serialized forms, string-path mocks, observability names, other repos) before any rename, move or delete that isn't file-local.
4. **Classify the symbol's reach:** *private* (file or class), *internal* (this repo), or *published* (other repos, other teams, external clients, persisted data). Published symbols need expand-contract and a deprecation period (step 7), because you can't update callers you can't see.
5. **Treat "no references found" as a hypothesis when deleting.** Dead-code tools miss dynamic use. When being wrong is expensive, instrument the path and watch production before you delete it.

### 5. Change in small, verified steps

Make each step one named refactoring from `references/refactoring-catalog.md`, then:

1. **Apply it with a tool when one exists** (IDE or language-server refactorings, or a codemod for many call sites); tools update imports and catch conflicts hand edits miss. **Review every tool-produced diff.** In dynamically typed code a tool rename is a best guess that can miss references made by name and catch unrelated same-named attributes. Still run the step 4 text search, and leave rename-in-strings-and-comments off unless you check each hit.
2. **Run the fast loop.**
3. **If it's green, commit or checkpoint.** Small commits are bisectable and read as a story.
4. **If it's red, revert the step instead of debugging forward**, and redo it more carefully or as two smaller steps (`git stash push --include-untracked -m "failed step: ..."` keeps the attempt). A failure you can't explain is a behavior dependency you didn't know about; investigate it with `implementation:debug-root-cause` first.
5. **Run the full suite at milestones:** every few steps, and before pushing.

While stepping:

- **Leave assertions alone.** A test that needs a new expected value means behavior changed; never weaken an assertion or change an expected value. Two kinds of test edit are legitimate, and the report lists both:
  - *Structural:* a renamed symbol, a moved import, a mock patched at its new location.
  - *Retargeted or removed:* tests of a unit the refactor inlines, merges or removes, changed only after a break-and-revert or mutation probe shows the boundary tests catch the same behaviors. Do it in its own commit and name the covering test for each.
- **Don't update snapshot or golden files**; a snapshot diff is the net doing its job. Run snapshot suites in CI mode (`jest --ci`, or `CI=true` for Jest and Vitest) so a missing snapshot fails instead of being written. A "written" or "obsolete" count means a renamed or moved test left its snapshot behind.
- **Check each step against `references/equivalence-traps.md`.** Skim it once per refactor, and recheck any step that crosses a function, thread, transaction or module boundary or touches serialized output.

### 6. Keep refactoring and behavior changes apart

- **Check how the repo merges** (repository settings, CONTRIBUTING, recent history on the default branch). Squash merge collapses a PR into one commit, so the PR becomes the unit of separation: characterization tests, mechanical changes, judgment refactors and any behavior change each get their own PR, stacked if needed. Merge commits and rebase merging keep separate commits intact.
- **Never mix a structural and a behavior change in one commit**, and prefer separate PRs. A pure refactor is approved by checking the tests are unchanged and green, a behavior change by reading a small diff. Mixed, the reviewer re-derives everything, and reverting one undoes the other.
- **For feature work, land the preparatory refactor first**, so the feature PR on top is small and obvious.
- **Record bugs you find mid-refactor** in an issue (except security and data-loss bugs; see step 3). Fix them after the refactor lands, with a test that fails before the fix.
- **Move or rename a file with no content edits in the same commit** (or PR, under squash merge). Heavy edits push a move below git's rename-similarity threshold, so the diff becomes a whole-file delete and add, and `git log --follow` and blame lose the history. Point reviewers of extract and move steps at `git diff --color-moved=dimmed-zebra --color-moved-ws=ignore-all-space`.
- **Give tool-driven formatting or reordering its own commit or PR.** After it merges, add its SHA as it exists on the default branch (a PR-branch SHA is gone after a squash or rebase) to `.git-blame-ignore-revs`. GitHub's blame view reads that file automatically; local blame needs `git config blame.ignoreRevsFile .git-blame-ignore-revs`.
- **When separation really is impossible** (an atomic swap has to ship with a fix), keep separate commits if they will survive the merge, and say in the PR description which part changes behavior.
- **Label refactor commits per team convention**, for example `refactor:` under Conventional Commits. `workflow:commit-message` and `workflow:pr-description` cover the wording.

### 7. Large, cross-cutting, or published changes

When the change won't fit in one reviewable PR, or touches callers you don't control, keep the system working at every intermediate commit:

| Situation | Strategy |
|---|---|
| A function, type or field with many callers | **Parallel change (expand-contract):** add the new form, make the old delegate to it, migrate callers in batches, delete the old |
| An internal component or library | **Branch by abstraction:** add a seam, put old and then new implementations behind it, switch, remove the old |
| A subsystem or service | **Strangler fig:** intercept at a boundary (router, facade, event stream), move slices across, retire the legacy side |
| A risky computation | **Parallel run:** execute both, serve the old result, log mismatches, switch once every diff is explained |
| A public API, SDK, CLI flag or wire format | **Deprecate before delete:** mark, warn, document the replacement, measure use, remove in a major version |

File the contract step as a tracked follow-up on the day you expand. An expand that never contracts leaves two paths to maintain forever. Mechanics, deprecation markers, `Deprecation` and `Sunset` headers, codemods and lint bans are in `references/large-refactors.md`.

Hand off the adjacent concerns:

- **Persisted names go to `data-api:db-migration-safety`.** Rename the code symbol here and pin the stored column name and JSON key with explicit mappings (an ORM column-name attribute, a serializer property name), so nothing outside the process changes. The column rename is its own migration; without that skill, add the new column, dual-write, backfill, switch reads, and drop the old one in a later release.
- **Wire contracts (HTTP, GraphQL, event fields) go to `data-api:api-design`.** Without it, keep the old field beside the new one and announce removal with `Deprecation` and `Sunset` headers and a changelog entry.

### 8. Verify and report

1. Run the full suite, typecheck, lint and build, and compare with the baseline: the same passes plus your new tests, the same pre-existing failures and no new ones, no new warnings or skips.
2. For a published package, run an API-diff tool against the last release and expect zero non-additive changes. Tools per ecosystem are in `references/equivalence-traps.md` ("Compatibility surfaces").
3. Run `git diff --stat` from the starting commit. Every file should trace to a step. Lockfiles, generated output or snapshots need a reason or a revert.
4. Confirm test changes are additive, structural, or retargeted with a named covering test.
5. Run `implementation:verify-before-done`, then report in the format below.

## Dependency and framework upgrades

An upgrade is a refactor whose behavior change arrives in someone else's code, so run the same loop (baseline, safety net, small steps, verify) with these additions:

- **Scope the breaking changes between the pinned and target versions with `implementation:docs-lookup`.** Read every release between the two versions, not only the target's: changelogs, migration guides, and deprecation notices, noting removed APIs, changed defaults, a new minimum runtime, and peer-dependency changes.
- **Prefer the maintainers' upgrade tooling** over hand edits: a framework's own upgrade command (for example `ng update`), OpenRewrite recipes for Java and Spring, `go fix`, or the codemods a migration guide publishes. Review their diffs like any tool-produced change.
- **Give the upgrade its own PR,** with no feature or refactor riding along, so a regression bisects to it and it can be reverted alone.
- **Step through intermediate majors** (2 to 3, then 3 to 4), clearing each version's deprecation warnings before the next. A jump over several majors hides which change broke what.
- **Pin and inspect.** Pin the exact version in the manifest, update the lockfile with the project's package manager, and read the lockfile diff for new transitive packages and their licenses (route supply-chain concerns to `review-suite:secure-code-review`).
- **Verify past the unit tests.** Run the full suite and build, then exercise at least one real consumer (start the app, run a key flow, import the package from a scratch project): upgrades break at runtime, in config loading, reflection, and serialization, where mocked unit tests don't look. New deprecation warnings become follow-ups.
- **Keep it revertible.** If the new version changes a persisted or wire format, ship that change separately and plan it with `data-api:db-migration-safety` or `data-api:api-design`, so rolling back the upgrade doesn't strand data.

## When not to refactor

- **No safety net and no time to build one.** Make the minimal change you came for and record the debt (options in `references/legacy-safety-net.md`, "When you can't build a net").
- **The code is about to be deleted or replaced.**
- **You're in an incident or hotfix.** Ship the smallest fix, then refactor afterwards with tests.
- **You don't yet understand what the code does.** Characterize it first, or the new structure bakes in the misunderstanding.
- **The code is stable and outside current work.** Refactoring pays off where code is about to change.
- **It's really a redesign or a rewrite of behavior.** Call it that and plan it with `implementation:plan-feature`.
- **It's generated code.** Change the generator or its input instead.
- **It's a hot path with no benchmark.** Measure before and after, or leave it alone (`review-suite:performance-review`).
- **A release freeze is close**, unless the team has agreed to it.

## Report format

```markdown
## Refactor: [one-line goal]

**Behavior change:** none intended.
**Motivation:** [smell(s)], and what this enables.
**Scope:** in: ... / explicitly out: ...

### Safety net
- Existing tests over the touched code: [suites, and the boundary they test at]; coverage before: [lines %, branches %]
- Added: [N] characterization tests in [path] ([sha]), passing on unmodified code
- Strength check: [manual break-and-revert result, or mutation score]

### Steps (one commit each; one PR each if the repo squash-merges)
1. `[sha]` Extract Function `computeTax` from `checkout()` (IDE extract)
2. `[sha]` ...

### Usage search (renames, moves, signature changes, deletes)
- Semantic references updated: [N], via [tool]
- Text patterns searched: `[patterns]`; dynamic or string references found: [list or none]
- Reach: private / internal / published; deprecation path if published: [...]

### Verification
- Baseline: [passed / failed / skipped, plus pre-existing failing test IDs]. After: [passed / failed / skipped] (+[N] new tests; same failing set, no new failures)
- Typecheck, lint, build: [clean / details]
- API diff against last release: [no non-additive changes / not a published package]
- Snapshot and golden files: unchanged; snapshots written: 0

**Test edits:** additive only, or the structural edits: [list]
**Tests retargeted or removed:** [test -> covering boundary test, probe result], or none
**Found, not fixed:** [bugs pinned by tests, with issue links; never describe an unfixed security issue here]
**Follow-ups:** [contract step once consumers migrate, deprecated symbol removal in vN, ...]
```

## Example

> "`processOrder` is 300 lines. Clean it up before I add gift cards."

1. Baseline: the suite is green, but coverage shows the refund branch of `processOrder` never runs.
2. Add a golden-master test that feeds 40 order fixtures through `processOrder` and records the return value plus every call to the payment and inventory fakes. Commit it alone: `test: characterize processOrder`.
3. Use the IDE to Extract Function four times (validate, price, apply discounts, persist), running tests and committing after each.
4. Replace the five-branch `switch (paymentType)` with a map of handler objects, then commit.
5. Stop and report. Gift cards are a separate PR, and now amount to one new handler.

The anti-example is a single commit, "refactor processOrder + gift cards", that also changes discount rounding. The reviewer can't tell which lines are meant to change behavior.

## Other common mistakes

- Leaning on tests that mock the very code being refactored. They stay green no matter what the real code does.
- Calling a big-bang rewrite on a long-lived branch a refactor. It rots against main; prefer trunk-based expand-contract.
- Letting dependency bumps, reformatting of untouched files, or "while I'm in here" fixes ride along in the refactor PR. Write them down for later.

## Related skills

- `implementation:tdd` for new behavior, and `implementation:debug-root-cause` for unexplained failures and slowdowns.
- `implementation:verify-before-done` for the final check, and `review-suite:pr-review` for review.
- `implementation:simplify-code` to trim code that was just written, rather than restructure existing code.
- `implementation:docs-lookup` to list what changed between the version you pin and the one you are upgrading to.
- `review-suite:performance-review` when the goal is speed rather than structure.
- `data-api:db-migration-safety` and `data-api:api-design` for persisted names and wire contracts (step 7).

Skills are named here as `plugin:skill`; an agent that lists skills by bare name knows each one by the part after the colon (`review-suite:pr-review` is `pr-review`). If a skill named here isn't installed, give the short version inline and list the deeper pass as a follow-up.

## Reference files

- `references/refactoring-catalog.md`: smell index and about 50 named refactorings with mechanics and traps. Read when choosing the next step.
- `references/finding-all-usages.md`: command-line semantic tools, search commands, the hidden-reference checklist, per-language dynamic access, proving code dead. Read before any non-local rename, move, signature change or delete.
- `references/legacy-safety-net.md`: characterization and golden-master tests, stable output, seams, coverage and mutation commands. Read when the net is thin.
- `references/equivalence-traps.md`: how "behavior-preserving" edits change behavior, and API-diff tools. Skim once per refactor.
- `references/large-refactors.md`: parallel change, branch by abstraction, strangler fig, parallel run, codemods, deprecation, lint bans. Read when the change spans PRs or repos, or touches a published interface.
