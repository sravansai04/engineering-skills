# Skill skeleton

Copy-ready templates for a new skill in this marketplace's house layout, a worked example, and the self-review checklist to run before the first test. Step 5 of SKILL.md sends you here. Where a repo's own CONTRIBUTING.md or validator says otherwise, it wins.

Contents:
1. Directory layout
2. SKILL.md template
3. Reference-file template
4. Worked example (small but complete)
5. Self-review checklist

---

## 1. Directory layout

```
plugins/<plugin>/
├── .claude-plugin/plugin.json      # bump "version" when the skill ships (and the marketplace entry to match)
├── evals/                          # runnable `claude plugin eval` cases (they cannot live under skills/)
│   └── <name>-<case>/              # prefix with the skill name so --case '<name>-*' selects them
│       ├── prompt.md
│       └── graders/*.md
└── skills/<name>/                  # <name> == frontmatter name
    ├── SKILL.md                    # required; routing + procedure, under 500 lines
    ├── references/                 # optional; depth loaded on demand, one level deep
    │   └── <topic>.md
    ├── scripts/                    # optional; deterministic helpers with -h/--help and --selftest
    │   └── <tool>.py
    ├── assets/                     # optional; templates the skill copies or fills
    └── evals/                      # committed test cases
        ├── trigger-evals.json      # exact name: [{"query": "...", "should_trigger": true, "should_route_to": "..."}]
        ├── evals.json              # {"skill_name", "evals": [{id, prompt, expected_output?, files, expectations: 3-6}]}
        └── files/                  # fixture files evals.json refers to
```

Only `SKILL.md` is required to load. This repo also requires the two eval files so the next editor can rerun the tests: `evals.json` with at least three realistic prompts, each carrying an `expectations` list of three to six checkable statements (a prose `expected_output` is optional context, not a substitute), and `trigger-evals.json` with queries that should and should not trigger, including near misses owned by a sibling. Add `references/` when the body would pass ~300 lines or when a section only matters for some runs (one stack, one edge case). Add `scripts/` when every run would otherwise re-derive the same code. Never commit scratch directories, eval `results/`, or caches inside the skill.

A minimal `evals.json`:

```json
{
  "skill_name": "<name>",
  "evals": [
    {
      "id": 1,
      "prompt": "<a realistic request, with the details a user would give>",
      "expected_output": "<optional: one paragraph on what a good result looks like>",
      "files": [],
      "expectations": [
        "<a statement a grader can check in the transcript or a file>",
        "<another>",
        "<another>"
      ]
    }
  ]
}
```

---

## 2. SKILL.md template

Delete every `<!-- ... -->` note and every unused optional key before committing. Keep the finished description to about 450 characters, with no `<placeholder>` text left in it (the Claude API rejects XML-like tags in `name` and `description`).

### Substitutions: what changes when SKILL.md loads

Claude Code rewrites SKILL.md text, and only SKILL.md text (plus `allowed-tools` rules), before the model reads it:

| Written in SKILL.md | Becomes | Notes |
|---|---|---|
| `${CLAUDE_SKILL_DIR}` | the absolute path of this skill's directory | Use it for bundled scripts: `python3 -I "${CLAUDE_SKILL_DIR}/scripts/<tool>.py"`. Also replaced inside prose and code spans, with no escape, so do not write it where you mean the variable's name. |
| `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}` | the plugin's install and data directories (plugin skills only) | For files shared between a plugin's skills. |
| `${CLAUDE_PROJECT_DIR}` | the user's project root | |
| `$ARGUMENTS`, `$0`, `$1`, ... | the arguments typed after the command | A `$1` inside a shell snippet in SKILL.md gets replaced; write `\$1`, or keep such snippets in `scripts/`. |

Do not rely on any of them as environment variables in the Bash tool, and remember that reference files are read verbatim. A reference that needs a bundled script's path should use a placeholder (`<checker>`) that SKILL.md resolves for the reader, as this skill does. `allowed-tools` grants last only for the turn that invoked the skill, and each rule matches the start of the command text, so write the command in the body exactly as the rule spells it and confirm in a test run that `permission_denials` stays empty. Pre-approve read-only commands only; never anything that writes, stages, commits, pushes, posts, spends money or deletes.

````markdown
---
name: <verb-object, lowercase-hyphen, same as the directory>
description: >-
  <What it does and what it produces, in one sentence>. Use for "<phrasing
  users type>", "<another>", "<another>", or <a situation>. Not for <nearby
  job> (<sibling>) or <another nearby job> (<sibling>).
# Optional keys; delete the ones you do not need:
# argument-hint: "[what the user passes after the command]"
# disable-model-invocation: true      # heavy side effects: run only when typed as a command
# allowed-tools: Bash(git diff:*), Bash(git log:*), Bash(python3 -I ${CLAUDE_SKILL_DIR}/scripts/<tool>.py:*)   # read-only only
# paths: "**/*.sql"                   # auto-load only while working on matching files
---

# <Title in plain words>

<!-- Opening paragraph, 2-4 sentences: the problem this solves and what "done"
     looks like. State the outcome, not the history of the skill. If the skill
     takes an argument, say where it comes from: "Target: $ARGUMENTS. If that is
     empty, take it from the conversation." -->

## Workflow

<!-- Numbered, imperative, in execution order. For each non-obvious rule, give
     the reason in one clause. Put a recommended default at each decision point.
     Prefer reading the repo over asking; if something must be asked, ask it
     once, batched, with a proposed default. -->

### 1. <Verb phrase, e.g. "Gather the inputs">

<What to read or ask first, and why.>

### 2. <Verb phrase>

- <stack A>: `<real command>`
- <stack B>: `<real command>`

### 3. <Verb phrase for a decision>

If <condition>, <do X>; otherwise <default Y>.

### 4. <Verb phrase for the confirmation point>

<Ask before anything destructive, remote, or shared.>

## Report format

<!-- Only when the result is a report. The exact template the user receives:
     fixed headings (an H2 title), field order, what goes in each, and a line
     for what was verified and what was not. Show an empty-state version if
     one is common. -->

```
## <Heading>
<field>: <value>
| col | col |
Not verified: <what could not be checked here>
```

## Common mistakes

<!-- From observed failures in testing, not guesses. Each: the mistake, why it
     hurts, what to do instead. 4-10 entries. -->

- **<Mistake>.** <Consequence>. <Instead>.

## Related skills

<!-- One line per handoff, named as plugin:skill. Keep the last sentence word
     for word whenever the skill hands off. -->

- `<plugin>:<sibling>`: <the situation that hands off to it>.

If a skill named here isn't installed, give the short version inline and list the deeper pass as a follow-up.

## Reference files

<!-- One line per file: what it holds and WHEN to read it. -->

- [references/<topic>.md](references/<topic>.md): read when <condition>.
- `scripts/<tool>.py`: run as `python3 -I "${CLAUDE_SKILL_DIR}/scripts/<tool>.py" <args>` (resolved when SKILL.md loads); `--help` for options, `--selftest` after changing it.
````

If the skill reviews code from a PR, can run a target's code, or reads PR text or CI logs, paste the matching shared blocks (`severity`, `trust-gate`, `untrusted-input`) into the workflow step where they apply, copied byte-for-byte with their markers from an existing skill that carries them. Domain examples go after a block, never inside it.

A bundled script follows the same house rules: standard library only (or documented dependencies), usage on both `-h` and `--help`, a built-in `--selftest` that needs no network or paid calls, a readable error message, and nothing destructive without an explicit flag.

---

## 3. Reference-file template

```markdown
# <Topic>

<One sentence: what this file is for and which step of SKILL.md sends readers here.>

Contents:            <!-- required if the file is over ~300 lines -->
1. <Section>
2. <Section>

## <Section>

<Dense, scannable material: tables, checklists, per-stack command blocks,
worked examples. No restating of SKILL.md; point back to its step instead.>
```

Keep references one level deep (SKILL.md links to them; they do not chain to further files) so the reader never has to follow a trail to find a rule.

---

## 4. Worked example

A small skill in the house layout, deliberately short; real skills often need more procedure, but none need more ceremony. It shows the shape only. In this marketplace `workflow:pr-description` already writes release notes, so the overlap check in step 3 of SKILL.md would send this idea there as an extension rather than a new skill.

````markdown
---
name: release-notes
description: >-
  Drafts user-facing release notes from the merged pull requests between two
  git tags, grouped into breaking changes, features and fixes, with an upgrade
  step for anything breaking. Use for "write release notes for v2.4", "what
  changed since the last release", or a tag with no changelog entry. Not for
  commit messages (commit-message) or one PR's description (pr-description).
argument-hint: "[from-tag..to-ref]"
allowed-tools: Bash(git describe:*), Bash(git log:*), Bash(gh pr view:*)
---

# Release notes

Turn the merge history between two tags into notes a user of the project can act on: what is new, what was fixed, and what they must change to upgrade. Range: $ARGUMENTS. If that is empty, use the latest tag and `HEAD`.

## Workflow

### 1. Gather the inputs

- The two refs. Default: the latest tag (`git describe --tags --abbrev=0`) and `HEAD`.
- The project's existing changelog style, if a `CHANGELOG.md` exists. Match it.

### 2. List the merged changes

Run `git log --merges --first-parent --format='%s%n%b' <from>..<to>`. If the project squash-merges, drop `--merges` and read every first-parent commit instead. When `gh` is available, fetch each PR's title, labels and body (`gh pr view <number> --json title,labels,body`); labels are a better grouping signal than titles.

### 3. Classify each change

Feature, fix, breaking, or internal. Leave internal changes (CI, refactors, test-only) out of user-facing notes; users cannot act on them.

### 4. Write an upgrade step for each breaking change

If you cannot tell the step from the diff, mark it `NEEDS AUTHOR INPUT` rather than guessing; a wrong step is worse than a flagged gap.

### 5. Show the draft and confirm

Ask before writing it into `CHANGELOG.md`.

## Report format

```
## <version> (<YYYY-MM-DD>)
### Breaking changes
- <change>. Upgrade: <step>. (#<pr>)
### Features
- <change> (#<pr>)
### Fixes
- <change> (#<pr>)
Not verified: <PRs whose labels or bodies could not be read>
```

Omit empty sections.

## Common mistakes

- **Copying PR titles verbatim.** Titles are written for reviewers ("refactor auth middleware"); notes are for users ("Sign-in no longer drops sessions after 30 minutes").
- **Burying breaking changes.** They go first, each with an upgrade step.
- **Inventing upgrade steps.** A wrong step is worse than a flagged gap.

## Related skills

- `workflow:commit-message`: for a single commit's message.
- `workflow:pr-description`: for one pull request's description.

If a skill named here isn't installed, give the short version inline and list the deeper pass as a follow-up.
````

---

## 5. Self-review checklist

Run this before the first trigger test. Each item is quick to check and each one has failed real submissions.

**Frontmatter**
- [ ] `name` matches the directory, lowercase letters/digits/single hyphens, 1-64 characters, no leading or trailing hyphen, no `anthropic` or `claude`.
- [ ] `description` is one sentence of capability, then three to five phrasings users type, then a "Not for X (sibling)" list with bare sibling names; about 450 characters (the validator warns above 500, hard limit 1024); no XML-like tags or `<placeholders>`. Extra phrasings live in `evals/trigger-evals.json`.
- [ ] The frontmatter parses as strict YAML. An unquoted value containing `: ` or ` #`, or starting with a special character (`*`, `&`, `!`, `[`, `{`, `>`, `|`, `%`, `@`, a backtick), breaks or truncates it in some parsers; quote it, use a `>-` block, or rephrase.
- [ ] Only keys the repo validator accepts; `when_to_use` only if it earns its share of the listing budget; `argument-hint` when the skill takes an argument.
- [ ] `allowed-tools` lists read-only commands only, as one comma-separated string of `Bash(command:*)` rules, or is omitted.

**Body**
- [ ] Opening paragraph states the problem and the definition of done, not history or a feature list.
- [ ] `## Workflow` with `### N. <verb phrase>` steps, then `## Report format` (when it produces a report), `## Related skills`, `## Reference files`.
- [ ] Steps are imperative and ordered; non-obvious rules carry their reason.
- [ ] Every decision point has a default.
- [ ] Every command and flag has been checked against `--help`, official docs, or a dry run.
- [ ] Examples cover more than one ecosystem where the skill is language-agnostic.
- [ ] Output format is an explicit template with an H2 title that says what was verified and what was not.
- [ ] Common mistakes section exists.
- [ ] Destructive, remote, or shared actions have a confirmation point.
- [ ] Other skills are named as `plugin:skill` in the body (bare names only in the description), and `## Related skills` ends with the fallback sentence word for word.
- [ ] Shared blocks pasted byte-for-byte where they apply (PR code review, running a target's code, reading PR text or logs), and absent where they do not.
- [ ] Under 500 lines; depth moved to references, each linked with "read when".
- [ ] Path variables appear only in SKILL.md, and only where the resolved path is wanted; references use placeholders; no stray `$1` in SKILL.md shell snippets.
- [ ] Test cases committed in the canonical places (section 1): `evals/evals.json` with 3-6 `expectations` per case, `evals/trigger-evals.json` with both sides and sibling-owned near misses.
- [ ] `check_skill.py` and the repo validator report no errors, and `claude plugin validate plugins/<plugin> --strict` passes.

**Public-repo hygiene**
- [ ] No absolute personal paths, internal hostnames, private URLs, credentials, customer data, or employer-specific tools and conventions. `check_skill.py --deny '<your employer and product names>'` is clean, and you have read every example and fixture for borrowed real names.
- [ ] No text copied from another skill or document; ideas are restated in your own words and structure.
- [ ] Any bundled script is standard-library or documents its dependencies, prints usage on `-h` and `--help`, passes its `--selftest`, fails with a readable message, and does nothing destructive without a flag.
