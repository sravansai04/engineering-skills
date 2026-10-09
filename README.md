# Engineering Skills

[![Validate](https://github.com/sravansai04/engineering-skills/actions/workflows/validate.yml/badge.svg)](https://github.com/sravansai04/engineering-skills/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

A [Claude Code](https://code.claude.com/docs) plugin marketplace of 28 skills for the judgment calls around day-to-day software engineering: shaping an idea before anyone builds it, planning and building features test-first, proving a bug's root cause, reviewing code with verified findings, designing APIs and migrations that survive a rolling deploy, the team artifacts around a change, frontend design and browser testing, and writing skills of your own. The skills are language- and framework-agnostic, and each ships with evals you can run to compare it against no skill. What they do differently:

- **They follow the project, not a default stack.** Each skill finds the project's own test runner, migration tool, commit style, ADR folder and PR template, and uses them.
- **Review findings are verified and rated one way.** Every review skill marks a finding Confirmed (reproduced or traced end to end) or Likely (one link unverified), and all of them share one severity scale and one verdict ladder.
- **Nothing outward happens without asking.** No push, pull request, posted comment or shared-database change happens until you say so.

| Plugin | Skills | For |
|---|---|---|
| [`implementation`](#implementation) | 10 | Shaping an idea into a spec, planning, building a feature end to end or executing a written plan, test-first development, root-cause debugging, safe refactoring and simplification, version-matched docs lookup, verifying work before calling it done |
| [`review-suite`](#review-suite) | 4 | Pull request review, security review, performance review, parallel multi-reviewer review |
| [`data-api`](#data-api) | 3 | API contract design, zero-downtime database migrations, SQL and query plan review |
| [`workflow`](#workflow) | 7 | Commits, PR descriptions, answering review comments, git worktrees, CI failure triage, architecture decision records, incident postmortems |
| [`frontend`](#frontend) | 3 | Visual direction and design tokens, browser verification and end-to-end tests, accessibility review |
| [`skill-dev`](#skill-dev) | 1 | Creating, testing and fixing Claude Code skills |

A skill is a folder with a `SKILL.md`: YAML frontmatter that tells Claude what the skill does and when to use it, followed by the instructions. Claude loads a skill when a request matches its description, or when you run it by name. Detail that is only sometimes needed sits in `references/` and is read on demand. Some skills also bundle helper `scripts/` and `assets/`. Every skill has `evals/` with test prompts.

---

## Quick start

### 1. Add the marketplace and install a starter set

From your shell, add the marketplace once, then install the plugins you want. `implementation` and `review-suite` are a good start:

```bash
claude plugin marketplace add sravansai04/engineering-skills
claude plugin install implementation@engineering-skills
claude plugin install review-suite@engineering-skills
```

On recent CLI versions, `claude plugin install implementation --marketplace sravansai04/engineering-skills` adds the marketplace and installs in one step (`claude plugin install --help` shows whether yours has `--marketplace`). Inside a Claude Code session the same steps are `/plugin marketplace add sravansai04/engineering-skills` and `/plugin install implementation@engineering-skills`.

Restart Claude Code (or run `/reload-plugins`) and check with `claude plugin list`.

### 2. Before installing all six, check the skill listing budget

> [!IMPORTANT]
> Claude Code lists every installed skill's description in a budget of 1% of the model's context window, counted in characters: about 8,000 on a 200k-token model, about 40,000 on a 1M-token model. Your personal skills and other plugins share it. When the listing overflows, the skills you have used least keep only their names, and right after an install those are these skills, so their trigger phrases vanish and automatic selection quietly stops picking them. All 28 descriptions here, names included, come to about 14,000 characters.
>
> - **1M-context models:** everything fits; install what you like.
> - **200k-context models:** install only the plugins you use, or raise the budget: add `"skillListingBudgetFraction": 0.02` to `~/.claude/settings.json`, or set `SLASH_COMMAND_TOOL_CHAR_BUDGET=20000` in your environment.
> - **To check:** the Skills row of `/context` in a session, and `claude plugin details <plugin>` for each installed plugin's always-on token cost.

Then install the rest, or only the ones you need:

```bash
for p in implementation review-suite data-api workflow frontend skill-dev; do
  claude plugin install "$p@engineering-skills"
done
```

### 3. Try one

Type `/` in a session and look for the `/implementation:` and `/review-suite:` entries, then run one on real work, for example `/review-suite:pr-review 482` on an open pull request. [Start here](#start-here) shows which skill to reach for when.

<details>
<summary>Installing from a private fork or mirror</summary>

Claude Code clones a marketplace with your own git credentials and never prompts for them, so for a private copy set up one of these first:

- **HTTPS (simplest):** `gh auth login`, then `gh auth setup-git`, so the git credential helper holds a GitHub credential.
- **SSH:** a GitHub SSH key loaded in `ssh-agent` (no passphrase prompt) with `github.com` already in `known_hosts`.

With the `owner/repo` form, Claude Code tries SSH first and falls back to HTTPS. If your machine has no GitHub SSH key, set `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1` to skip the SSH attempt. The public repository needs none of this.

</details>

### Share it with everyone on a project

Run this once in the project repository and commit the `.claude/settings.json` it writes. Teammates who trust the folder get the marketplace registered automatically:

```bash
claude plugin marketplace add sravansai04/engineering-skills --scope project
claude plugin install review-suite@engineering-skills --scope project
```

Auto-update is off by default for a third-party marketplace, so without it the team quietly stays on old versions. Before committing, add `"autoUpdate": true` to the `engineering-skills` entry under `extraKnownMarketplaces` in that `.claude/settings.json`.

### Updates

Background auto-update is off by default for a third-party marketplace. Either turn it on (`/plugin` → **Marketplaces** → `engineering-skills` → **Enable auto-update**), or update by hand:

```bash
claude plugin marketplace update engineering-skills
claude plugin update review-suite@engineering-skills

# every plugin you installed from this marketplace
for p in implementation review-suite data-api workflow frontend skill-dev; do
  claude plugin update "$p@engineering-skills"
done
```

You only receive a new copy of a plugin when its `version` changes. [CHANGELOG.md](CHANGELOG.md) records what changed.

### Alternative: copy individual skills

Every skill folder is self-contained, so you can use one without the marketplace. Copy the folder (not only `SKILL.md`) into your personal or project skills directory:

```bash
git clone https://github.com/sravansai04/engineering-skills.git

# personal: available in every project
cp -R engineering-skills/plugins/review-suite/skills/pr-review ~/.claude/skills/

# project: shared with the team through the repository
cp -R engineering-skills/plugins/implementation/skills/tdd <project>/.claude/skills/
```

Copied skills are invoked without the plugin prefix (`/pr-review` rather than `/review-suite:pr-review`) and do not update themselves.

### Try it without installing

To load plugins for a single session, for example while editing a skill:

```bash
claude --plugin-dir ./plugins                  # every plugin in the folder
claude --plugin-dir ./plugins/implementation   # just one
```

---

## Coming from popular skills?

If you already use one of these widely shared skills, plugins or MCP servers, this is the closest match here. The skills in this repository were written independently and are not affiliated with or endorsed by those projects. Most can sit side by side with them; if two installed skills cover the same request, invoke the one you want by name.

| If you use... | Try | Notes |
|---|---|---|
| Feature Dev, or the brainstorm, plan and execute flow from Superpowers | `implementation:build-feature` | Runs the whole path from request to a review-ready change. Each phase also stands alone: `implementation:brainstorm-spec`, `implementation:plan-feature`, `implementation:execute-plan`, `implementation:tdd`, `implementation:verify-before-done`. |
| Code Review | `review-suite:pr-review` or `review-suite:parallel-review` | `pr-review` for a routine PR; `parallel-review` puts one subagent on each reviewer angle for big or risky changes. |
| Code Simplifier | `implementation:simplify-code` | Works on just-written code, in test-gated batches. |
| Context7 | `implementation:docs-lookup` | Works with or without the Context7 MCP server: it uses Context7 when connected, and otherwise reads the docs and installed source for the version your lockfile pins. |
| Front-End Design | `frontend:ui-design-direction` | Commits to a visual direction and encodes it as design tokens before components are built. |
| Playwright | `frontend:browser-testing` | Uses a Playwright or Chrome DevTools MCP server when one is connected, and falls back to its bundled smoke test and the Playwright CLI when not. |
| Skill Creator | `skill-dev:create-skill` | Measures triggering in fresh sessions and output against a no-skill baseline. |

Context7 and Playwright are MCP servers rather than skills, so they complement these skills instead of competing with them. See [Optional MCP servers](#optional-mcp-servers).

---

## Start here

The skills hand work to each other along one path, and each step passes on ids the next one keeps, so every commit traces back to a requirement:

```text
idea
 → brainstorm-spec      a spec you approve, with requirement ids (R1, SC1, C1)
 → plan-feature         acceptance criteria tied to those ids (AC-1: R1), slices, steps T1, T2, ...
 → execute-plan         one verified commit per step, with the trailer "Plan-Task: T3"
   (or build-feature, which runs the whole path in one checkpointed run)
 → verify-before-done → pr-description → pr-review, or parallel-review for big changes
 → respond-to-review and ci-failure-triage until it merges
```

Any step also works alone. When two skills sound alike, one question usually settles it:

| Choosing between | Ask |
|---|---|
| `brainstorm-spec`, `plan-feature`, `build-feature`, `execute-plan` | Is the problem itself still fuzzy? brainstorm-spec. Settled, and you want a reviewed plan before code? plan-feature. A written plan exists? execute-plan. You want it built end to end? build-feature. |
| `verify-before-done`, `pr-review`, `parallel-review` | Checking your own change before you hand it off? verify-before-done. Reviewing a pull request? pr-review, or parallel-review when it is big or risky enough for several reviewers. |
| `simplify-code`, `refactor-safely` | Code that was just written and came out bloated? simplify-code. Existing code to restructure toward a goal, or a dependency upgrade? refactor-safely. |

---

## Skill catalog

Claude picks a skill automatically when your request matches its description. You can also run one directly with `/<plugin>:<skill>`, optionally followed by an argument. Each description also names the sibling skill to use instead for nearby requests, so the skills hand off to each other rather than overlap.

**Built-in commands.** Claude Code ships its own `/code-review` (also reachable as `/review`), `/security-review` and `/simplify`, and they can win automatic selection for generic phrasings such as "review this", "security review this" or "simplify this". When you want these skills, invoke them explicitly (`/review-suite:pr-review`, `/review-suite:secure-code-review`, `/implementation:simplify-code`) or name the skill in your prompt.

The review skills share one severity scale (`critical`, `high`, `medium`, `low`, plus `nit` where a report has a Nits section) and one verdict ladder (Block, Fix before merge, Merge with follow-ups, Merge), so a finding gets the same rating and the same merge outcome whichever skill raised it. `frontend:accessibility-review` uses the same scale and verdict, and also reports WCAG conformance as a separate dimension.

### `implementation`

| Skill | Invoke | What it does |
|---|---|---|
| `brainstorm-spec` | `/implementation:brainstorm-spec [rough idea, problem statement, or issue link]` | Turns a rough idea into a spec you approve before any plan or code, asking one multiple-choice question at a time, cutting scope, and comparing two or three approaches. |
| `plan-feature` | `/implementation:plan-feature [feature description, ticket link, or path to a spec]` | Writes a reviewable implementation plan before any code: acceptance criteria, prior art, change surface, risks and scale, rollout and rollback, and small verifiable slices. |
| `build-feature` | `/implementation:build-feature [feature request, ticket text, or issue link]` | Takes a multi-file feature from request to a verified, review-ready change in gated phases: read-only exploration, only the questions the code cannot answer, a design choice, a plan, test-first commits, and an independent review. |
| `execute-plan` | `/implementation:execute-plan [plan path, issue link, or task range such as T3-T6]` | Carries out a written implementation plan task by task: checks it against the code, keeps a durable ledger, commits each task only after its check passes, and stops on deviations instead of improvising. |
| `tdd` | `/implementation:tdd [behavior to build, bug to reproduce, or untested module]` | Builds code test-first in a red-green-refactor loop, including regression-test-first bug fixes and tests for existing untested code (each proven able to fail), and answers test-design questions (what to mock, which level, deterministic time). |
| `debug-root-cause` | `/implementation:debug-root-cause [error, stack trace, failing test, or symptom]` | Proves the root cause of a bug, crash, wrong output, flaky test, race, hang, environment-only failure, slowdown or memory leak, then fixes it with a regression test that fails first. |
| `refactor-safely` | `/implementation:refactor-safely [file, symbol, or area to refactor, and the goal]` | Restructures code without changing behavior: pins behavior with tests, finds every usage including string and reflective ones, moves in small verified steps, and runs dependency and framework upgrades the same way. |
| `simplify-code` | `/implementation:simplify-code [path or git range; default is this session's edits, else the branch diff]` | Shrinks just-written code, the branch diff or a named file without changing behavior: deletes dead code, duplicate helpers, needless abstraction, deep nesting and generated bloat in test-gated batches, and flags any edit a caller could notice. |
| `docs-lookup` | `/implementation:docs-lookup [library, API or config key, error message, or versions to compare]` | Checks API calls and config keys against the exact library version the project pins, not memory: reads the lockfile, pulls that version's docs (through Context7 when connected), and confirms each call in the source or types. |
| `verify-before-done` | `/implementation:verify-before-done` | Proves a code change is finished: runs the project's own checks and reads the output, exercises the change through its real entry point, self-reviews the diff, and reports what was verified and what was not. |

### `review-suite`

| Skill | Invoke | What it does |
|---|---|---|
| `pr-review` | `/review-suite:pr-review [pr-number \| pr-url \| branch \| base...head]` | Reviews a pull request, merge request, branch or local diff without touching your checkout, and reports verified, severity-rated findings with a merge verdict. |
| `secure-code-review` | `/review-suite:secure-code-review [PR number \| base...head \| path; default is pasted code, else the current branch]` | Security review of code, a diff or a PR: traces untrusted input to dangerous sinks and finds missing controls (authorization and IDOR, injection, XSS, SSRF, secrets, crypto, supply chain), mapped to OWASP. |
| `performance-review` | `/review-suite:performance-review [PR number, branch, commit range, or path]` | Works out how a change's cost grows at 10x to 1000x data and traffic: N+1s, unbounded queries, quadratic work, memory growth, cache and timeout flaws, pool contention and frontend load, each with an impact estimate and a fix. |
| `parallel-review` | `/review-suite:parallel-review [branch, PR number, or paths] [optional persona list]` | Runs one subagent per reviewer angle (correctness, security, performance, data, architecture, tests, API compatibility, reliability, UX), re-verifies the serious findings, and merges them into one ranked report. |

### `data-api`

| Skill | Invoke | What it does |
|---|---|---|
| `api-design` | `/data-api:api-design [spec file, endpoint, PR or diff, capability to design, or a single API question]` | Designs and reviews API contracts, REST first plus GraphQL, gRPC, webhooks, and event or message schemas: resources, status codes, errors, pagination, concurrency, retry-safe writes, versioning and deprecation. |
| `db-migration-safety` | `/data-api:db-migration-safety [migration file, PR, or planned schema change]` | Writes and reviews schema and data migrations that are safe under rolling deploys: expand/backfill/contract, two app versions on one schema, PostgreSQL and MySQL lock and rewrite hazards, batched backfills, safe renames and drops, rollback. |
| `query-review` | `/data-api:query-review [SQL text, file path, ORM call site, or EXPLAIN output]` | Reviews one SQL statement, query plan or ORM call site for correctness, speed and concurrency safety, PostgreSQL first with MySQL notes: NULL and fan-out bugs, EXPLAIN reading, index advice, parameterization, locking. |

### `workflow`

| Skill | Invoke | What it does |
|---|---|---|
| `commit-message` | `/workflow:commit-message` | Writes commit messages in the repository's convention (Conventional Commits by default) and splits a working tree into atomic commits without interactive staging, keeping secrets and junk out. Also resolves merge and rebase conflicts, regenerating lockfiles instead of hand-merging them. |
| `pr-description` | `/workflow:pr-description [PR number or URL to update \| base branch \| tag or commit range for release notes]` | Writes or refreshes a PR title and description from the real diff and commits, fills the repository's template, and can open or update the PR with `gh`. Also writes release notes and changelog entries for a tag or commit range. |
| `respond-to-review` | `/workflow:respond-to-review [pr-number \| pr-url \| branch, or pasted review comments]` | Works through review feedback on your own PR or MR: checks each comment against the code, fixes what holds up in focused commits, pushes back with evidence, and answers every thread. |
| `git-worktrees` | `/workflow:git-worktrees [branch or task to isolate \| worktree path to clean up]` | Creates, sets up and safely removes git worktrees, so each branch, PR or agent gets its own isolated checkout. |
| `ci-failure-triage` | `/workflow:ci-failure-triage [PR number, run ID, job URL, or pasted log]` | Triages a red CI run or PR check: finds the first real error, decides with evidence whether the change caused it, reproduces it with CI's setup, and fixes the cause instead of retrying or skipping. |
| `adr-writer` | `/workflow:adr-writer [decision topic \| ADR number to accept, supersede, deprecate, or review]` | Writes, accepts, supersedes, deprecates and reviews Architecture Decision Records in Nygard or MADR style, following the repository's folder, numbering and template. |
| `incident-postmortem` | `/workflow:incident-postmortem [incident ID, ticket or channel link, pasted log, or path to a draft to review]` | Writes and reviews blameless incident postmortems: a sourced UTC timeline, quantified impact, contributing factors, where you got lucky, and owned action items. Also preps the review meeting. |

### `frontend`

| Skill | Invoke | What it does |
|---|---|---|
| `ui-design-direction` | `/frontend:ui-design-direction [page, screen, or component to design; or a mockup, screenshot, or URL to match]` | Decides a visual direction before UI code exists, encodes it as design tokens (conforming to an existing design system first), builds token-only components, and checks contrast, hard-coded values and screenshots. |
| `browser-testing` | `/frontend:browser-testing [URL, flow to check, or e2e spec file]` | Verifies web UI changes in a real browser with evidence (console, network, screenshots from phone to desktop widths), and writes, fixes or de-flakes end-to-end tests, Playwright by default. |
| `accessibility-review` | `/frontend:accessibility-review [url \| component or file path \| pr-number]` | Reviews and fixes web UI accessibility against WCAG 2.2 AA (axe, a scripted keyboard walk, manual keyboard and screen-reader passes), tying each finding to a criterion, an element, the users it blocks, and a fix. |

The frontend skills' bundled scripts need Node.js, and the ones that drive a browser also need Playwright (and `@axe-core/playwright` for the accessibility scan) from a project or scratch directory. The skills ask before adding anything to your project, and can use a scratch directory instead.

Bundled shell scripts (in `debug-root-cause`, `verify-before-done`, `git-worktrees` and `respond-to-review`) need bash; on Windows, use Git Bash or WSL. The Python scripts need only Python 3's standard library.

### `skill-dev`

| Skill | Invoke | What it does |
|---|---|---|
| `create-skill` | `/skill-dev:create-skill [skill idea, or path to an existing skill]` | Creates or fixes a Claude Code skill, measuring triggering in fresh sessions and output against a no-skill baseline before it ships. |

---

## Optional MCP servers

No skill here requires an MCP server. Two of them pick one up when it is connected, and work without it otherwise. The skills never install or configure a server on their own; they may offer the command and ask first.

### Context7 (for `implementation:docs-lookup`)

A third-party hosted index of library documentation. Without it, `docs-lookup` reads the official docs and the installed package source for the version the project pins. Pick one setup:

```bash
# Plugin from Anthropic's official marketplace (hosted server, works anonymously at shared rate limits)
claude plugin install context7@claude-plugins-official

# Or register the hosted server yourself with an API key from the Context7 dashboard
claude mcp add --scope user --header "Authorization: Bearer YOUR_API_KEY" --transport http context7 https://mcp.context7.com/mcp

# Or run the local server over stdio
claude mcp add --scope user context7 -- npx -y @upstash/context7-mcp --api-key YOUR_API_KEY
```

The vendor also offers a setup CLI (`npx ctx7 setup --claude`) and its own marketplace (`/plugin marketplace add upstash/context7`, then `/plugin install context7@context7-marketplace`). Setup flows for hosted services change, so check [the vendor's Claude Code instructions](https://context7.com/docs/clients/claude-code) before running these. Never commit an API key: at project scope, reference an environment variable from `.mcp.json` instead. Queries go to the vendor's service, so `docs-lookup` keeps them generic and does not send it the names or symbols of private packages unless your team indexed them there. The skill's `references/context7-setup.md` has the details.

### Playwright or Chrome DevTools (for `frontend:browser-testing`)

Browser automation servers. Without one, `browser-testing` falls back to its bundled page smoke test, the Playwright CLI, or a short throwaway script.

```bash
# Playwright MCP (from the Playwright team)
claude mcp add playwright npx @playwright/mcp@latest

# A typical verification setup: headless, nothing persisted, signed in from a saved state, request mocking on
claude mcp add playwright -- npx @playwright/mcp@latest --headless --isolated \
  --storage-state /tmp/pw-verify/auth.json --caps network

# Chrome DevTools MCP (from the Chrome DevTools team; adds performance traces, Lighthouse, CSS inspection)
claude mcp add chrome-devtools --scope user npx chrome-devtools-mcp@latest
```

Put server flags after `--` so the client does not try to parse them. `--storage-state` is only honored together with `--isolated`. The skill's `references/browser-drivers.md` lists the flags and capability groups, and was checked against Playwright 1.64, `@playwright/mcp` 0.0.83 and `chrome-devtools-mcp` 1.10. Prefer a server with an isolated profile: one attached to your everyday browser acts as you.

After adding any server, start a new session and confirm it with `claude mcp list` (or `/mcp` inside a session).

---

## Example prompts

You do not need to name a skill. Prompts like these load it on their own. Generic phrasings such as "review this" or "simplify this" can go to Claude Code's built-in commands instead (see [Built-in commands](#skill-catalog) above), so the review and simplify examples below are worded to match these skills, and the explicit form always works.

**implementation**

- `brainstorm-spec`: "Rough idea: let users schedule posts in advance. Let's brainstorm it properly before anyone writes code."
- `plan-feature`: "Plan how we add CSV export to the reports page and break it into PRs."
- `build-feature`: "Add a 'duplicate project' action to the projects list. It should copy settings and members but not the history. Go ahead and implement it." It pauses for your answers and a design choice before editing, and asks before pushing. Say "just build it, no questions" to have it pick its recommended defaults, log them as assumptions, and run straight through (it still asks about anything that could lose data, widen access, break a contract or move money).
- `execute-plan`: "docs/plans/search-reindex.md has been approved. Implement it task by task."
- `tdd`: "Use TDD to add a discount rule: 10% off orders over $200, never on gift cards."
- `debug-root-cause`: "This test fails about 1 in 20 runs on my machine. Find the root cause." / "It got slower after the framework upgrade. Which commit broke it?"
- `refactor-safely`: "Split this 900-line OrderService class before I add the refund feature."
- `simplify-code`: "The endpoint works now, but the code you wrote is bloated. Simplify it in test-gated batches without changing behavior." (or `/implementation:simplify-code`)
- `docs-lookup`: "Is useFormState still the current hook in the React version this app uses?" / "Use context7 to check how to add auth middleware in our Next.js app."
- `verify-before-done`: "Are we done? Make sure everything actually passes before I hand this off."

**review-suite**

- `pr-review`: "Review PR 482 and give me a merge verdict with severity-rated findings." / "Is my branch ready to merge?" (or `/review-suite:pr-review 482`)
- `secure-code-review`: "Trace untrusted input through this upload endpoint. Can a user read another user's files?" (or `/review-suite:secure-code-review`)
- `performance-review`: "Will this scale to 10x traffic? Look for N+1s across the PR."
- `parallel-review`: "Review this branch from every angle before we ship it. Get several reviewers on it."

**data-api**

- `api-design`: "Design the API for creating and listing invoices, including pagination and errors." / "Is this response change breaking for clients?"
- `db-migration-safety`: "Add a NOT NULL `region` column to the users table, which has 80M rows." / "Is this migration safe to run during a deploy?"
- `query-review`: "Why is this query slow? Here is the EXPLAIN ANALYZE output." / "The monthly totals are doubled. What is wrong with this SQL?"

**workflow**

- `commit-message`: "Commit this, split into sensible atomic commits."
- `pr-description`: "Open a PR for this branch with a proper description."
- `respond-to-review`: "Alice left 12 comments on my PR #57. Go through them and fix whatever is legit."
- `git-worktrees`: "I want to review PR #482 locally and run its tests, but I'm in the middle of something and my tree is dirty."
- `ci-failure-triage`: "CI is red on my PR but it passes locally. What's going on?"
- `adr-writer`: "Write an ADR recording why we picked PostgreSQL over MongoDB." / "Supersede ADR 12."
- `incident-postmortem`: "Write up yesterday's checkout outage. Here is the incident channel export."

**frontend**

- `ui-design-direction`: "Restyle the analytics dashboard. It looks like every other admin template."
- `browser-testing`: "Click through the checkout flow on localhost:3000 and make sure the coupon field still applies the discount." / "This e2e test is flaky. Fix it."
- `accessibility-review`: "Can a keyboard-only user get through our signup modal?" / "Is #6b7280 on #f9fafb enough contrast for body text?"

**skill-dev**

- `create-skill`: "I keep pasting the same prompt every time I review Terraform plans. Turn it into a proper skill." / "My skill fires whenever anyone mentions SQL. Fix its description."

---

## How skills are tested

Each skill carries trigger evals (prompts that should and should not load it, including near misses that belong to a sibling) and behavior evals (realistic tasks with checkable expectations, graded with and without the skill). [docs/testing-skills.md](docs/testing-skills.md) explains how to run them, and [CONTRIBUTING.md](CONTRIBUTING.md) covers the repository layout and the validators CI runs.

---

## Contributing

Contributions are welcome: bug reports, sharper descriptions, new evals, reference-file additions, and new skills. Start with [CONTRIBUTING.md](CONTRIBUTING.md), which has the skill conventions, the pull request flow and the review bar, and follow the [Code of Conduct](CODE_OF_CONDUCT.md).

- **Looking for a first task?** Browse issues labelled [`good first issue`](https://github.com/sravansai04/engineering-skills/labels/good%20first%20issue), or the scoped ideas in [docs/roadmap.md](docs/roadmap.md).
- **Questions and ideas** go to [GitHub Discussions](https://github.com/sravansai04/engineering-skills/discussions): **Q&A** for help using a skill, **Ideas** for a new skill before anyone writes it. [SUPPORT.md](SUPPORT.md) says what a good bug report contains.
- **Writing a skill?** `skill-dev:create-skill` drafts it in this repository's conventions and measures it before you open the pull request.

---

## Security

These skills run inside a coding agent with access to your files, shell and credentials, so a skill that leads the agent into unsafe behavior counts as a vulnerability. Report it privately as described in [SECURITY.md](SECURITY.md), never in a public issue.

---

## License

[MIT](LICENSE)
