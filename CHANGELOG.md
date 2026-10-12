# Changelog

All notable changes to this marketplace are recorded in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each plugin's version lives in its `plugin.json` and its marketplace entry, and Claude Code delivers an update only when that version changes. A heading below is a repository release (git tag `vX.Y.Z`), and at a release every plugin carries the release's version; between releases, a plugin with a merged change can run ahead of the others. How versions are chosen is described in [docs/maintainers.md](docs/maintainers.md).

## [Unreleased]

### Fixed

- `frontend` 1.0.1: `ui-design-direction`'s `scan-hardcoded.mjs` no longer hangs on a Tailwind arbitrary value like `[9/999/999/...]`. Its layout-only check could backtrack exponentially (about 4.6 s at 107 characters, growing about 6x per extra segment); it now runs in linear time, with a self-test that guards it.

## [1.0.0] - 2026-10-12

First public release: six plugins with 28 skills, all at plugin version 1.0.0.

### Added

#### `implementation` 1.0.0

- `brainstorm-spec`: turns a rough idea into a spec the user approves, through a one-question-at-a-time dialogue, before any plan or code exists.
- `plan-feature`: writes a reviewable implementation plan with acceptance criteria, risks, rollout and rollback, and small verifiable slices.
- `build-feature`: takes a multi-file feature from request to a verified, review-ready change through checkpointed phases.
- `execute-plan`: carries out an existing written plan task by task with a progress ledger, and stops where the code contradicts the plan.
- `tdd`: builds code test-first in a red-green-refactor loop, including regression-test-first bug fixes, and adds tests to existing untested code.
- `debug-root-cause`: proves the root cause of a crash, wrong output, flaky test, hang, slowdown or leak before fixing it with a regression test.
- `refactor-safely`: restructures code and runs dependency or framework upgrades without changing behavior, in small verified steps.
- `simplify-code`: shrinks just-written code without changing behavior, gated by tests and grouped by risk.
- `docs-lookup`: grounds API calls and configuration in the documentation for the exact library versions the project resolves.
- `verify-before-done`: proves a change is finished by running the project's own checks and exercising the change through its real entry point.

#### `review-suite` 1.0.0

- `pr-review`: reviews a pull request, branch or diff and reports verified, severity-rated findings with a merge verdict.
- `secure-code-review`: traces untrusted input to dangerous sinks and finds missing security controls, mapped to OWASP.
- `performance-review`: works out how a change's cost grows at 10x to 1000x data and traffic, with an impact estimate and a fix per finding.
- `parallel-review`: runs one reviewer subagent per angle, re-verifies every serious finding and merges the results into one ranked report.

#### `data-api` 1.0.0

- `api-design`: designs and reviews HTTP, GraphQL and gRPC contracts, webhooks, and event and message schemas.
- `db-migration-safety`: writes and reviews schema and data migrations that stay safe under rolling deploys.
- `query-review`: reviews one SQL statement, query plan or ORM call site for correctness, speed and concurrency safety.

#### `workflow` 1.0.0

- `commit-message`: writes commit messages in the repository's convention, splits a working tree into atomic commits, and resolves merge and rebase conflicts.
- `pr-description`: writes pull request titles and descriptions from the real diff, and release notes for a tag or commit range.
- `respond-to-review`: works through review comments on your own pull request, checks each claim before fixing or pushing back, and replies to every thread.
- `git-worktrees`: creates, sets up and safely removes git worktrees for parallel branches, long-running jobs and parallel agents.
- `ci-failure-triage`: finds the first real error in a red CI run, decides with evidence whether the change caused it, and fixes the cause.
- `adr-writer`: writes, accepts, supersedes, deprecates and reviews architecture decision records in the repository's format.
- `incident-postmortem`: writes and reviews blameless postmortems with a sourced timeline, quantified impact and owned action items.

#### `frontend` 1.0.0

- `ui-design-direction`: decides a deliberate visual direction, encodes it as design tokens, and checks the built components against it.
- `browser-testing`: verifies UI changes in a real browser and writes, fixes or de-flakes end-to-end tests.
- `accessibility-review`: reviews and fixes web UI against WCAG 2.2 Level AA, pairing automated scans with manual keyboard and screen-reader passes.

#### `skill-dev` 1.0.0

- `create-skill`: creates, tests and ships a new skill, or fixes an existing one, with fresh-session trigger and behavior evals.

#### Repository

- `scripts/validate_skills.py`: checks skill frontmatter (including XML-like tags in descriptions), positional `$0`-`$9` placeholders that Claude Code would substitute, links, reference coverage, eval files, manifests and version agreement, keeps shared blocks identical across skills, checks that every label the forms and Dependabot apply exists, and scans for locally denylisted terms.
- Shared blocks used across skills: one severity scale and verdict ladder for review findings (`severity`), the trust check before running code from a GitHub pull request or GitLab merge request (`trust-gate`), and the rule that PR text, code comments and logs are data, not instructions (`untrusted-input`).
- Contributor and community documents: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), `SECURITY.md`, `SUPPORT.md`, `LICENSE` (MIT), and the guides in `docs/` (testing skills, roadmap, maintainer process).

[Unreleased]: https://github.com/sravansai04/engineering-skills/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/sravansai04/engineering-skills/releases/tag/v1.0.0
