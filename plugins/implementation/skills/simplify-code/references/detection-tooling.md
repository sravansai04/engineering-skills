# Detection tooling and proof recipes

Detectors find candidates quickly; they do not decide anything. Every hit
still goes through the tier check in SKILL.md, and anything not file-local
needs the proof recipe below before you delete it.

## Contents

1. Using detectors well
2. Commands by language
3. Redundant casts, conditions, and handlers
4. Proving something is unused
5. Finding an existing helper before keeping a new one

---

## Using detectors well

- Prefer what the project already runs. If the repository configures a
  linter, type checker, or complexity limit, use that configuration first;
  its findings are the ones reviewers expect you to fix. Use the extra
  commands below as a supplement, not a replacement.
- Point file-level tools at the scope only. Run this from the repository
  root, since `git diff --name-only` prints root-relative paths:

  ```bash
  git diff --merge-base origin/main --name-only -z --diff-filter=d -- '*.py' \
    | xargs -0 -r ruff check --select F401,F841
  ```

  (`--diff-filter=d` drops deleted files. `-z` with `xargs -0` keeps paths
  with spaces intact, and `-r` stops GNU xargs from running the tool with no
  paths, which would lint the whole project; BSD and macOS xargs accept `-r`
  and already behave that way. Substitute your merge target.)
- Whole-program tools (knip, deadcode, vulture across packages) must see the
  whole project to judge reachability. Run them project-wide and filter the
  output to the scope.
- Do not run autofix modes blind. Unused-assignment fixers in several tools
  have deleted a side-effecting right-hand side along with the variable.
  Apply fixes per file and read the diff. Never enable "unsafe" fix modes
  (for example ruff's `--unsafe-fixes`) without reviewing every change.
- Install nothing permanent without asking. `npx`, `pipx run`, and `go run`
  style invocations keep tools out of the project's dependencies.
- Rerun after deletions; dead code is often transitively dead.

## Commands by language

### JavaScript and TypeScript

| Finds | Command | Notes |
|---|---|---|
| Unused locals and parameters | `npx tsc --noEmit --noUnusedLocals --noUnusedParameters` | Uses the project's tsconfig plus these two checks |
| Unused files, exports, dependencies | `npx knip --include files,exports,dependencies` | Whole-project; non-standard layouts need entry points in a knip config |
| Complexity and nesting | `npx eslint --rule 'complexity: [warn, 10]' --rule 'max-depth: [warn, 3]' <paths>` | `--rule` is merged on top of the existing config |

### Python

| Finds | Command | Notes |
|---|---|---|
| Unused imports, variables, arguments; commented-out code; else after return | `ruff check --select F401,F841,ARG,ERA001,RET505 <paths>` | |
| Complexity, blind excepts, try-except-pass, simplifiable constructs | `ruff check --select C901,BLE001,S110,SIM <paths>` | C901 threshold is `lint.mccabe.max-complexity` (default 10) |
| Unused code across modules | `vulture <paths> --min-confidence 80` | At 80 you mostly see imports, arguments, unreachable code; drop the flag to include functions and classes (reported at 60% confidence) and verify each |
| Complexity ranking | `radon cc -s -n C <paths>` | Shows blocks ranked C or worse (complexity 11 and up); always exits 0 |

### Go

| Finds | Command | Notes |
|---|---|---|
| Suspicious constructs | `go vet ./...` | |
| Unused unexported identifiers | `staticcheck -checks U1000 ./...` | Exported identifiers count as used |
| Functions unreachable from any main or test | `deadcode -test ./...` | Install with `go install golang.org/x/tools/cmd/deadcode@latest`; `deadcode -whylive=<pkg>.<Func> -test ./...` explains why something is live |
| Complexity | `gocyclo -over 15 .` | Exits 1 when anything is over the limit |

### Rust

| Finds | Command | Notes |
|---|---|---|
| Dead code, unused imports and variables, lints | `cargo clippy --all-targets` | `dead_code` is a rustc lint and warns by default; `pub` items of a library are not reported |
| Unused dependencies | `cargo machete` | Text-based and fast; false positives for crates used only via macros or build scripts |

### Java

| Finds | Command | Notes |
|---|---|---|
| Unused private fields and methods, locals, parameters | `pmd check -d src/main/java -R category/java/bestpractices.xml -f text` | PMD 7 syntax; the category also contains unrelated rules, so filter the output |
| Complexity | `pmd check -d src/main/java -R category/java/design.xml/CyclomaticComplexity -f text` | |
| Duplication | `pmd cpd --minimum-tokens 100 -d src/main/java --language java` | |

### C#

| Finds | Command | Notes |
|---|---|---|
| Unnecessary usings, unused or unread private members, unused parameters | `dotnet format style --diagnostics IDE0005 IDE0051 IDE0052 IDE0060 --severity info --verify-no-changes` | Report-only with `--verify-no-changes`; IDE0060 often has no automatic fix |

### Ruby

| Finds | Command | Notes |
|---|---|---|
| Useless assignments, unused arguments | `rubocop --only Lint/UselessAssignment,Lint/UnusedMethodArgument,Lint/UnusedBlockArgument <paths>` | Comma-separated, no spaces |
| Complexity and nesting | `rubocop --only Metrics/CyclomaticComplexity,Metrics/BlockNesting <paths>` | |

### Any language

| Finds | Command | Notes |
|---|---|---|
| Copy-paste duplication | `npx jscpd --min-lines 5 --reporters console <paths>` | Supports many languages; lower `--min-tokens` to be more sensitive |
| Cyclomatic complexity | `lizard -C 10 -w <paths>` | Warnings only, for functions over 10; non-zero exit when any are found |

## Redundant casts, conditions, and handlers

Several targets that otherwise rest on a hand-checked fact (a cast that does
nothing, a condition that cannot be false, a catch that only rethrows, a
suppression that suppresses nothing, a parameter that always receives the
same value) have type-aware or flow-aware detectors. When one exists, run it
and cite its output as the evidence for the tier 1 fact.

| Stack | Command | Finds |
|---|---|---|
| TypeScript (typed lint) | `npx eslint --rule '@typescript-eslint/no-unnecessary-condition: warn' --rule '@typescript-eslint/no-unnecessary-type-assertion: warn' --rule '@typescript-eslint/no-unnecessary-boolean-literal-compare: warn' <paths>` | Conditions always true or false per the types, `!` and `as` that change nothing, `x === true` on a boolean. Needs the project's typescript-eslint setup with type information already configured |
| JavaScript and TypeScript | `npx eslint --rule 'no-useless-catch: warn' --rule 'no-else-return: warn' --rule 'no-lonely-if: warn' --rule 'no-unneeded-ternary: warn' --rule 'no-useless-return: warn' <paths>` | Catch clauses that only rethrow, `else` after `return`, an `if` alone inside `else`, `x ? true : false`, a bare `return` at the end of a function |
| Python (mypy) | `mypy --warn-redundant-casts --warn-unused-ignores --warn-unreachable <paths>` | `cast()` to the type it already has, `# type: ignore` that ignores nothing, code the checker proves unreachable |
| Python (pyright) | set `reportUnnecessaryCast`, `reportUnnecessaryIsInstance`, `reportUnnecessaryComparison`, `reportUnnecessaryContains`, and `reportUnnecessaryTypeIgnoreComment` to `"warning"` in the pyright config, then `npx pyright <paths>` | The same family, plus `isinstance` and `==` checks the types already decide |
| Python (ruff) | `ruff check --select TRY203,RET504 <paths>` and `ruff check --extend-select RUF100 <paths>` | `try`/`except` whose every handler only re-raises; assigning a variable just to return it; `# noqa` comments that suppress nothing. RUF100 judges each `noqa` against the enabled rules, so extend the project's selection rather than replacing it |
| Go | `go run mvdan.cc/unparam@latest ./...` | Unused parameters and results, and parameters that always receive the same value (premature generalization) |
| Go | `go run github.com/mdempsky/unconvert@latest ./...` | Conversions to the type a value already has |
| Go | `staticcheck -checks 'S1*' ./...` | Simplifications (redundant `return`, needless `if`/`else` around a boolean, and so on). `'S*'` would also pull in the SA and ST groups |
| Rust | `cargo clippy --all-targets` | `unnecessary_cast`, `useless_conversion`, `needless_return`, and `needless_bool` warn by default |
| C# | `dotnet format style --diagnostics IDE0004 IDE0059 --severity info --verify-no-changes` | Unnecessary casts and values assigned but never read. IDE0079 (suppressions that suppress nothing) reports in the IDE |
| Java | `pmd check -d src/main/java -R category/java/design.xml/AvoidRethrowingException,category/java/codestyle.xml/UnnecessaryCast,category/java/codestyle.xml/UnnecessaryLocalBeforeReturn -f text` | Catch blocks that only rethrow, casts to the static type, a local assigned only to be returned |

Two caveats:

- These rules trust the declared types. At trust boundaries (parsed JSON,
  `any`, unchecked casts, untyped callers, Python hints nothing enforces) a
  finding is a lead, not proof.
- Rethrow detectors differ on sibling handlers. Ruff's TRY203 fires only
  when every handler on the `try` re-raises, and JavaScript has a single
  catch clause, so those findings are safe. For any other tool, confirm that
  no broader handler follows the clause before removing it (see
  [catalog.md](catalog.md#error-handling-that-swallows-or-repeats)).

## Proving something is unused

A symbol that is not local to one function needs all of these checks before
deletion. Record the evidence in the ledger.

1. **Search everything, by whole word.** Code, config, templates, SQL,
   scripts, CI files, docs that are generated into anything:

   ```bash
   git grep -n -w 'applyLoyaltyDiscount'
   ```
2. **Search for string-built and renamed references.** Quoted names, name
   fragments joined at runtime, and the other casings a serializer or
   framework maps between:

   ```bash
   git grep -n -i -E 'loyalty_?discount|loyalty-discount|"applyLoyalty'
   ```
3. **Check registration mechanisms** that call code without naming it at the
   call site: decorators and annotations (routes, event listeners, scheduled
   jobs, CLI commands, DI bindings); discovery by convention (file names,
   method prefixes such as `test_`, `visit_`, `handle`, `on`); lifecycle
   hooks the framework calls; reflection (`getattr`, `Class.forName`,
   `send`, `reflect`, `Activator.CreateInstance`); serializer and ORM
   mappings; template engines; plugin entry points (package `exports` or
   `bin`, Python entry points in `pyproject.toml`,
   `META-INF/services` files).
4. **Check the public surface.** Exported from a package entry point
   (`index.ts`, `__init__.py` or `__all__`), `pub` in a library crate, an
   exported Go identifier, a public type in a published artifact. If the
   repository is a library or other repositories import from it, a search
   inside this repository cannot prove absence: tier 3.
5. **For an import, check what importing does.** In Python, Ruby, plain
   JavaScript, and TypeScript under `verbatimModuleSyntax` or
   `preserveValueImports`, the import executes the module. Open it and look
   for top-level registration or patching (decorators that register, signal
   connections, plugin or model registries, monkeypatching, polyfills). An
   import with zero references in a file that re-exports (`__init__.py`,
   `__all__`, an index barrel) is a re-export, not dead code.
6. **Check whether it is new.** If the symbol does not exist on the merge
   target, nothing outside this branch can depend on it yet, which is
   strong evidence:

   ```bash
   git grep -n -w 'applyLoyaltyDiscount' origin/main   # no output: introduced on this branch
   git log -S'applyLoyaltyDiscount' --oneline          # commits that added or removed it
   ```
7. **Tests-only references** mean dead production code. Delete it together
   with its tests, unless it is itself a test utility, and say so in the
   report.
8. **Monorepos**: search from the repository root, not the package
   directory.

When any step is inconclusive, do not delete. Move the candidate to
"Deliberately left alone" with what you could not rule out.

## Finding an existing helper before keeping a new one

Run this for every new function in the diff that is not domain-specific
(formatting, parsing, collections, retries, dates, strings, money, paths).

- **By name fragments and synonyms**: format, render, display; parse, read,
  decode; slug, kebab; money, currency, amount; chunk, batch, partition.

  ```bash
  git grep -n -i -E '(def|function|func|fn) +[a-z_]*(slug|kebab)' -- ':!*.min.js'
  ```
- **By a distinctive literal** the new code contains: a regular expression,
  a date format string, an error message, a magic number.

  ```bash
  git grep -n -F 'yyyy-MM-dd'
  ```
- **In the usual homes**: `utils`, `lib`, `common`, `shared`, `helpers`,
  `core`, and the module's own internal package.
- **In what is already declared**: the standard library (Python `itertools`,
  `functools`, `collections`, `pathlib`; JavaScript `Array`, `Object`,
  `Intl`, `structuredClone`; Go `slices`, `maps`, `strings`; Java streams and
  `Collections`; Rust iterator adapters) and the libraries in the dependency
  manifest. Do not add a new dependency to replace a few lines; that is not
  a simplification.

Only reuse a helper the scope can already import: one in the same package,
in a declared dependency, or in a shared library's public API. A match in
another module's internals, under a test-support directory, or in a heavy
module the scope does not otherwise depend on would add a dependency edge or
an import cycle, which is a structural change nobody asked for and may break
the project's layering rules. Keep the duplicate in that case and list it
under "Noticed outside scope" as a candidate to promote to shared code.
After a swap, run the project's import-cycle or module-boundary check if it
has one.

If several helpers qualify, use the one the neighboring code uses. Before
swapping, compare edge-case behavior as described in
[catalog.md](catalog.md#duplication-reuse-what-exists).
