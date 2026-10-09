# Security policy

This repository ships instructions and helper scripts that run inside a coding agent with access to a developer's files, shell, credentials and accounts. A flaw here does not need a server to be exploitable: a skill that tells the agent to run the wrong thing, or a script that trusts the wrong input, runs with the full rights of whoever installed it. Reports of that kind are taken as seriously as a vulnerability in conventional code.

## Supported versions

Only the latest release is supported: the newest tagged release and the current default branch, which is what `claude plugin marketplace update` delivers. Fixes are released as new plugin versions, not backported. If you copied a skill folder by hand instead of installing it, copy the fixed folder again.

| Version | Supported |
|---|---|
| Latest release (each plugin's current `version`) | Yes |
| Anything older | No: update the plugin |

## What is in scope

- **Skills that can lead the agent into unsafe behavior.** For example, a skill whose instructions:
  - run code from an untrusted pull request, fork or archive without checking who wrote it;
  - treat text from a PR, issue, code comment, CI log, web page or tool output as instructions to follow (prompt injection made easier by the skill);
  - make a destructive or outward-facing action happen without the user's confirmation: force-pushing, deleting branches or data, dropping tables, posting comments, publishing, sending messages, spending money;
  - expose secrets: printing tokens or keys, committing `.env` files or credentials, or pasting private data into a public place.
- **`allowed-tools` over-grants.** A skill's frontmatter pre-approves a command that writes, pushes, posts or deletes, or a rule whose prefix matches more than intended. A rule matches the start of the command, so a rule such as `Bash(gh api:*)` also approves state-changing API calls.
- **Bundled scripts** under any skill's `scripts/` and the repository's own `scripts/`: command or argument injection, unsafe handling of paths, temporary files or archives, network access a script does not need, or executing content it downloaded or read.
- **CI and repository automation** under `.github/`: workflows that run untrusted pull request code with secrets or a write-scoped token, script injection through issue, PR or branch text interpolated into a `run:` step, token permissions broader than the job needs, and third-party actions that are not pinned.
- **Sensitive content in the repository**: a real credential, private hostname, internal name or personal data in a skill, reference file or eval fixture.

## What is out of scope

- Vulnerabilities in Claude Code itself, in Claude models, or in the plugin system: report those to Anthropic through its [responsible disclosure policy](https://www.anthropic.com/responsible-disclosure-policy).
- Vulnerabilities in third-party tools a skill tells you to run (test runners, linters, scanners, browsers): report those to their maintainers. If a skill recommends a tool version that is known to be vulnerable, that part is in scope.
- A model making a mistake that no instruction in this repository caused or made more likely. A skill whose wording makes such a mistake more likely is in scope.
- Findings that need an already-compromised machine, or a user who deliberately edited a skill to remove its safeguards.
- Fixture files under `evals/files/` that are intentionally vulnerable or contain obviously fake secrets (for example `example-not-a-real-key-0000`), as long as nothing runs them outside a test.

If you are unsure, report it privately anyway.

## How to report

Do not open a public issue, pull request or discussion for a vulnerability.

1. Go to the repository's **Security** tab (labelled **Security and quality** in newer GitHub layouts).
2. Choose **Report a vulnerability**. This uses GitHub's private vulnerability reporting: the report is visible only to you and the maintainer.
3. Include:
   - the skill, script or workflow, with its path and the plugin version (`version` in the plugin's `.claude-plugin/plugin.json`);
   - your Claude Code version (`claude --version`) and the model, if a skill is involved;
   - the prompt or input that triggers the problem, and what the agent or script then does;
   - the impact: what an attacker gains or what the user loses;
   - a fix, if you have one in mind.

Never include real secrets, tokens or personal data in a report; redact them or use fakes.

## What to expect

This project has a single maintainer and response times are best effort:

| Step | Target |
|---|---|
| Acknowledgement | Within 5 business days |
| First assessment (confirmed, needs more information, or not a vulnerability) | Within 10 business days |
| Fix or mitigation for a confirmed critical or high issue | Within 30 days, sooner where possible |
| Fix for a confirmed medium or low issue | In a following release |

You will be kept up to date in the advisory thread. Once a fix is released, the advisory is published with credit to you, unless you ask to stay anonymous. Please keep the details private until then; if a fix needs longer than the targets above, the maintainer will say so in the thread and agree a disclosure date with you.
