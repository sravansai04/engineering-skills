# Getting help

## Questions

Ask in [GitHub Discussions](https://github.com/sravansai04/engineering-skills/discussions), in the **Q&A** category: how to install a plugin, which skill fits a task, why a skill behaves the way it does, how to adapt one to your stack. Mark the reply that solved it as the answer so the next person finds it. Search first; the question may already be answered there or in the [README](README.md).

Ideas for new skills or bigger changes go in the **Ideas** category, where they can be discussed before anyone writes code. [docs/roadmap.md](docs/roadmap.md) lists ideas that are already welcome.

Please don't use issues for questions, and don't contact the maintainer privately for support: answers in public help everyone who searches later.

## Bug reports

A bug is something in this repository that is wrong: a skill that gives incorrect advice or a command that doesn't exist, a script that fails, a broken link, an install step that doesn't work. [Open an issue](https://github.com/sravansai04/engineering-skills/issues/new/choose) and pick the bug report template. If a skill loads when it shouldn't, or never loads, use the **Skill improvement** form instead.

Include:

- **Claude Code version**: the output of `claude --version`.
- **Plugin and version**: which plugin, and its version from `claude plugin list`. If you copied a skill folder instead of installing the plugin, say so and give the commit you copied it from.
- **Skill**: which skill, and whether you invoked it by name (`/review-suite:pr-review`) or it loaded on its own. If you expected it to load and it didn't, say that.
- **The prompt**: exactly what you typed. Trim private code, but keep enough for someone else to reproduce the problem.
- **Expected vs actual**: what you expected the agent to do, and what it did. Paste the relevant part of the output.
- **Environment**: operating system, the model if you chose one, and other plugins or personal skills you have installed. Other skills compete for the same requests, so they matter for "it never triggers" reports.

For a skill that never loads, also check `/context` in a session: when the skill listing is over its budget, Claude Code drops some descriptions, and the README explains how to raise the budget.

Remove secrets, tokens, internal hostnames and customer data from anything you paste.

## Security problems

Do not report vulnerabilities in public issues or discussions. Follow [SECURITY.md](SECURITY.md) to report privately.

## Conduct

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md), which also explains how to report a problem privately.

## What to expect

This project is maintained by one person in their own time. Most questions get a reply within a week, and the [maintainer guide](docs/maintainers.md) describes how issues are triaged. Answers from other community members are welcome and often faster.

Problems with Claude Code itself (installation, login, billing, the CLI or the model) are outside this repository; use Claude Code's built-in `/feedback` command or Anthropic's support channels for those.
