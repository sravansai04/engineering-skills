# Roadmap

## Vision

Coding agents are fast at producing code and uneven at the judgment around it: when to stop and ask, what to check before calling something done, which edge case breaks at scale, what a reviewer will actually catch. This marketplace packages that judgment as skills that any team can install, whatever its language or stack.

Every skill here aims to be:

- **Measurably better than no skill.** Each one ships with evals, and a change is accepted when it shows a before and after.
- **Precise about when it applies.** It loads for its own requests and names the sibling skill that owns each nearby request, so skills hand off instead of overlapping.
- **Stack-agnostic.** It finds and follows the project's own conventions and tools instead of imposing one ecosystem's habits.
- **Safe by default.** Read-only pre-approved tools, confirmation before anything destructive or public, and untrusted input treated as data.

Growth is deliberately slow: a smaller set of skills that each clearly earn their place in the shared skill listing beats a large set that crowds each other out.

## The plugins

| Plugin | Holds skills that... | Skills today |
|---|---|---|
| `implementation` | write or change code: shape an idea, plan, build, test-drive, debug, refactor, simplify, check docs, verify before done | brainstorm-spec, plan-feature, build-feature, execute-plan, tdd, debug-root-cause, refactor-safely, simplify-code, docs-lookup, verify-before-done |
| `review-suite` | evaluate code someone wrote: pull requests, security, performance, multi-reviewer passes | pr-review, secure-code-review, performance-review, parallel-review |
| `data-api` | design or check API contracts, database migrations and queries | api-design, db-migration-safety, query-review |
| `workflow` | produce the team artifacts around code: commits, PR descriptions, review responses, worktrees, CI triage, ADRs, postmortems | commit-message, pr-description, respond-to-review, git-worktrees, ci-failure-triage, adr-writer, incident-postmortem |
| `frontend` | shape and check user interfaces: visual direction, browser testing, accessibility | ui-design-direction, browser-testing, accessibility-review |
| `skill-dev` | author, test and maintain skills themselves | create-skill |

A new plugin needs a real gap that no existing plugin's moment covers. Propose one in a Discussion before building it.

## How to pick something up

1. Comment on the matching issue (or open one, labelled with the plugin) so two people don't build the same thing.
2. For a new skill, start a thread in the **Ideas** discussion category first and use the `skill-dev:create-skill` skill to check for overlap before drafting: it is cheaper to reshape an idea than a finished pull request.
3. Follow [CONTRIBUTING.md](../CONTRIBUTING.md) and [testing-skills.md](testing-skills.md). Every item below needs real, checked commands and a before and after in the pull request.

The lists are suggestions, not commitments. Better ideas are welcome.

## Good first issues

Small, self-contained additions to an existing reference file or eval set. Each takes an afternoon and teaches the repository's conventions.

1. **Failure markers for more test runners** (`workflow`): add PHPUnit, Elixir ExUnit and Swift XCTest rows to the ecosystem table in `ci-failure-triage/references/failure-signatures.md`, with the strings each runner prints when a test or build fails.
2. **Dead-code tooling for PHP and Kotlin** (`implementation`): add sections to `simplify-code/references/detection-tooling.md` with tested commands for unused code and complexity in those languages.
3. **Query-count recipes for more ORMs** (`review-suite`): add GORM, Ecto, Sequelize and TypeORM rows to the query-count table in `performance-review/references/measurement.md`.
4. **Elixir security tooling** (`review-suite`): add an Elixir and Phoenix row (static analysis and dependency audit) to the per-ecosystem table in `secure-code-review/references/tooling.md`.
5. **A fourth eval for a minimal eval set** (`implementation`): `tdd` and `verify-before-done` have the minimum three behavior evals; add a realistic prompt with a fixture under `evals/files/` and three to six checkable expectations.
6. **Near-miss trigger prompts for "root cause" wording** (`implementation`, `workflow`): "find the root cause of last night's outage from these logs" belongs to `debug-root-cause`, while "write the RCA for last night's outage" belongs to `incident-postmortem`. Add a few such pairs to both skills' `evals/trigger-evals.json` (true on one side, false with `should_route_to` on the other) and run them with the trigger checker.

## Medium

A new reference file, a new reviewer angle, or tooling that touches one skill. Expect a few days and a short design discussion in the issue.

7. **TDD in Java and Kotlin** (`implementation`): a `tdd/references/java.md` covering JUnit 5 with Gradle and Maven, confirming a test ran, parameterized tests and test doubles without heavy mocking, linked from `SKILL.md`.
8. **TDD in Rust** (`implementation`): a `tdd/references/rust.md` covering unit versus integration test layout, `cargo test` filtering, property tests and deterministic time.
9. **Security sinks for Rust** (`review-suite`): a `secure-code-review/references/sinks-rust.md` covering `unsafe` and FFI, command execution, raw SQL, path handling and deserialization, in the format of the existing sink files.
10. **Migration safety for SQL Server or SQLite** (`data-api`): a `db-migration-safety` reference with the lock, rewrite and online-operation behavior of one more engine, plus its safe recipes for adding columns, indexes and constraints.
11. **Two more CI systems** (`workflow`): add Buildkite and Bitbucket Pipelines sections to `ci-failure-triage/references/jenkins-and-others.md`: how to fetch the log, find the failing step, rerun it, and reproduce it locally.
12. **A cost reviewer persona** (`review-suite`): a `parallel-review` persona that looks for changes that quietly raise running costs (per-request paid API calls, unbounded storage growth, egress, log volume) with an estimate per finding.
13. **Runnable behavior evals for one plugin** (`data-api`): convert the three `data-api` skills' `evals/evals.json` prompts into `claude plugin eval` case directories with graders, and record the with-and-without scores in the pull request.

## Large

New skills, or repository tooling with its own design. Open a Discussion in the **Ideas** category before writing code, and name the sibling boundaries up front.

14. **`iac-review`** (`review-suite`): reviews an infrastructure change (a Terraform plan, a Kubernetes or Helm diff, a Dockerfile) for destructive replacements, blast radius, drift and misconfiguration before it is applied, leaving application-code security to `secure-code-review`.
15. **`runbook-writer`** (`workflow`): writes and reviews operational runbooks that take an on-call engineer from an alert to diagnosis, mitigation and rollback with verified commands, complementing `incident-postmortem`.
16. **`instrument-code`** (`implementation`): adds structured logs, metrics and traces to a change, chosen from the questions an on-call engineer will ask about it, without high-cardinality labels or logged secrets.
17. **`i18n-review`** (`frontend`): finds and fixes localization blockers (hard-coded strings, sentences built by concatenation, plural rules, locale-aware dates, numbers and currency, text expansion), leaving visual right-to-left polish to `ui-design-direction`.
18. **`subagent-design`** (`skill-dev`): creates and tunes custom subagent definitions (scope, tool lists, model choice, the brief they receive) and tests whether delegation to them helps, as `create-skill` does for skills.
19. **Trigger regression checks in CI** (repository tooling): a maintainer-triggered workflow that reruns the trigger evals of any skill whose description changed in a pull request, within a fixed cost cap, and posts the before-and-after table. It needs a design for secrets and fork pull requests before any code.
