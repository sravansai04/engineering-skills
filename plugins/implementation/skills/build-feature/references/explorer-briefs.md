# Explorer briefs for Phase 2

Read this when writing the explorer subagent prompts, when synthesizing what
they return, or when you have to explore without subagents.

## Contents

1. Dispatch mechanics
2. The shared preamble and return contract
3. The four angle prompts
4. Synthesizing the results
5. Exploring without subagents
6. Search commands worth knowing

---

## 1. Dispatch mechanics

- Send every explorer call in **one message**. Calls issued in separate turns
  run one after another and the phase takes three times as long.
- Use a read-only agent type when the harness has one. In Claude Code that is
  the built-in `Explore` subagent; ask for "medium" thoroughness for M
  features and "very thorough" for L. If you must use a general-purpose agent,
  say explicitly in the prompt that it must not create, edit, or delete files
  or run commands that change state.
- Subagents start with an empty context. They do not know the feature, the
  conversation, or what you have already read. Everything they need goes into
  the prompt.
- How many: two or three for M (two suffice when the analog and the
  integration surface are the same code); three or four for L, adding angle
  D. S features get no subagents.
- Cap the size of what comes back. A subagent's report lands in your context;
  a 3,000-word essay crowds out the code you still need to read.

## 2. Shared preamble and return contract

Start every explorer prompt with this preamble, filled in:

```text
Context: I am about to implement a feature in this repository and need to
understand the existing code first. Feature: <one-sentence goal from the brief>.
Repository root: <path>. Primary language and framework, if known: <...>.

You are read-only. Do not create, modify, or delete files, and do not run
commands that change state (no installs, migrations, commits, or formatters).
Reading files, searching, and read-only git commands are fine.

Your angle: <angle name>. Stay on it; other explorers cover the other angles.
```

End every explorer prompt with this return contract:

```text
Return, in under ~500 words:
1. Findings: short bullets, each anchored to file:line. Label each bullet
   FACT (you read it) or INFERENCE (you are guessing from names or structure).
2. Files to read: at most 8, ranked by importance, each with one line on why.
3. Surprises: anything that contradicts what a newcomer would assume.
4. Open questions: things the code cannot answer and a human must decide.
Do not propose a design. Report what exists.
```

The FACT and INFERENCE labels matter: they tell you which claims you must
check in the source before building on them. The "no design" rule keeps
explorers from anchoring you on the first idea they had.

## 3. The four angle prompts

Insert the body between the preamble and the return contract.

### A. Closest analog

```text
Find the one or two existing features most similar to the one described, and
trace each end to end: where a request or event enters, which layers and
modules it passes through, where state is read or written, how errors are
surfaced, and how the result reaches the user or caller. Note which parts look
copied between similar features (a de facto template) and which parts differ.
Use recent history (git log on the relevant paths) to find the most recently
added similar feature; it usually reflects current conventions best.
```

### B. Integration surface

```text
Identify exactly where the new behavior would plug in: entry points (routes,
handlers, commands, jobs, UI components), the services or modules it must
call, data structures and storage it would touch, configuration and feature
flags, dependency wiring or registration it would need, and any extension
points designed for this kind of addition. List the boundaries it would cross
(module, process, network, permission) and the rules each boundary enforces.
```

### C. Verification and conventions

```text
Determine how code like this is tested and reviewed here. Report: the test
layout and naming for similar features; fixtures, factories, fakes, or test
helpers they use; the exact commands to run a single test, one file, the
relevant suite, the linter, the formatter in check mode, and the type checker
(read package manifests, build files, Makefiles, CI workflow files, and
contributor docs to find them; quote the source of each command); CI checks a
change must pass; the installed versions of the frameworks and libraries this
feature is likely to call (from the lockfile, not the version range in the
manifest; quote the file); and conventions that review clearly enforces
(naming, error handling, logging, layering, translations, documentation).
```

### D. Risk surface (L features)

```text
Identify what this feature could break or make unsafe. Look at: the data model
and how schema changes are made and deployed; permission and visibility
checks near the integration points; hot paths and large-data operations the
feature would join; external services and how failures and retries are
handled; caching that could serve stale results; rollout mechanisms (feature
flags, config, staged deploys); and observability (logs, metrics, alerts) in
the area. For each risk, name the file:line that makes it real.
```

## 4. Synthesizing the results

1. **Read before you believe.** Read the top-ranked files yourself, at least
   the ones your design will depend on. Check every INFERENCE that a decision
   will rest on; promote it to FACT or discard it.
2. **Reconcile conflicts.** When explorers disagree (one says all writes go
   through a repository class, another found raw queries in handlers), open
   both sites. Often both are true and the difference is old versus new
   style; the newer one is usually the convention to follow, but confirm with
   history before assuming.
3. **Write the codebase map.** Keep it short; it goes into the Clarify message
   and the plan:

```text
Codebase map: <feature>
Entry points:     <file:line> <what>
Analog to copy:   <feature> at <file>; differences we need: <...>
Patterns:         <pattern> (<file:line>); <pattern> (<file:line>)
Tests:            style <...>; single test: `<cmd>`; suite: `<cmd>`
Quality gates:    lint `<cmd>`; types `<cmd>`; CI checks <...>
Dependencies:     <library>@<installed version> (<lockfile>)
Constraints:      <...>
Risks:            <...> (<file:line>)
For the user:     <questions only a human can answer>
```

4. **Update the brief.** Move unknowns the code answered into facts, and
   carry the rest to Phase 3. The dependency versions tell Phase 6 which
   calls to check with `implementation:docs-lookup`: any API the repo does not already use
   the same way.

## 5. Exploring without subagents

Run the same angles yourself, in the order C, A, B (D for L). Doing C first
means you know how to run tests before you need to, and it surfaces the
contributor docs that explain the architecture. Time-box each angle and stop
when you can fill its row in the codebase map; reading every file in a
directory is not exploration, it is avoidance.

## 6. Search commands worth knowing

All of these are read-only. Adapt paths and patterns to the repository.

```bash
# Find candidates by name or content (ripgrep; -g filters by glob)
rg -n "class \w+Exporter" -g '*.py'
rg -l "toCsv|to_csv|WriteCsv"
git grep -n "registerRoute"            # works without ripgrep installed

# Find the most recent similar work and who touched it
git log --oneline -n 20 -- src/reports/
git log -S "to_csv" --oneline          # commits that added or removed the string
git blame -L 40,80 src/reports/service.py

# Locate the test and quality commands
cat package.json pyproject.toml Makefile 2>/dev/null | head -100
ls .github/workflows .gitlab-ci.yml .circleci 2>/dev/null
```

Typical single-test commands, to confirm against the project's own docs:

| Ecosystem | Run one test or file |
|-----------|---------------------|
| JavaScript or TypeScript (Vitest) | `npx vitest run src/reports/export.test.ts` |
| JavaScript or TypeScript (Jest) | `npx jest src/reports -t "exports csv"` |
| Python (pytest) | `pytest tests/test_export.py -k csv -x` |
| Go | `go test ./internal/reports/... -run TestExportCSV` |
| Rust | `cargo test export_csv` |
| Java (Gradle) | `./gradlew test --tests 'com.acme.reports.ExportTest'` |
| Java (Maven) | `mvn -Dtest=ExportTest#writesHeader test` |
| Ruby (RSpec) | `bundle exec rspec spec/reports/export_spec.rb:42` |
| .NET | `dotnet test --filter "FullyQualifiedName~ExportTests"` |

Prefer the project's wrapper (a Makefile target, an npm script, a task runner)
over the raw tool when one exists; it carries the flags and environment the
team relies on.
