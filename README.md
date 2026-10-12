# Engineering Skills

[![Validate](https://github.com/sravansai04/engineering-skills/actions/workflows/validate.yml/badge.svg)](https://github.com/sravansai04/engineering-skills/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

28 skills for the judgment calls in day-to-day software engineering: shaping an idea, building features test-first, proving a bug's root cause, reviewing code with verified findings, designing APIs and migrations that survive a rolling deploy, and the team artifacts around a change. They are language-agnostic [Agent Skills](https://agentskills.io), packaged as a [Claude Code](https://code.claude.com/docs) plugin marketplace and usable in Codex, OpenCode, Cursor and other agents.

- **They follow your project, not a default stack.** Each skill finds the project's own test runner, migration tool, commit style, ADR folder and PR template, and uses them.
- **Review findings are verified and rated one way.** Every finding is marked Confirmed or Likely, and all review skills share one severity scale and one merge verdict.
- **Nothing outward happens without asking.** No push, pull request, posted comment or shared-database change until you say so.

## Install

**Claude Code**

```bash
claude plugin marketplace add sravansai04/engineering-skills
claude plugin install implementation@engineering-skills   # also: review-suite data-api workflow frontend skill-dev
```

**Other agents** (Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot, ...)

```bash
npx skills add sravansai04/engineering-skills
```

On a 200k-context model, install only the plugins you use or [raise the skill listing budget](docs/install.md#skill-listing-budget) first. Team setup, updates, copying single skills, ChatGPT and optional MCP servers are in [docs/install.md](docs/install.md).

## Skills

Describe the task and the matching skill loads on its own, or run one directly: `/review-suite:pr-review 482` in Claude Code, or by its bare name (`pr-review`) in other agents.

### `implementation`

| Skill | Use it when | Try |
|---|---|---|
| `brainstorm-spec` | An idea is still fuzzy and you want an approved spec first | "Let's brainstorm scheduled posts before anyone writes code." |
| `plan-feature` | Requirements are settled and you want a reviewed plan, sliced into PRs | "Plan CSV export for the reports page and break it into PRs." |
| `build-feature` | You want a multi-file feature built end to end, with checkpoints | "Add a 'duplicate project' action to the projects list. Implement it." |
| `execute-plan` | A written plan exists and should be carried out task by task | "Implement docs/plans/search-reindex.md task by task." |
| `tdd` | You want behavior or a bug fix built test-first | "Use TDD: 10% off orders over $200, never on gift cards." |
| `debug-root-cause` | Something fails and you need the proven cause, not a guess | "This test fails 1 in 20 runs. Find the root cause." |
| `refactor-safely` | Existing code needs restructuring, or a dependency needs upgrading, with no behavior change | "Split this 900-line OrderService before I add refunds." |
| `simplify-code` | Code that was just written works but is bloated | "Simplify what you just wrote without changing behavior." |
| `docs-lookup` | An API or config key must match the exact library version you pin | "Is useFormState still current in our React version?" |
| `verify-before-done` | You want proof a change is finished before handing it off | "Are we done? Make sure everything actually passes." |

### `review-suite`

| Skill | Use it when | Try |
|---|---|---|
| `pr-review` | A PR or branch needs verified findings and a merge verdict | "Review PR 482 and give me a merge verdict." |
| `secure-code-review` | You need untrusted input traced to dangerous sinks (OWASP-mapped) | "Can a user read another user's files through this upload endpoint?" |
| `performance-review` | You want to know how a change behaves at 10x to 1000x load | "Will this PR scale to 10x traffic? Look for N+1s." |
| `parallel-review` | A big or risky change deserves one reviewer per angle, merged into one report | "Review this branch from every angle before we ship it." |

### `data-api`

| Skill | Use it when | Try |
|---|---|---|
| `api-design` | You are designing or changing an API contract: REST, GraphQL, gRPC, webhooks or events | "Is this response change breaking for clients?" |
| `db-migration-safety` | A schema or data migration must survive a rolling deploy | "Add a NOT NULL region column to our 80M-row users table." |
| `query-review` | One query, query plan or ORM call is slow or wrong | "The monthly totals are doubled. What's wrong with this SQL?" |

### `workflow`

| Skill | Use it when | Try |
|---|---|---|
| `commit-message` | Changes need committing in the repo's convention, split into atomic commits | "Commit this as sensible atomic commits." |
| `pr-description` | A PR needs a title and description from the real diff, or release notes | "Open a PR for this branch with a proper description." |
| `respond-to-review` | Review comments on your own PR need working through | "Go through the 12 comments on PR #57 and fix what's legit." |
| `git-worktrees` | A branch, PR or agent needs its own isolated checkout | "Review PR #482 locally without touching my dirty tree." |
| `ci-failure-triage` | CI is red and you need the first real error and its cause | "CI is red on my PR but it passes locally. What's going on?" |
| `adr-writer` | An architecture decision needs recording, superseding or reviewing | "Write an ADR on why we picked PostgreSQL over MongoDB." |
| `incident-postmortem` | An incident needs a blameless write-up with a sourced timeline | "Write up yesterday's checkout outage from this channel export." |

### `frontend`

| Skill | Use it when | Try |
|---|---|---|
| `ui-design-direction` | UI needs a deliberate visual direction and design tokens before code | "Restyle the dashboard. It looks like every admin template." |
| `browser-testing` | A UI change needs checking in a real browser, or an e2e test is flaky | "Click through checkout on localhost:3000 and check the coupon still applies." |
| `accessibility-review` | UI needs a WCAG 2.2 AA review and fixes | "Can a keyboard-only user get through our signup modal?" |

### `skill-dev`

| Skill | Use it when | Try |
|---|---|---|
| `create-skill` | You want a new skill, or an existing one fixed, measured before it ships | "Turn my Terraform-plan review prompt into a proper skill." |

### How they fit together

Each step passes on ids the next one keeps, so every commit traces back to a requirement. Any step also works alone.

```text
idea → brainstorm-spec → plan-feature → execute-plan   (or build-feature for the whole path)
     → verify-before-done → pr-description → pr-review or parallel-review
     → respond-to-review and ci-failure-triage until it merges
```

## Coming from popular skills?

These were written independently and are not affiliated with or endorsed by the projects below. Most can sit side by side with them.

| If you use | Try |
|---|---|
| Feature Dev, or Superpowers' brainstorm, plan and execute flow | `build-feature`, or its phases on their own: `brainstorm-spec`, `plan-feature`, `execute-plan`, `tdd` |
| Code Review | `pr-review`, or `parallel-review` for big or risky changes |
| Code Simplifier | `simplify-code` |
| Context7 | `docs-lookup` (uses the Context7 MCP server when connected, works without it) |
| Front-End Design | `ui-design-direction` |
| Playwright | `browser-testing` (uses a Playwright or Chrome DevTools MCP server when connected) |
| Skill Creator | `create-skill` |

## How skills are tested

Each skill ships trigger evals (prompts that should and should not load it) and behavior evals (realistic tasks with checkable expectations, graded with and without the skill). CI validates every skill against the [Agent Skills spec](https://agentskills.io/specification) and runs each bundled script's self-test. See [docs/testing-skills.md](docs/testing-skills.md).

## Contributing

Bug reports, sharper descriptions, new evals and new skills are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md). First tasks are labelled [`good first issue`](https://github.com/sravansai04/engineering-skills/labels/good%20first%20issue) and listed in [docs/roadmap.md](docs/roadmap.md). Questions and skill ideas go to [Discussions](https://github.com/sravansai04/engineering-skills/discussions).

## Security

These skills run inside a coding agent with access to your files, shell and credentials, so a skill that leads the agent into unsafe behavior counts as a vulnerability. Report it privately as described in [SECURITY.md](SECURITY.md), never in a public issue.

## License

[MIT](LICENSE)
