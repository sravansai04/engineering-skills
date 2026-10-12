# Contributing

Thanks for improving these skills. Keep changes small and focused: one skill, or one fix across skills, per pull request.

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md). Questions go to [GitHub Discussions](https://github.com/sravansai04/engineering-skills/discussions) (see [SUPPORT.md](SUPPORT.md)), and security problems are reported privately as described in [SECURITY.md](SECURITY.md), never in a public issue.

## Ways to contribute

- **Report a bug.** A skill gives wrong advice, names a command or flag that doesn't exist, or a script fails. [SUPPORT.md](SUPPORT.md) lists what to include. If a skill loads when it shouldn't, or never loads, use the **Skill improvement** form instead.
- **Improve a skill.** Correct a fact, add a language, framework or tool to a reference file's table, or sharpen a description so the skill triggers more precisely.
- **Add evals.** New behavior prompts with checkable expectations, or near-miss trigger prompts that separate two sibling skills. They make every later change safer.
- **Propose a new skill.** Start a thread in the **Ideas** discussion category before writing it, and check it for overlap with the `skill-dev:create-skill` skill: reshaping an idea is cheaper than reshaping a finished pull request.
- **Improve the tooling and docs.** The validator, the CI workflows, and the guides under `docs/`.
- **Help others.** Answer questions in Discussions, or review open pull requests: a second reader who checks a command or a claim is always useful.

[docs/roadmap.md](docs/roadmap.md) lists scoped ideas, from good first issues to new skills. Comment on an issue before starting on it, so two people don't build the same thing.

## The plugins

Skills are grouped by the moment the user is in, not by topic. Put a new skill where people will look for it at that moment.

| Plugin | Holds skills that... |
|---|---|
| `implementation` | write or change code: shape an idea, plan, build, test-drive, debug, refactor, simplify, check docs, verify before done |
| `review-suite` | evaluate code someone wrote: pull requests, security, performance, multi-reviewer passes |
| `data-api` | design or check API contracts, database migrations and queries |
| `workflow` | produce the team artifacts around code: commits, PR descriptions, review responses, worktrees, CI triage, ADRs, postmortems |
| `frontend` | shape and check user interfaces: visual direction, browser testing, accessibility |
| `skill-dev` | author, test and maintain skills themselves |

A new plugin needs a gap no existing plugin's moment covers, a `plugin.json`, a marketplace entry, and agreement in a Discussion first.

## Development setup

You need git, Python 3.8 or later (the validator uses only the standard library), and the Claude Code CLI (`claude --version`). `gh` and `jq` help with the commands below and in the testing guide. Node.js is needed only to run the frontend skills' scripts, and Python 3.11 or later only to run the Agent Skills reference validator locally (CI runs it anyway).

```bash
gh repo fork sravansai04/engineering-skills --clone   # or fork on GitHub, then git clone your fork
cd engineering-skills

python3 -I scripts/validate_skills.py                 # the repository validator
claude plugin validate . --strict                     # the marketplace manifest
for p in plugins/*/; do claude plugin validate "$p" --strict; done   # each plugin and its skills' frontmatter
```

Set up the local denylist described under **Content rules** below before your first commit, so the validator also scans for names that must never be published. To try your working copy, load the plugins for one session: `claude --plugin-dir ./plugins` loads every plugin in the folder, and `claude --plugin-dir ./plugins/<plugin>` loads one.

## Pull request flow

1. **Agree on the change.** For anything beyond a small fix, comment on the issue (or open one) first; for a new skill, start in Discussions.
2. **Branch in your fork** from an up-to-date `main`, with a short descriptive name: `git switch -c fix-query-review-null-join`.
3. **Make the change** following the conventions below. Keep it to one skill, or one fix across skills.
4. **Test it.** Run the checks in [Before opening a pull request](#before-opening-a-pull-request), then the skill's trigger and behavior evals as described in [docs/testing-skills.md](docs/testing-skills.md).
5. **Bump and record.** If the change ships to users, bump the plugin's version (item 7 of the review bar) and add a line under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md). [docs/maintainers.md](docs/maintainers.md) explains which bump to pick.
6. **Open the pull request** against `main` and fill in the template GitHub pre-fills (`gh pr create --web` opens it in the browser). The description must show a **before and after on at least one eval prompt**, in the Evidence format of [docs/testing-skills.md](docs/testing-skills.md) (section 6); for a small wording fix, the template's short Prompt, Before and After lines are enough. Leave "Allow edits by maintainers" on.
7. **Get CI green.** Every pull request runs the repository checks; all of them must pass before review. If this is your first contribution, a maintainer approves the CI run before it starts.
8. **Respond to review**, then a maintainer squash-merges it.

By contributing, you agree that your contribution is licensed under the [MIT License](LICENSE) that covers this repository.

## Related documents

- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md): expected behavior, and how to report a problem privately.
- [SECURITY.md](SECURITY.md): what counts as a vulnerability here, and how to report one.
- [SUPPORT.md](SUPPORT.md): where to ask questions and what a good bug report contains.
- [docs/testing-skills.md](docs/testing-skills.md): trigger and behavior evals, run in fresh sessions.
- [docs/roadmap.md](docs/roadmap.md): the direction of the project and contribution ideas by size.
- [docs/maintainers.md](docs/maintainers.md): versions and releases, labels, triage targets.

## Skill authoring conventions

The skills follow the open [Agent Skills](https://agentskills.io) standard, so they also load in OpenCode, Codex, Cursor, Gemini CLI, GitHub Copilot and other agents that support it. Claude Code stays the primary target: the rules below keep a skill working at full strength there while nothing in it breaks elsewhere.

**Layout**

- One skill per folder: `plugins/<plugin>/skills/<skill-name>/SKILL.md`. The frontmatter `name` equals the folder name: lowercase letters and digits in hyphen-separated runs (no leading, trailing or doubled hyphen), at most 64 characters.
- `SKILL.md` holds the workflow and stays under 500 lines. Longer detail goes in `references/` (one level deep), and every reference file is mentioned from `SKILL.md` together with when to read it.
- Bundled scripts live in `scripts/`, are referenced as `"${CLAUDE_SKILL_DIR}/scripts/<file>"` (quoted, so a path with spaces still works), print usage with both `-h` and `--help`, and use only what a typical developer machine already has (bash, POSIX tools, the Python 3 standard library). Every bundled script has a built-in self-check named `--selftest`; CI runs each one on Linux and macOS and fails on a script without one. Run Python scripts as `python3 -I`. Templates go in `assets/`.
- Keep `${CLAUDE_SKILL_DIR}` for paths into the skill folder rather than a relative `scripts/<file>`: Claude Code fills it in with the folder's absolute path, while a relative path depends on a working directory that varies. It is filled in only in `SKILL.md` and its `allowed-tools`, and other agents never fill it in. So a skill that uses it anywhere outside `allowed-tools` (the `SKILL.md` body, a reference, a script, an asset) carries this sentence once in the `SKILL.md` body, just before the first use, word for word: "`${CLAUDE_SKILL_DIR}` stands for this skill's folder, the directory that contains this SKILL.md. Claude Code fills it in; in other tools, use that folder's path." The validator fails without it. A reference file that shows a command with the variable also says, once, that it is not a shell variable and which path to use instead (the validator warns otherwise).
- A skill is self-contained: no links outside its own folder, so it still works when someone copies just that folder.

**Frontmatter**

- Use only the fields of the Agent Skills standard: `name`, `description`, `license`, `compatibility`, `metadata` (string keys and string values) and `allowed-tools`. Claude Code reads more (`when_to_use`, `disable-model-invocation`, `paths`, ...), but the standard's reference validator rejects any other field and other agents ignore it, so carry its intent in the body. The repository validator and the `skills-ref` CI job both fail on another key.
- `description` says what the skill does in one sentence, then when to use it with the three to five strongest phrasings people actually type ("review this PR", "why is this query slow"), then a short "Not for X (sibling)" list naming the skill that owns each nearby request. Use bare skill names there to save space. Keep it to about 450 characters: Claude Code fits every installed skill's description into one listing budget of about 1% of the context window, and when it overflows, the least-used skills lose their descriptions. The validator warns above 500 characters; 1024 is the hard limit. Put longer phrase lists in `evals/trigger-evals.json`, where they are tested.
- Write the description as a double-quoted string on one line (escape inner quotes as `\"`); a folded `>-` block is fine for an existing skill, and the validator parses both. Never put an XML-like tag in it: write `docs/plans/search.md`, not `docs/plans/<name>.md` (the validator fails on tags, because the open skill format rejects them).
- There is no `argument-hint`. It is a Claude Code-only autocomplete hint: other tools and the reference validator reject it as an unknown field. A skill that takes an argument says in the body what it accepts and what to do when there is none, and refers to it in words ("the arguments", "the PR number the user gave"). Never write Claude Code's `$ARGUMENTS` placeholder (or `$ARGUMENTS[N]`) in `SKILL.md` or a reference file: other agents show it as literal text, and Claude Code does not need it, because a skill with no placeholder gets the user's input appended at its end as `ARGUMENTS: <input>`. The validator fails on it.
- Add `compatibility` when the skill bundles scripts, or works best with a capability not every agent has: one line on what it needs (for example "bash, jq, and gh signed in"; "Node.js 20 or later and Playwright"; "an agent that can run subagents; without them the lanes run one after another"), at most 500 characters.
- `allowed-tools` is experimental in the standard: Claude Code honors it as pre-approval and other agents may ignore it, so it is a convenience, never a safety control. It pre-approves read-only commands only (`git diff`, `gh pr view`, the skill's own scripts), written as one comma-separated string of `Bash(command:*)` rules, the form the official plugins use. `git fetch` counts as read-only and may be listed by skills that need a remote ref: it downloads objects and updates remote-tracking refs, and never touches the working tree, local branches, or the remote. Anything that writes files (including `gh run download`), stages, commits, pushes, or posts must still ask for permission. A rule matches the start of the command, so write the command the way the rule spells it (`git diff ...`, not `git -c key=value diff ...`).

**Body**

- Use the same skeleton as the other skills: an opening paragraph, `## Workflow` with `### N. <verb phrase>` steps, then `## Report format` when the result is a report, `## Related skills`, and `## Reference files`. Report titles inside a template are H2 (`## Review: ...`); a standalone document a skill writes to a file (a postmortem, a plan, an ADR) may use H1.
- Write numbered steps in the imperative and give the reason behind each rule, so Claude can handle cases the rule did not anticipate.
- Prefer the project's own conventions and tools (its test command, migration tool, commit style) over a hard-coded stack. Where the stack matters, cover the common ones and say what to do for the rest.
- Include only what Claude would not do well by default. Cut generic advice.
- Name capabilities, not one agent's tools. Where a step relies on a tool only some agents have (subagents through Claude Code's Agent tool, AskUserQuestion, the task-list tools), name the capability first, the Claude Code tool as an example, and a fallback for agents without it: "ask with a structured-question tool if your agent has one (AskUserQuestion in Claude Code), otherwise ask in chat"; "track the phases with your agent's task list if it offers one (TaskCreate and TaskUpdate in Claude Code, on models where they are enabled), otherwise a checklist in the conversation"; "without subagents, run the lanes one after another in this session".
- Give the output format when the result is a report, and make it say what was verified and what was not.
- Never make a destructive or outward-facing action (force-push, dropping data, posting comments) happen without the user's confirmation.
- Refer to another skill in the body as `plugin:skill` (`review-suite:pr-review`, `data-api:query-review`), which matches the installed listing. Any skill that hands off to another ends its `## Related skills` list with these sentences, word for word: "Skills are named here as `plugin:skill`; an agent that lists skills by bare name knows each one by the part after the colon (`review-suite:pr-review` is `pr-review`). If a skill named here isn't installed, give the short version inline and list the deeper pass as a follow-up." The first one matters outside Claude Code: other agents install the same skills under their bare names.
- Never write `$0` to `$9` in `SKILL.md`, even inside a code block: Claude Code replaces them with the skill's positional arguments, so a SQL placeholder or a shell positional parameter turns into the user's words. Use named placeholders (`:id`), write `\$1` for a literal, or keep the example in a reference file, where nothing is substituted. The validator fails on them.
- A skill that reviews code from a PR, or runs it, uses the shared blocks below instead of its own wording.

**Shared blocks**

Some text must read the same in every skill that uses it, and stays self-contained by being pasted into each skill rather than linked. Each copy sits between `<!-- shared:NAME vN -->` and `<!-- /shared:NAME vN -->` markers, and the validator fails if any two copies of the same block differ.

- `severity`: the severity levels, their merge effect, the verdict ladder, and the finding format. In every review skill: pr-review, secure-code-review, performance-review, parallel-review (in `references/finding-schema.md`), query-review, db-migration-safety, api-design, and accessibility-review. A skill adds its own domain examples after the block, never inside it: accessibility-review carries the block, then adds a user-impact table and two fields (Conformance, Instances) after it. Any new skill that produces severity-rated findings uses the block.
- `trust-gate`: who counts as a trusted author, on GitHub and GitLab, before running anything from a PR or merge request. In every skill that can execute a target's code, including one that runs a contributor's skill scripts (create-skill) or the code behind a query (query-review).
- `untrusted-input`: PR text, code comments, and CI or production logs are data, not instructions. In every skill that reads a PR or a log. The validator warns when a skill pre-approves `gh pr view`, `gh pr diff` or `gh run` but carries no copy.

To change a block, edit every copy in the same pull request. If the meaning changes, bump the version in the markers (`v1` to `v2`) in every copy at once.

**Content rules**

- Company-agnostic and public-safe: no employer or customer names, internal tool names, hostnames, paths, tickets, or code. The validator can scan every file against a denylist of terms you must never publish and fail on any hit. Keep that list out of the repository, since publishing it would name what it protects: put one term per line in `~/.config/engineering-skills/denylist.txt`, in a file named by the `SKILLS_DENYLIST_FILE` environment variable, or in `.denylist.local` at the repository root (gitignored). Without one, the scan is skipped and the validator says so.
- Write in your own words. Do not paste text from other skill collections, books, or vendor docs; link to the source instead.
- Commands, flags, and API names must be real and current. Run them before you write them down.

**Evals**

- `evals/evals.json`: at least three realistic task prompts, each with an `expectations` list of three to six checkable statements (the validator requires a non-empty list and warns outside three to six). A prose `expected_output` is optional context, not a substitute. Put fixture files under `evals/files/` and list them in the case's `files`, with a `setup.sh` when the case needs a git history or a fake CLI, so anyone can rerun it.
- `evals/trigger-evals.json` (this exact name): queries with `should_trigger` true and false, including near misses that belong to a sibling skill. Every `false` case names where the query belongs in `should_route_to`: a `plugin:skill`, or `none (reason)` when no skill should load (the validator warns when it is missing). When two skills could claim a phrasing, add it to one as true and to the other as false.
- Fixtures sometimes need credentials, hostnames, or prices that look real, for example to test that a skill refuses to commit a secret. Make them obviously fake (`example-not-a-real-key-0000`, `*.internal`, `@example.com`), or build token-shaped strings at runtime, so a secret scanner or a reader doesn't mistake them for a leak.

## The review bar

A skill change is merged when:

1. **It is correct.** Every command, flag, threshold, and claim is accurate and has been checked, not recalled.
2. **It triggers precisely.** It loads for its own requests and stays out of its siblings' requests, and the trigger evals cover both sides.
3. **It earns its place.** Following the skill produces visibly better work than Claude does without it. Show a before and after on at least one eval prompt in the PR description.
4. **It is safe.** No secrets, no destructive defaults, read-only `allowed-tools`.
5. **It is consistent.** Same structure, tone, and terminology as the neighbouring skills.
6. **The checks pass.** The repository validator, the Agent Skills reference validator (`skills-ref`) and `claude plugin validate --strict` pass for every touched plugin.
7. **The version is bumped.** Raise `version` in the plugin's `plugin.json` and in its entry in `.claude-plugin/marketplace.json`, keeping the two identical. Users do not receive changes until the version changes.

## Repository layout

```text
engineering-skills/
├── .claude-plugin/marketplace.json   # the marketplace catalog: lists the six plugins and their versions
├── plugins/<plugin>/
│   ├── .claude-plugin/plugin.json    # plugin manifest: name, description, version, author, keywords
│   └── skills/<skill>/
│       ├── SKILL.md                  # frontmatter + core instructions (under 500 lines)
│       ├── references/               # detail Claude reads on demand, one level deep, each linked from SKILL.md
│       ├── scripts/                  # optional helper scripts, each with --help and --selftest
│       ├── assets/                   # optional templates
│       └── evals/                    # evals.json (task cases), trigger-evals.json, files/ (fixtures)
├── scripts/
│   ├── validate_skills.py            # repository validator (Python 3 standard library only)
│   └── setup_labels.sh               # creates the issue labels (maintainers)
├── docs/                             # testing guide, roadmap, maintainer process
└── .github/                          # CI workflows, issue, discussion and pull request templates
```

Plugins use the default layout: Claude Code discovers every `skills/<name>/SKILL.md` without listing skills in `plugin.json`, and namespaces each one under the plugin name.

## What the checks cover

`python3 -I scripts/validate_skills.py` needs only Python 3.8 or later. For every skill it checks that:

- the frontmatter parses and uses only the Agent Skills fields (`name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`), so `argument-hint` and the other Claude Code-only fields fail; `name` matches the folder and the standard's rule (lowercase letters and digits in hyphen-separated runs, at most 64 characters);
- `description` is present, at most 1024 characters (a warning above 500), and holds no XML-like tag;
- `SKILL.md` has no unescaped `$0` to `$9` and is under 500 lines;
- neither `SKILL.md` nor any reference file contains `$ARGUMENTS` or `$ARGUMENTS[N]`;
- a skill that uses `${CLAUDE_SKILL_DIR}` outside `allowed-tools` (in `SKILL.md`, `references/`, `scripts/` or `assets/`) explains it with the exact sentence given under Layout, in the `SKILL.md` body;
- every relative Markdown link, every backticked `references/`, `scripts/` or `assets/` path and every `${CLAUDE_SKILL_DIR}/...` path resolves inside the skill, and every file in `references/` is mentioned from `SKILL.md`;
- `evals/evals.json` gives every eval a non-empty `expectations` list, and `evals/trigger-evals.json` has queries on both sides.

It also checks that `marketplace.json`, every `plugin.json` and every other JSON file parse, that every marketplace source exists and every plugin folder is listed, that versions agree, that every copy of a shared block is identical, and that every label the issue forms and Dependabot apply is created by `scripts/setup_labels.sh`. It warns about expectation counts outside three to six, `false` trigger cases with no `should_route_to`, an unexplained `${CLAUDE_SKILL_DIR}` in a reference file's commands, and a skill that reads PRs or CI runs without the untrusted-input block. With a local denylist (see Content rules) it also scans every file and path for those terms. It exits `0` when clean and `1` with a file-and-line report otherwise; `--selftest` checks its YAML parser, its content patterns, and each portability rule against throwaway skills.

`claude plugin validate` complements it: validating `.` checks the marketplace and each `plugin.json`, and validating each plugin directory also parses the skills' frontmatter, so run both. The **Agent Skills spec (skills-ref)** job runs the standard's reference validator, [`skills-ref`](https://pypi.org/project/skills-ref/) (pinned, with its command `agentskills`), on every skill folder: it parses the frontmatter with a stricter YAML parser and checks the allowed fields, the name rules and the length limits the way other agents read them. CI runs all of this on every pull request, plus every bundled script's `--selftest` on Linux and macOS, `shellcheck` and a dry run of `scripts/setup_labels.sh`, and actionlint on the workflow files.

## Before opening a pull request

```bash
python3 -I scripts/validate_skills.py
claude plugin validate . --strict
for p in plugins/*/; do claude plugin validate "$p" --strict; done
for f in plugins/*/skills/*/scripts/*.sh; do bash "$f" --selftest > /dev/null || echo "FAILED: $f"; done   # and the .py and .mjs scripts you touched

# Optional, CI runs it too: the Agent Skills reference validator (Python 3.11 or later)
python3 -m venv .venv && .venv/bin/pip install skills-ref==0.1.1
for d in plugins/*/skills/*/; do .venv/bin/agentskills validate "$d" || echo "FAILED: $d"; done
```

Then load the plugin locally (`claude --plugin-dir ./plugins/<plugin>`) and run a few of the skill's eval prompts to confirm it triggers and behaves as intended.
