# Message Format Reference

Read the section you need. The core rules (subject, type table, body, footer basics) are in
SKILL.md and aren't repeated here.

## Contents

1. Conventional Commits parsing rules
2. Ambiguous types
3. Choosing a scope
4. Breaking changes
5. Reverts
6. Security fixes
7. Trailer reference
8. Other house styles
9. Detecting enforced conventions
10. Git message-handling gotchas

---

## 1. Conventional Commits parsing rules

These rules come from the Conventional Commits 1.0.0 specification, summarized here. They are
what tools actually parse.

- **Header.** A type, an optional `(scope)`, an optional `!`, then a colon, a space, and the
  description. The scope is a noun naming an area of the codebase.
- **Body.** Optional and free-form. It starts after exactly one blank line and may run to
  several paragraphs.
- **Footers.** Optional. They start after a blank line, and each is a token followed by
  `: ` or ` #`, then a value (`Refs: #12`, `Fixes #12`). Write a space inside a token as a
  hyphen (`Reviewed-by`). The one exception is `BREAKING CHANGE`, which may keep its space.
  `BREAKING-CHANGE` means the same thing.
- **Case.** Parsers must treat everything as case-insensitive except `BREAKING CHANGE`, which
  must be uppercase. Lint configs are stricter: commitlint's conventional config requires a
  lowercase type.
- **Types.** The spec defines only `feat` and `fix`. The common extended set (`build`,
  `chore`, `ci`, `docs`, `perf`, `refactor`, `revert`, `style`, `test`) is the `type-enum` of
  `@commitlint/config-conventional`, which derives from the Angular convention. Angular's own
  guidelines omit `chore` and `style`. A repo can narrow or extend the list in its lint config.

## 2. Ambiguous types

| Situation | Type | Reasoning |
|---|---|---|
| A refactor that also fixes a bug | `fix`, and say the restructuring was needed | Users see changed behavior. Split it if the two can be separated. |
| A performance change that alters output or ordering | `fix` or `feat` | `perf` promises identical behavior |
| Tests added for existing, unchanged code | `test` | No production change |
| Tests that ship with a fix or feature | Part of that commit | Tests aren't a separate logical change |
| A config value change that alters runtime behavior | `fix` or `feat` | It's a behavior change, whatever the file type |
| A runtime dependency bump | Follow the repo. A common split: `fix(deps)` for runtime deps, `chore(deps)` or `build(deps)` for dev tooling | Dependency bots often default to this. Look at their past commits. |
| A security patch via a dependency bump | `fix(deps)` or `fix(security)` per house style | Consumers need to see it in the changelog |
| Removing a public function, flag, or endpoint | Breaking: usually `feat!` or `refactor!`, with a `BREAKING CHANGE:` footer | Removal breaks callers |
| Removing dead internal code | `refactor` | Nobody outside can observe it |
| Code comments only | `docs` | |
| A CSS or theme change users can see | `feat` or `fix` | `style` means code formatting |
| Lint autofix or formatter run | `style` | |
| Linter or formatter config change | `chore` or `build` per house style | |
| CI pipeline YAML | `ci` | |
| Build scripts, bundler, compiler flags, Dockerfile for builds | `build` | |
| A release or version-bump commit | Usually tool-generated, e.g. `chore(release): 1.4.0` | Hand-write one only if history shows people do |
| Initial commit | Whatever the repo does. `chore: initial commit` is common. | |

When two types both seem to fit, pick the one that tells a changelog reader the most. If the
commit honestly needs two types, it's probably two commits.

## 3. Choosing a scope

- **Pick a noun for one area.** A package, module, service, app, or directory, for example
  `feat(cart)`, `fix(cli)`, `build(docker)`.
- **Reuse existing scopes before inventing new ones.** This lists the most frequent ones:

  ```bash
  git log -n 300 --format=%s | grep -oE '^[a-z]+(\([^)]+\))' | sort | uniq -c | sort -rn | head -20
  ```

- **Leave the scope off when the change spans many areas.** A vague scope like `(core)` or
  `(misc)` adds nothing.
- **Respect a scope allowlist.** A `scope-enum` rule in the commitlint config means only the
  listed scopes are allowed.

## 4. Breaking changes

A change is breaking when existing consumers must change something to keep working. Common
cases:

- A public API, CLI flag, configuration key, or environment variable is removed or renamed.
- A default changes in a way callers can observe.
- A wire format, file format, or stored data shape changes incompatibly.
- The minimum supported runtime, language, or platform version goes up.
- A previously tolerated input is now rejected.

Mark it in two places. Use `!` in the header so it's visible in one-line logs, and add a
`BREAKING CHANGE:` footer that says what broke and how to migrate. The footer is not optional
when you use `!`. It's the marker every parser understands, while some don't read `!` at all:
semantic-release's default preset (angular) has a header pattern that doesn't match `feat!:`.
That commit then counts as no release unless the footer is present. Presets built for
Conventional Commits (`conventionalcommits`) read both.

```text
feat(config)!: read settings from environment before config file

Environment variables now override values in settings.yaml, matching
how the container platform injects secrets.

BREAKING CHANGE: a value set in both settings.yaml and the environment
now resolves to the environment value. Remove duplicated keys from
settings.yaml, or unset the variable, to keep the old behavior.
```

Version-zero projects (0.x) are a special case. Many release tools bump the minor version
instead of the major for breaking changes before 1.0, depending on configuration. Check the
release tool's config before promising a version number.

## 5. Reverts

Run `git revert <sha>`. Its default message is `Revert "original subject"` followed by
`This reverts commit <full sha>.`. Keep that SHA line, because tools and people use it to
connect the two commits. What the default message lacks is the reason.

To write the message yourself:

```bash
git revert --no-commit 3f2a91c
git commit -F - <<'EOF'
revert: prorate from the plan change date

This reverts commit 3f2a91c8e4b0d2a7c1f6e9b3d5a8c0f2e4b6d8a1.

Invoices generated after the change double-counted the upgrade day for
plans billed in arrears. Reverting until the fix handles arrears
billing; reland tracked in #497.

Refs: 3f2a91c
EOF
```

- **Subject style.** Under Conventional Commits, use `revert: original subject`. The spec's FAQ
  suggests a `Refs:` footer listing the reverted SHAs. In repos that keep git's default
  `Revert "..."` subject, keep it.
- **Say why** the revert was needed and whether a reland is planned.
- **Reverting a merge commit** needs `-m 1` (the parent to keep), and reverting a merge has
  lasting consequences for re-merging that branch later. Confirm with the user first.

## 6. Security fixes

A commit message becomes public the moment it reaches a public remote, often before users can
upgrade. What it should say depends on whether the vulnerability is already known.

- **Already public** (a dependency advisory, a disclosed report): cite the identifier in a
  footer, `Refs: CVE-...` or `Refs: GHSA-...`, so people can find the fix by searching for the
  advisory. Describing the impact is fine, because the advisory already does.
- **Not yet disclosed** (a flaw in the project's own code): follow the project's `SECURITY.md`
  or embargo process. Keep the message accurate but neutral, for example
  `fix(import): tighten XML parser limits`, without the attack path, the affected endpoint,
  or reproduction steps. The details belong in the advisory published with the release. If
  you can't tell whether the issue is public, ask the user before writing the message.
- **Never** put exploit payloads, proof-of-concept input, or the exposed credential itself
  into a message.

## 7. Trailer reference

SKILL.md lists the five common footers. These notes cover the rest, and the details that cause
mistakes:

| Trailer | Notes |
|---|---|
| `Closes`, `Fixes`, `Resolves` (and their tense variants) | These are the hosting platform's keywords, not part of Conventional Commits. On GitHub, an issue closed from a commit message doesn't list the pull request as linked. If you want that link, put the keyword in the PR description as well. For partial work, use `Refs:`. |
| `Co-authored-by: Name <email>` | GitHub links a co-author only when the email belongs to their account, or is their no-reply address. Use the address they commit with, not a guess. |
| `Signed-off-by:` | Certifies the Developer Certificate of Origin: that the contributor has the right to submit the change. Only a human can make that certification, so an agent never adds it, and never passes `-s`, on its own initiative. The user adds their own after reviewing the commit, or tells you explicitly that they certify this change. |
| `Assisted-by:` (and similar AI-disclosure trailers) | Some projects ask for AI assistance to be disclosed in a trailer, in a format their contribution guide defines. Use the exact format the project documents, and follow the host tool's attribution instructions. Don't list an AI tool as `Co-authored-by` unless the project or the tool's instructions call for that. Some projects reject AI-generated contributions outright; stop and tell the user if so. |
| `Reviewed-by:`, `Acked-by:`, `Tested-by:` | Review credit used by some projects. Add only when history shows the practice. |
| `Change-Id: I...` | Gerrit's commit-msg hook adds it. Keep it unchanged on amend, or Gerrit opens a new review instead of updating the existing one. |

To add trailers without editing the text, use `git commit --trailer "Token: value"`
(Git 2.32+), repeated once per trailer. To inspect trailers already in history:

```bash
git log -n 50 --format='%(trailers:only,unfold)' | sort | uniq -c | sort -rn | head
```

## 8. Other house styles

Match these when history shows them. Don't convert a repo to Conventional Commits on your own
initiative.

- **Subsystem prefix** (common in large C projects): `net: fix use-after-free in socket
  close`. The prefix is the area, and the summary is lowercase and imperative.
- **Ticket key**: `PROJ-123: Add retry to upload client` or `[PROJ-123] Add retry ...`. Put
  the key exactly where history puts it, and still explain the why in the body.
- **Plain imperative sentence**: `Add retry to upload client`. A capitalized subject with no
  prefix and no period is the classic git style.
- **Emoji prefixes**: use them only if the history consistently does.

## 9. Detecting enforced conventions

| File or setting | What it means |
|---|---|
| `commitlint.config.{js,cjs,mjs,ts}`, `.commitlintrc*`, `commitlint` key in `package.json` | commitlint rules. Read `type-enum`, `scope-enum`, `header-max-length`, `subject-case`, `body-max-line-length`. |
| `.czrc`, `.cz.toml`, `.cz.json`, `.cz.yaml`, `config.commitizen` in `package.json` | Commitizen. Its types and scopes define the vocabulary. |
| `.gitlint` | gitlint rules for title length, body requirements, and banned words |
| `.gitmessage`, or `git config commit.template` | A message template. Mirror its sections. |
| `.husky/commit-msg`, `lefthook.yml`, `.pre-commit-config.yaml` with a commit-msg stage | A local hook validates messages. Expect off-format messages to be rejected. |
| An installed, untracked hook in the hooks directory (`git rev-parse --git-path hooks`), or a `core.hooksPath` setting | Hooks that never appear in `git ls-files`. Gerrit's `commit-msg` hook, which adds `Change-Id`, usually lives here. Read the hook to see what it enforces or adds. |
| `.releaserc*`, `release.config.*`, `release` key in `package.json` | semantic-release. Commit types drive version bumps and the changelog. |
| `release-please-config.json`, `.release-please-manifest.json` | release-please. Same implication. |
| `cliff.toml` | git-cliff builds the changelog from commit types |
| CI workflow that runs commitlint or checks the PR title | Commits or PR titles are validated in CI |
| `.git-blame-ignore-revs` | Formatting-only commits are hidden from blame. After a mass-reformat commit lands, add its full SHA in a follow-up commit. |

To validate locally when commitlint is already a project dependency (don't install it just for
this):

```bash
npx commitlint --from HEAD~1 --to HEAD    # lint the last commit
```

## 10. Git message-handling gotchas

- **The editor drops `#` lines.** When git opens an editor, its default cleanup removes every
  line that starts with `#` as a comment, so a line beginning `#123` disappears. Messages
  passed with `-F` or `-m` only get whitespace cleanup and keep those lines. Prefer the heredoc
  form, or move the reference mid-line.
- **The title is everything before the first blank line.** If the first two lines have no
  blank line between them, both become the title and are joined in one-line views.
- **Trailers must be the last paragraph.** Put them after a blank line, one per line, with no
  prose mixed in. Otherwise `git interpret-trailers`, hosting platforms, and release tools may
  ignore them.
- **Message files must be plain UTF-8 without a byte-order mark.** Git rejects a UTF-16 file
  ("a NUL byte in commit log message not allowed") and keeps a byte-order mark as invisible
  characters at the start of the subject. Windows PowerShell 5.1 hits both: `>` and `Out-File`
  write UTF-16, and `Set-Content -Encoding UTF8` writes a byte-order mark. Write the file
  explicitly instead:

  ```powershell
  [IO.File]::WriteAllText("$env:TEMP\msg.txt", $msg, [Text.UTF8Encoding]::new($false))
  git commit -F "$env:TEMP\msg.txt"
  ```

  PowerShell 7 writes BOM-less UTF-8 by default, so its `Set-Content` and `Out-File` are fine.
