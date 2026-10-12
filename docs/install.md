# Installing and setup

The [README](../README.md) has the two-line install. This page has everything else: the Claude Code details, team setup, updates, other agents, and the optional MCP servers two skills can use.

- [Claude Code](#claude-code)
  - [Skill listing budget](#skill-listing-budget)
  - [Installing from a private fork or mirror](#installing-from-a-private-fork-or-mirror)
  - [Share it with everyone on a project](#share-it-with-everyone-on-a-project)
  - [Updates](#updates)
  - [Copy individual skills](#copy-individual-skills)
  - [Try it without installing](#try-it-without-installing)
  - [Built-in commands with similar names](#built-in-commands-with-similar-names)
- [Other agents](#other-agents)
- [Optional MCP servers](#optional-mcp-servers)
- [Requirements for bundled scripts](#requirements-for-bundled-scripts)

## Claude Code

From your shell, add the marketplace once, then install the plugins you want. `implementation` and `review-suite` are a good start:

```bash
claude plugin marketplace add sravansai04/engineering-skills
claude plugin install implementation@engineering-skills
claude plugin install review-suite@engineering-skills
```

On recent CLI versions, `claude plugin install implementation --marketplace sravansai04/engineering-skills` adds the marketplace and installs in one step (`claude plugin install --help` shows whether yours has `--marketplace`). Inside a Claude Code session the same steps are `/plugin marketplace add sravansai04/engineering-skills` and `/plugin install implementation@engineering-skills`.

Restart Claude Code (or run `/reload-plugins`) and check with `claude plugin list`. Then type `/` in a session and look for the `/implementation:` and `/review-suite:` entries.

To install all six:

```bash
for p in implementation review-suite data-api workflow frontend skill-dev; do
  claude plugin install "$p@engineering-skills"
done
```

### Skill listing budget

Read this before installing all six on a 200k-context model.

Claude Code lists every installed skill's description in a budget of 1% of the model's context window, counted in characters: about 8,000 on a 200k-token model, about 40,000 on a 1M-token model. Your personal skills and other plugins share it. When the listing overflows, the skills you have used least keep only their names, and right after an install those are these skills, so their trigger phrases vanish and automatic selection quietly stops picking them. All 28 descriptions here, names included, come to about 14,000 characters.

- **1M-context models:** everything fits; install what you like.
- **200k-context models:** install only the plugins you use, or raise the budget: add `"skillListingBudgetFraction": 0.02` to `~/.claude/settings.json`, or set `SLASH_COMMAND_TOOL_CHAR_BUDGET=20000` in your environment.
- **To check:** the Skills row of `/context` in a session, and `claude plugin details <plugin>` for each installed plugin's always-on token cost.

### Installing from a private fork or mirror

Claude Code clones a marketplace with your own git credentials and never prompts for them, so for a private copy set up one of these first:

- **HTTPS (simplest):** `gh auth login`, then `gh auth setup-git`, so the git credential helper holds a GitHub credential.
- **SSH:** a GitHub SSH key loaded in `ssh-agent` (no passphrase prompt) with `github.com` already in `known_hosts`.

With the `owner/repo` form, Claude Code tries SSH first and falls back to HTTPS. If your machine has no GitHub SSH key, set `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1` to skip the SSH attempt. The public repository needs none of this.

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

You only receive a new copy of a plugin when its `version` changes. [CHANGELOG.md](../CHANGELOG.md) records what changed.

### Copy individual skills

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

### Built-in commands with similar names

Claude Code ships its own `/code-review` (also reachable as `/review`), `/security-review` and `/simplify`, and they can win automatic selection for generic phrasings such as "review this", "security review this" or "simplify this". When you want these skills, invoke them explicitly (`/review-suite:pr-review`, `/review-suite:secure-code-review`, `/implementation:simplify-code`) or name the skill in your prompt.

## Other agents

These are standard [Agent Skills](https://agentskills.io), so they load in any tool that supports the standard. The [`skills` CLI](https://github.com/vercel-labs/skills) installs them:

```bash
npx skills add sravansai04/engineering-skills --list                 # preview the skills
npx skills add sravansai04/engineering-skills                        # pick skills and agents interactively
npx skills add sravansai04/engineering-skills -a codex -s pr-review  # one agent, one skill
```

For Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot, Cline, Amp and others it installs into the project's shared `.agents/skills/`. `-a <agent>` (`opencode`, `codex`, ...) targets one agent, `-s <skill>` picks skills by name, and `-g` installs for your user instead of the project.

- **By hand:** copy a whole skill folder (not only `SKILL.md`) into `.agents/skills/` or the tool's own skills folder. OpenCode also reads `.claude/skills/`.
- **ChatGPT:** on plans that have Skills, upload a skill folder under Skills. If it asks for an archive, zip the folder itself, so the archive holds one folder with `SKILL.md` directly inside (for example `cd plugins/review-suite/skills && zip -r pr-review.zip pr-review`). Codex is the better fit for skills that need a repository, git or a terminal.

What differs outside Claude Code:

- The plugin marketplace and the `/plugin:skill` names are Claude Code only; other agents know each skill by its bare name (`pr-review`).
- Paths to a skill's bundled files are written `${CLAUDE_SKILL_DIR}/...`, which only Claude Code fills in; every skill that uses it says to read it as the skill's own folder.
- `allowed-tools` is how Claude Code pre-approves a skill's read-only commands; other agents may ignore it and follow their own approval settings, which may run commands without asking. The skills' own rules (confirm before anything outward-facing) apply either way.
- `parallel-review`, `build-feature` and `execute-plan` run their subagent lanes one after another when the agent can't run subagents.

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

## Requirements for bundled scripts

Skills work without their scripts, but the scripts make several checks faster and more reliable.

- **frontend:** the bundled scripts need Node.js, and the ones that drive a browser also need Playwright (and `@axe-core/playwright` for the accessibility scan) from a project or scratch directory. The skills ask before adding anything to your project, and can use a scratch directory instead.
- **Shell scripts** (in `debug-root-cause`, `verify-before-done`, `git-worktrees` and `respond-to-review`) need bash; on Windows, use Git Bash or WSL.
- **Python scripts** need only Python 3's standard library.
