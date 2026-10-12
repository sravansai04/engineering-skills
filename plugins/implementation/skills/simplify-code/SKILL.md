---
name: simplify-code
description: "Shrinks just-written code, the branch diff or a named file, without changing behavior: deletes dead code, duplicate helpers, needless abstraction, deep nesting and generated bloat in test-gated batches, and flags any edit a caller could notice. Use for \"simplify this\", \"clean up what you just wrote\", \"de-slop this diff\", \"tighten it up before review\". Not for restructuring or public API changes (refactor-safely), bug hunting (pr-review), or speed (performance-review)."
allowed-tools: Bash(git diff:*), Bash(git grep:*), Bash(git log:*), Bash(git show:*), Bash(git ls-files:*), Bash(git status:*), Bash(git symbolic-ref:*), Bash(git merge-base:*), Read, Grep, Glob
---

# Simplify Code

Make recently written code smaller and plainer without changing what it does.
The deliverable is a diff a reviewer can trust: every edit is either provably
behavior-identical or explicitly flagged as a behavior change, the tests were
green before and after every batch, and the report says what was removed, why
that was safe, and what was left alone on purpose.

Fresh code, whether typed or generated, carries scaffolding the author needed
while thinking: checks for states that cannot happen, wrappers added "in case",
helpers that duplicate ones the codebase already has. Each extra line is
something the next reader must understand and the next change must preserve.
But a cleanup that silently changes behavior is worse than the bloat it
removed, so this skill trades a little speed for proof.

The scope is the skill's arguments
(in Claude Code, typed arguments appear after ARGUMENTS: at the end of this skill)
when they name a path or a git range. When none were given (as when this skill
loads on its own), take the scope from the user's message, and fall back to the
current branch diff (step 2).

## Ground rules

1. **Behavior is frozen.** Behavior is everything a caller, user, or operator
   can observe: return values, which errors escape (type, and message when
   something parses or displays it), side effects and their order, I/O,
   what other threads or callers can see of shared state, logs and metrics
   that alerts or audits consume, the public surface (exported names,
   signatures, serialized field names, CLI flags, config keys), and
   complexity class. Full checklist and the classic equivalence traps:
   [references/behavior-preservation.md](references/behavior-preservation.md).
2. **Green before, green after every batch.** For tier 0 and 1 edits, a red
   test means the edit was not equivalent: revert it. Never edit an assertion
   to make such an edit pass. Delete a test only when it exercises code you
   removed as dead, and say so. The single exception is an authorized tier 2
   change whose old behavior a test pins (generated tests often assert the
   bloat itself, such as "returns [] on error"): update that test in its own
   batch and quote the old and new assertion under Behavior changes.
3. **Stay in scope.** Touch the changed hunks and the code they directly lean
   on. Older mess nearby goes in the report under "Noticed outside scope".
   Unrequested edits to stable code inflate the review and carry risk nobody
   asked for.
4. **The codebase's style wins.** Before editing, skim two or three
   neighboring files for local idioms: how errors are handled, early return
   versus single exit, naming verbs (`get`/`fetch`/`load`), comment density,
   how optional values are expressed. Simplify toward those, not toward your
   own taste.
5. **Prefer deleting to adding.** A batch that adds net lines needs a reason:
   a guard clause that removes a nesting level, or a clever construct
   rewritten as plain code a reader no longer has to decode. Do not introduce
   a new abstraction unless it replaces two or more existing ones.
6. **One kind of change per batch.** Homogeneous batches make a failure easy
   to localize and the final diff easy to review by kind.
7. **Contracts change only with informed confirmation.** Anything consumable
   outside the scope (an exported symbol of a published package, a signature
   other modules call, a serialized name, a CLI flag, a config key) is
   tier 3. A bare "just delete it" is not enough, because the person asking
   may not know the symbol is public. First say exactly what makes it public
   and that a search inside this repository cannot rule out outside callers.
   Then either hand off to `implementation:refactor-safely` (deprecate
   before delete), or apply the change only after the user confirms in a
   reply to that explanation.
8. **Stop at taste.** When the remaining ideas rearrange code without removing
   lines, branches, nesting, symbols, indirection, or a construct a reader
   must decode (nested ternary, bit trick, spread-in-reduce, implicit
   coercion), you are done.

Scale the ceremony to the diff. For a 30-line change, keep the ledger in your
head and run the tests before and after. For a 1,000-line branch, write the
ledger down and batch strictly. When another workflow invokes this skill
non-interactively (for example `implementation:build-feature` running a
cleanup pass before its review), apply tiers 0 and 1 and list everything else.

## Workflow

### 1. Confirm the request is a cleanup

This skill does subtractive cleanup in place on code that was just written or
generated: delete, inline, flatten, reuse. Route anything else before you
start, because each of these needs a different safety net:

| Situation | Use |
|---|---|
| You want bugs, risks, or design flaws found | `review-suite:pr-review` |
| The cleanup means extracting, splitting, moving, or renaming established code, deleting a long-lived module, or changing anything public | `implementation:refactor-safely` |
| The code is slow or allocates too much | `review-suite:performance-review` |
| Tests are already failing | `implementation:debug-root-cause` or `workflow:ci-failure-triage` first |

If you find a bug while simplifying, do not fix it here. A fix is a behavior
change, and burying it in a cleanup diff hides it from review. List it in the
report instead.

### 2. Fix the scope

If this session wrote the code, the default scope is this session's edits:
`git diff HEAD` plus the new untracked files it created, plus any commits it
made. "Simplify what you wrote" means that, not days of other work on the
same branch. Report the size of the full branch diff, and widen to it only if
the user says so.

Otherwise (the session made no edits) the default scope is everything the
current branch changed, committed or not:

```bash
git symbolic-ref --short refs/remotes/origin/HEAD   # prints the default branch, e.g. origin/main
git diff --merge-base origin/main --stat            # branch commits + uncommitted edits, per file
git diff --merge-base origin/main                   # the hunks themselves
git ls-files --others --exclude-standard            # new files git is not tracking yet
```

Substitute whatever the first command prints. If it fails (no remote default
set), use the branch the work will merge into. On the default branch itself
with only uncommitted work, `git diff HEAD` is the scope.

A path or range from the skill's arguments or the user's message replaces
this default. For a large path, rank functions by complexity (see
[references/detection-tooling.md](references/detection-tooling.md)) and start
with the worst few.

Leave out generated files (an `@generated` or `DO NOT EDIT` header, or
`linguist-generated` in `.gitattributes`), vendored code, lockfiles,
snapshots and golden files, minified assets, and database migrations that may
already have run anywhere (editing one does not re-run it; see
`data-api:db-migration-safety`). If the scope spans several modules or more
than about a thousand changed lines, split it and do one module per pass.

### 3. Get a green baseline and a checkpoint

1. Find how the project verifies itself: CI workflow files, Makefile or task
   runner, package scripts, CONTRIBUTING. Run the tests, linter, and type
   checker that cover the scope. Record the exact commands and results; you
   will rerun the same commands at the end. Run the scoped tests twice, or
   check CI for tests marked flaky or quarantined, and record any test whose
   result flips. A flaky test cannot judge a batch.
2. If anything is red before you start, stop and report, and point to
   `implementation:debug-root-cause` or `workflow:ci-failure-triage`. A
   pre-existing failure makes "still green" meaningless, so do not deselect
   or skip the red test to get a baseline.
3. Set a checkpoint before writing anything, tests included, so each batch
   can be rolled back and the total measured:

   ```bash
   git diff --cached --quiet && echo "index clean"   # if not clean, ask before using the index
   git add -- <scope paths>                          # pre-simplification state now lives in the index
   git stash create                                  # prints a snapshot commit id; changes nothing
   ```

   Note the printed id (call it SNAP) and reuse it literally; shell variables
   may not survive between tool calls. If it prints nothing, there were no
   local changes and SNAP is `HEAD`. From now on `git diff` shows only your
   edits. After a green batch, `git add -- <files>` advances the checkpoint;
   after a red one, `git restore -- <files>` returns to the last green
   state. Tell the user their work is staged (`git restore --staged <paths>`
   undoes it). If they prefer commits, one commit per batch works as well,
   but do not commit without their go-ahead. No git, or a carefully staged
   index you must not disturb:
   [references/behavior-preservation.md](references/behavior-preservation.md#checkpointing).
4. Check that the code you plan to touch is actually executed by a test. A
   passing suite proves nothing about lines it never runs. For uncovered
   code, write characterization tests as batch 0 (see `implementation:tdd` and
   [references/behavior-preservation.md](references/behavior-preservation.md#characterization-test)):
   run them green against the unchanged code, then stage them. They appear
   in the report under "Tests added". Otherwise limit yourself to tier 0
   edits there. Coverage commands are in
   [references/behavior-preservation.md](references/behavior-preservation.md#coverage-commands).

### 4. Inventory before you cut

Read every changed function in full, plus its callers and the code it calls.
Then:

- Run the cheap detectors for unused symbols, duplication, complexity, and
  redundant casts, conditions, and handlers
  ([references/detection-tooling.md](references/detection-tooling.md)). Their
  output is leads, not verdicts.
- For every new helper or hand-written routine in the diff, look for an
  existing equivalent before keeping it: in the codebase (name fragments,
  distinctive literals, similar signatures), the standard library, and the
  dependencies already declared. Re-implemented grouping, chunking, retry,
  debounce, deep equality, case conversion, and date arithmetic are the usual
  finds.

  ```bash
  git grep -n -i -E 'def (chunk|batch|group_?by)' -- '*.py'
  git grep -n -i -E '(retry|backoff|debounce)[A-Za-z]*\(' -- '*.ts' '*.js'
  ```

  Reuse only what the scope can already import: the same package, its
  declared dependencies, or a shared library's public API. An equivalent in
  another module's internals or under a test-support tree would add a
  dependency edge or an import cycle; keep the duplicate and list it under
  "Noticed outside scope" as a candidate to promote to shared code.
- Prove "unused" before deleting anything that is not file-local. String-built
  references, reflection, DI and route registration, serialization, public
  exports, and imports kept for their side effects all hide from a plain
  search; the recipe is in
  [references/detection-tooling.md](references/detection-tooling.md#proving-something-is-unused).
- Mark every candidate that sits next to shared state: a lock, an `await` or
  `yield`, a transaction, or a collection that is returned, stored, or handed
  to another thread or task. A check or read repeated across one of those is
  usually load-bearing, and a defensive copy usually is too. Single-threaded
  tests rarely exercise interleavings, so these edits are tier 2 at minimum
  and must be justified by reasoning about who else can observe the state.
- Walk the target catalog below against each changed function.

Give every candidate a risk tier, and when torn between two tiers, take the
higher one:

| Tier | Meaning | Examples | Action |
|---|---|---|---|
| 0, identical by construction | Local; a compiler or linter can confirm it | unused local whose initializer has no side effect; unused import where imports are compile-time only (Java, C#, Rust `use`, TypeScript with default import elision); `else` after `return`; comment restating the next line; branch on a constant with one definition in source that no build configuration overrides | Apply |
| 1, identical given a checked fact | Safe because of an invariant you verified and can cite | null check on a value the type checker proves non-null (strict checking runs in CI over every caller, and no `any`, untyped, or deserialized path reaches it); a catch that only rethrows and is the sole handler on its `try` (or every handler rethrows unchanged); an unused Python, Ruby, or plain JavaScript import whose module registers or patches nothing and is not re-exported; wrapper with one caller; duplicate replaced by a helper whose edge cases you compared | Apply; cite the fact |
| 2, observable at the edges | Some input, failure, operator, or concurrent caller would notice | removing a catch that swallowed errors; dropping a fallback default; deleting log lines; reordering side effects; removing a re-check or re-read across a lock, `await`, or transaction; removing a defensive copy; deleting a branch on a build-configured constant | Propose. Apply only if the code is new in this diff and nothing outside it depends on it yet, or the user asked for this cleanup; then list it under Behavior changes |
| 3, contract change | Consumable outside the scope | exported symbol of a published package, signature, wire or serialized format, config key, CLI flag, schema | Do not apply without informed confirmation (rule 7); recommend `implementation:refactor-safely` or `data-api:api-design` |

A ledger entry should carry its evidence, for example:
`T1 src/billing/invoice.ts:88 - formatAmount() duplicates shared formatMoney(); compared: both round half-even, same symbol placement, both throw on NaN - apply`.

### 5. Apply in batches, in this order

1. **Dead code**: unused imports, variables, private functions, parameters of
   private functions, unreachable branches, commented-out code.
2. **Defensive and generated bloat**: swallowed errors, log noise,
   impossible-state checks, repeated validation, gratuitous casts, needless
   fallbacks.
3. **Duplication**: call the existing helper; merge copies inside the diff.
4. **Needless abstraction**: inline pass-through wrappers, collapse
   single-implementation interfaces, remove knobs that never vary.
5. **Control flow**: guard clauses, early return or continue, plain code in
   place of clever code.
6. **Comments and naming**: delete narration, keep the why, align new names
   with local conventions.

The order runs from safest and most mechanical to most judgment-heavy, and
each step shrinks what the next has to read: stripping bloat often reveals
that two blocks were duplicates or that a wrapper now does nothing. Names come
last because they should describe the final shape.

For each batch: make the edits of one kind, then run the fastest checks that
cover them (type check, lint, tests for the touched files).

- **Green**: advance the checkpoint.
- **Red**: first rerun only the failing tests two or three times without
  changing anything. If a result flips, the test is flaky: record it for the
  report, judge the batch on the remaining checks, and do not bisect against
  it. If it fails consistently, restore the batch, re-apply its edits one at
  a time to find the culprit, and move that one to "left alone" with the
  reason.

Never fix forward by adding code or changing tests (rule 2 has the single
exception). After deletions, rerun the unused-code detector, since removing
one dead function often orphans its helpers. After swapping in an existing
helper, run the project's import-cycle or module-boundary check if it has
one.

### 6. Stop

Stop when any of these holds:

- The remaining candidates only rearrange code: no fewer lines, branches,
  nesting levels, symbols, or indirections, and no construct a reader must
  decode goes away.
- Justifying an edit would take longer than reading the code it replaces.
- The next edit is tier 2 or 3 and you are not authorized to make it.
- The next edit is outside scope.

Do not reformat by hand. Run the project's formatter only on files you
touched, and only if those files were formatter-clean at baseline (check
with its check mode, such as `prettier --check`, `ruff format --check`, or
`gofmt -l`). Otherwise format just your own hunks, or leave formatting alone
and say so in the report.

### 7. Verify and report

- Rerun the full baseline commands, same commands, same environment
  (`implementation:verify-before-done` has the complete checklist).
- Read the whole simplification diff (`git diff <SNAP>`) hunk by hunk, asking
  "could any caller, user, or operator notice this?" against the checklist in
  [references/behavior-preservation.md](references/behavior-preservation.md).
- Measure with `git diff <SNAP> --shortstat`. If you added characterization
  tests, measure production code alone too, for example
  `git diff <SNAP> --shortstat -- . ':(exclude)tests/'`. Add before and after
  complexity numbers for the touched functions if you ran a complexity tool.
- Write the report below and leave the git state explained.

## Target catalog

Worked before/after examples in several languages, each with safe-when and
unsafe-when conditions, are in [references/catalog.md](references/catalog.md).
How to spot generated-code bloat specifically:
[references/ai-bloat.md](references/ai-bloat.md).

| Target | Signals | Default move | The trap |
|---|---|---|---|
| Dead code, unused imports, vars, params | linter warnings; zero references | Delete | Reached dynamically (reflection, string dispatch, DI, routes, templates, public exports); an import kept for its side effects or as a re-export; side-effecting initializer (keep the call, drop the binding); parameter required by a callback or interface shape; branch on a constant that differs per build |
| Duplicated logic | near-identical blocks; hand-rolled stdlib or helper | Call the existing helper | Helper differs on empty, null, unicode, rounding, timezone, or ordering; the helper is not importable from the scope without a new dependency edge; code that looks alike but changes for different reasons |
| Single-implementation interface | one implementer; not mocked; not a published extension point | Use the concrete type | The interface is a test seam, plugin boundary, or module boundary the project enforces |
| Pass-through wrapper | body is one call with the same arguments | Inline at call sites | The wrapper is a public facade, or its name documents intent at many call sites |
| Premature generalization, config that never varies | parameter always passed the same value; options with one used key; registry with one entry | Remove the knob | The knob is public API or set from deployment config |
| Deep nesting | three or more levels; `else` after `return` | Guard clauses, early return or continue | The early exit skips cleanup (unlock, close, finally); a wrong De Morgan inversion |
| Overly clever code | nested ternaries, dense one-liners, reduce-for-everything, bit tricks | Plain loop, if/else, named intermediate | The plain version differs outside the common range; the trick was a measured optimization |
| Redundant defensive checks and copies | null checks on non-nullable types; re-validating validated input; copies of data already in hand | Delete | The check sits at a trust boundary (user input, network, deserialization, FFI); the type is declared but not enforced (`any`, untyped callers, parsed data); a lock, `await`, or transaction sits between the first check or read and the repeat; the copy keeps other callers or threads from sharing mutable state |
| Error-swallowing try/catch | catch, log, continue; catch, return default; catch, rethrow unchanged | Remove, or narrow to the error the caller handles | Callers rely on "never throws" (tier 2); top-level handlers legitimately catch everything; a rethrow clause keeps its type out of a broader handler below it |
| Logging noise | entry and exit logs; the same error logged at every layer | Log once, where the error is handled | An alert, dashboard, or audit trail matches that line |
| Gratuitous casts | `as any`, `cast()`, `!`, converting a value to the type it already has | Delete, or fix the type at its source | The cast is a real narrowing the compiler cannot infer; a `!` hides a value that really can be missing (report it, do not "fix" it) |
| Unnecessary fallbacks | `?? default` or `or {}` on values that cannot be absent | Remove so bugs surface | The value can legitimately be absent; then the fallback is behavior |
| Restating comments | narrates the next line; docstring repeats the signature | Delete; keep why, constraints, links | License headers, doc comments that build public docs, directives tools parse |
| Inconsistent naming | new code uses a different verb or noun than its neighbors | Rename to the local convention | Public or serialized names are tier 3 |

## Report format

Use this structure. Omit empty kind headings, but always include "Behavior
changes" and "Deliberately left alone", writing "None" when empty, because a
missing section is ambiguous.

```markdown
## Simplification summary
Scope: <branch diff vs origin/main | path>, <N> files
Checks: <exact commands>, green before and after (<n> tests); flaky: <tests, or none>
Net: <git diff --shortstat vs checkpoint, production code>; <optional complexity before -> after>
Confidence: <edits on lines no test executes, or that survived a mutation spot-check; or "all edited lines covered">
Not verified: <checks the project lacks or you could not run, and why; or "none">

### Changes by kind
**Dead code removed (<n>)**
- path:line - what was removed - evidence it was unused
**Bloat removed (<n>)**
**Reused existing helpers (<n>)**
**Abstraction removed (<n>)**
**Control flow flattened (<n>)**
**Comments and naming (<n>)**

### Tests added
- path - what behavior it pins - keep or delete (the user's call)

### Behavior changes
- path:line - what is now observable differently - why it is worth it (quote old and new assertion if a test changed)

### Deliberately left alone
- path:line - candidate - reason (public API, trust boundary, no test coverage, taste only, ...)

### Noticed outside scope
- path:line - what - suggested follow-up

### Possible bugs spotted, not fixed
- path:line - symptom - why it looks wrong
```

## Common mistakes

- **Deleting code that is only "unused" to grep.** Reflection, name-based
  dispatch, DI containers, route and event registration, serializers,
  templates, and other repositories consuming a public export are invisible
  to a text search. Prove it, or treat it as tier 3.
- **Treating every import as inert.** In Python, Ruby, and JavaScript an
  import runs the module, which may register handlers, models, or plugins;
  in an `__init__.py` or index file it may be a re-export.
- **Dropping an unused variable together with its side-effecting initializer.**
  Linter autofixes do this too; read every autofix.
- **Calling "let the exception propagate" behavior-preserving.** Removing a
  swallowing catch changes what callers see. It may be the right call, but it
  is tier 2 and belongs in the report.
- **Removing a rethrow-only clause that sits before a broader handler.**
  `except ValueError: raise` followed by `except Exception: return None` is
  what keeps a `ValueError` from being swallowed.
- **Swapping in an "equivalent" helper without comparing edge cases.** Empty
  input, null, unicode, rounding mode, timezone, stable ordering, and error
  behavior are where near-duplicates differ.
- **Truthiness rewrites.** `if x is not None` to `if x`, or `??` to `||`,
  also treats 0, empty strings, and false (and in Python, empty collections)
  as missing.
- **Guard clauses that skip cleanup.** An early return before a manual unlock,
  close, or span end leaks it.
- **Changing evaluation order or laziness.** Hoisting a call out of a loop,
  merging loops, or turning a list into a generator changes when side effects
  run and how many times data can be iterated.
- **Trusting a green suite on concurrent code.** A second check after taking
  a lock, a re-read inside a transaction, or a defensive copy looks redundant
  and the tests will not object when it disappears.
- **Merging code that is similar by coincidence.** Two blocks that change for
  different reasons should stay apart; the wrong abstraction costs more than
  the duplication.
- **Inlining an interface the tests use as a seam.** Check test doubles before
  collapsing an abstraction.
- **Editing tests to make a simplification pass.** That converts a red signal
  into a hidden behavior change.
- **Bisecting against a flaky test.** Rerun the failure first; a test that
  flips on unchanged code says nothing about the batch.
- **Scope creep and taste edits.** Reformatting, renaming to personal
  preference, and tidying untouched legacy code bury the real changes.
- **Claiming "no behavior change" without rerunning the full checks after the
  last batch.**

## Related skills

- `review-suite:pr-review` to find bugs, risks, and design flaws, including
  an independent look at the diff once the cleanup is done.
- `implementation:refactor-safely` for extracting, splitting, moving, or
  renaming established code, deleting long-lived modules, and any change to a
  public surface (deprecate before delete).
- `review-suite:performance-review` when the code is slow or allocates too
  much.
- `implementation:debug-root-cause` or `workflow:ci-failure-triage` when the
  baseline is already red.
- `implementation:tdd` for characterization tests (step 3), and
  `implementation:verify-before-done` for the final checks (step 7).
- `data-api:db-migration-safety` for migrations, and `data-api:api-design`
  for wire or serialized contracts a tier 3 change would touch.
- `workflow:git-worktrees` to work in a separate checkout when the index
  holds staged work you must not disturb.

Skills are named here as `plugin:skill`; an agent that lists skills by bare name knows each one by the part after the colon (`review-suite:pr-review` is `pr-review`). If a skill named here isn't installed, give the short version inline and list the deeper pass as a follow-up.

## Reference files

- `references/catalog.md`: before/after examples (TypeScript, Python, Go,
  Java, C#, Rust) with safe-when and unsafe-when conditions. Read while
  applying any target (step 5).
- `references/ai-bloat.md`: fingerprints of generated code, the boundary
  rule, and keep or remove rules per pattern. Read when the diff was
  generated or reads like it.
- `references/behavior-preservation.md`: observable-behavior checklist,
  equivalence traps, characterization and differential testing, coverage
  commands, and checkpoint edge cases. Read before any tier 1 or 2 edit and
  during the final diff review (step 7).
- `references/detection-tooling.md`: per-language commands for unused code,
  duplication, complexity, and redundant casts, conditions, and handlers,
  plus the recipes for proving something is unused and for finding a
  reusable helper. Read at inventory time (step 4).
