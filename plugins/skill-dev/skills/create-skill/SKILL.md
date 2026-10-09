---
name: create-skill
description: >-
  Creates or fixes a Claude Code skill, measuring triggering in fresh sessions
  and output against a no-skill baseline before it ships. Use for "turn this
  workflow into a skill", "add a skill to this marketplace", "my skill never
  triggers", "this skill fires on everything", or "split this huge SKILL.md".
  Not for product features (brainstorm-spec, build-feature), skill-syntax
  questions (docs-lookup), PR text (pr-description), or hooks and CLAUDE.md.
argument-hint: "[skill idea, or path to an existing skill]"
allowed-tools: Bash(git status:*), Bash(git rev-parse:*), Bash(git ls-files:*), Bash(git diff:*), Bash(git log:*), Bash(python3 -I ${CLAUDE_SKILL_DIR}/scripts/check_skill.py:*), Bash(python3 -I "${CLAUDE_SKILL_DIR}/scripts/check_skill.py":*), Read, Grep, Glob
compatibility: The bundled checkers need Python 3.8 or later (standard library only); the trigger checker also runs the claude CLI.
---

# Create a skill

A skill is two things that fail independently:

- **The description** is routing. It sits in the context of every session of every user who installs the plugin, and it shares one fixed listing budget with every other installed skill. The model reads it to decide whether to load the skill. A weak description means the skill never runs; a greedy one hijacks requests that belong to a sibling; a long one crowds other skills out of the listing.
- **The body** is behavior. It is read only after the skill fires, and it decides whether the result is better than what the model would have done with no skill at all.

So "done" means both were measured in fresh sessions, not eyeballed in the session that wrote them: should-trigger prompts fire it, near-miss prompts do not, the output beats a no-skill baseline on criteria written down first, the checks pass, the catalog lists it, the plugin version is bumped, and the PR carries the evidence.

Skill idea or path to work on: $ARGUMENTS

If that is empty (as it is when this skill loads on its own), take the idea or the path from the conversation.

## Before you start: pick the mode

| Situation | Mode | Skip |
|---|---|---|
| A checkout of this marketplace (skills at `plugins/*/skills/*/SKILL.md`, usually a `.claude-plugin/marketplace.json` at the root) | **Contribute** | nothing |
| Changing a skill that already exists in this repo | **Rework**: write a short intent card for the change (what fails today), then steps 5-10 with the current version as the baseline | steps 3-4 unless the scope changes |
| A personal (`~/.claude/skills/`) or project (`.claude/skills/`) skill elsewhere | **Standalone**: draft it inside a throwaway plugin in the scratch directory (`<scratch>/plugin/skills/<name>/SKILL.md`); wherever a command below loops over `plugins/*/`, pass `--plugin-dir <scratch>/plugin` instead, and test it as `plugin:<name>`. Copy it to its final home only after it passes | the branch in step 1, plugin choice in step 4, the repo validator in step 8, steps 9-10 |

## Workflow

### 1. Set up and orient

1. Confirm the repo root (`git rev-parse --show-toplevel`) and a clean tree (`git status --short`); if unrelated changes are present, ask whether to commit or stash them before starting. Run every command below from that root.
2. In Contribute and Rework modes, branch **now**, before the first edit, so nothing lands on the default branch: `git switch -c add-<topic>-skill`. Rename it with `git branch -m` once the name is settled in step 4.
3. Make a private scratch directory and reuse the path it prints, literally, from then on (written below as `<scratch>`). The worksheet, cases files, results and PR body live there, out of the commit and safe from parallel sessions; a fixed name such as `/tmp/cases.json` gets overwritten by the next session that picks it.
   ```bash
   mktemp -d "${TMPDIR:-/tmp}/<topic>-skill.XXXXXX"
   ```
4. Note the two bundled tools. Their paths below were filled in when this skill loaded. Reference files do not get that substitution, so they write `<checker>` and `<check-skill>`: paste these paths in their place.
   - `<checker>`: `${CLAUDE_SKILL_DIR}/scripts/trigger_check.py`
   - `<check-skill>`: `${CLAUDE_SKILL_DIR}/scripts/check_skill.py`
5. Read, in this order, so the draft follows the repo's actual rules instead of remembered ones:
   1. `CONTRIBUTING.md` (or whatever the README points contributors to): layout, frontmatter and description rules, body skeleton, shared blocks, eval layout, branch, and commit sign-off (DCO) or CLA rules.
   2. The repo validator (look in the repo's top-level `scripts` directory; this marketplace's is `validate_skills.py`). It is the authority on frontmatter keys, limits and layout; where it disagrees with this skill, it wins and the PR notes the discrepancy.
   3. The README catalog section, to copy its row format, and each plugin's `.claude-plugin/plugin.json` (`name`, `version`).
   4. The PR template: `ls .github/ .github/PULL_REQUEST_TEMPLATE/ 2>/dev/null | grep -i pull_request`.
   5. How skills keep test cases: `ls plugins/*/skills/*/evals/ plugins/*/evals/ 2>/dev/null`. The canonical names are in steps 6 and 7.
   6. Every existing skill's frontmatter, for step 3:
      ```bash
      awk 'FNR==1{n=0; print "== " FILENAME} /^---[[:space:]]*$/{n++; next} n==1' plugins/*/skills/*/SKILL.md
      ```

   If any of these is missing (a fresh or staging checkout), note it, use the fallback checks in step 8, and list what is missing in the report. Do not invent a validator rule, a template or a version number.

When the skill to fix or review comes from someone else's branch, fork or pull request, its scripts, eval fixtures and setup files are code its author wrote, and steps 6 to 8 run them with this session's permissions (`claude plugin eval` and the trigger checker load the plugin as you). Apply the gate first:

<!-- shared:trust-gate v2 -->
**Trust gate: check the author before running anything from the target.** Tests, builds, package scripts, dependency installs, migrations, and benchmarks all execute code the author wrote, on a machine that holds the user's tokens, SSH keys, and cloud credentials. This is why CI withholds secrets from fork PRs. For a PR, check:

```bash
gh pr view N --json author,isCrossRepository
gh api "repos/{owner}/{repo}/pulls/N" --jq .author_association
```

Trusted: the user's own branch, or an `OWNER`, `MEMBER`, or `COLLABORATOR` on a PR that isn't from a fork. Everything else is untrusted: `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, `FIRST_TIMER`, `NONE`, any fork PR, and a branch or archive from someone you can't identify. Where you can't tell, ask.

On GitLab, `glab mr view N --output json` shows a fork MR as one whose `source_project_id` differs from its `target_project_id`. For the author's role, `glab api projects/:id/members/all/<author.id>` returns an `access_level`: Developer (30) or higher, on an MR from the project itself, is trusted; a lower level, or a 404 because the author is not a member, is untrusted.

For an untrusted target, run nothing from it unless the user vouches for the author. Even then, run it only in a throwaway container with no credentials in its environment and no home-directory mount, with install scripts disabled where the tool allows (`npm ci --ignore-scripts`). Otherwise work from reading and CI results, mark findings that needed a run **Likely**, and write "not executed: untrusted author" in the report.
<!-- /shared:trust-gate v2 -->

For a skill from an untrusted author, read its scripts and eval files instead of running them, and run steps 6 to 8 only after the user vouches for the author, or in a throwaway container.

**Paid runs need a go-ahead.** Every checker or eval run starts real sessions billed to the user. Before the first one in steps 3, 6 and 7, show the plan (sessions = cases x runs; the checker's `--dry-run` prints the count) with a per-session price, and wait for an OK unless the user already set a budget. Price it with a one-case `--runs 1` run if unsure: a trigger session is about one model turn with the full skill listing in context. Record the actual cost (the checker's `Cost:` line, the eval's cost column) in worksheet F and the report.

### 2. Write the intent card

Start from what this session already holds. If the workflow being captured just happened here, list the commands that actually ran, in order, and every place the user overrode you; those overrides are the seed of the Common mistakes section. Ask only for what is still missing, in one batch, with a proposed default for each. Record the card in the worksheet ([references/evaluation-worksheet.md](references/evaluation-worksheet.md)).

| Field | What good looks like |
|---|---|
| Problem | A concrete failure without the skill: "Claude adds a NOT NULL column with no default and locks the table", not "help with migrations". |
| Moment | When a user reaches for it: "after CI goes red on a PR". |
| Should-trigger prompts (3-5) | Realistic and varied: one terse, one long with project details, one that never names the task, one with shorthand or a typo. |
| Should-NOT prompts (3+) | Near misses that share vocabulary but belong elsewhere. Write where each one *should* go (a sibling skill id, or `none`). |
| Output | The artifact or report the user gets, and its shape. |
| Success criteria (3-6) | Observable checks a transcript can be graded against: "runs the test suite before claiming done", "report ends with a one-line verdict". These become the `expectations` in step 7. |
| Side effects | Files written, commands run, anything pushed, sent or paid for. Each needs a confirmation point in the body. |

Then write the prompts to `<scratch>/cases.json` (format: worksheet section D). Steps 3 and 6 run that file.

Two stop signs. If you cannot write one convincing should-NOT prompt, the scope is too vague to route; narrow it. If you cannot name a failure the model makes today without the skill, there may be nothing to fix; check with a baseline run (step 7) before drafting.

### 3. Check overlap, then decide

Grep the frontmatter dump and the bodies for the nouns and verbs on your card:

```bash
grep -rniE 'migration|schema change' plugins/*/skills/*/SKILL.md
```

Then see what fires **today** for your should-trigger prompts. Point the checker at the closest existing skill and ignore its verdict column; the hit counts and the "other skills that fired" column show who already answers these prompts:

```bash
args=(); for d in plugins/*/; do args+=(--plugin-dir "$d"); done
python3 -I "${CLAUDE_SKILL_DIR}/scripts/trigger_check.py" "${args[@]}" \
  --skill <plugin>:<nearest-skill> --cases <scratch>/cases.json --runs 1
```

Before you add anything, snapshot the one or two nearest siblings' committed trigger cases, so step 6 can prove your skill took nothing from them. The canonical file is `evals/trigger-evals.json`. In a repository that names it differently, pass that file to `--cases`; `check_skill.py` warns about non-canonical names.

```bash
args=(); for d in plugins/*/; do args+=(--plugin-dir "$d"); done
python3 -I "${CLAUDE_SKILL_DIR}/scripts/trigger_check.py" "${args[@]}" \
  --skill <p>:<sibling> --cases plugins/<p>/skills/<sibling>/evals/<trigger-file>.json \
  --runs 3 --json-out <scratch>/sibling-<sibling>-before.json
```

| Finding | Decision |
|---|---|
| An existing skill already covers this job at this moment | **Extend it**: add a step, a section or a reference file there. Do not create a near-duplicate. |
| Same domain, different moment (writing vs reviewing, planning vs executing) | **New skill**, and both descriptions name the boundary ("Not for X (sibling)"). Edit the sibling's description in the same PR if it would otherwise take your prompts. |
| A stack- or tool-specific variant of an existing skill | **Reference file** in the existing skill (`references/<stack>.md`), not a new skill. |
| A wrapper around one command, or something the baseline already does well | **Do not build.** Tell the user why, with the baseline evidence. |

### 4. Pick the plugin and the name

At the time of writing this marketplace has these plugins (`ls plugins/` for the current list):

| Plugin | Holds skills that... |
|---|---|
| `implementation` | write or change code: brainstorm a spec, plan, build, execute a plan, test-drive, debug, refactor, simplify, look up docs, verify before done |
| `review-suite` | evaluate code someone else wrote: PR, security, performance, parallel multi-reviewer passes |
| `data-api` | design or check schemas, migrations, queries and API contracts |
| `frontend` | shape and check user interfaces: design direction, browser testing, accessibility |
| `workflow` | produce team-process artifacts: commits, PR descriptions, review responses, worktrees, CI triage, ADRs, postmortems |
| `skill-dev` | author and maintain skills themselves |

Pick by the *moment the user is in*, not by the topic. A skill that reviews migrations belongs where reviewers look (`review-suite` or `data-api`, whichever the repo already uses for similar skills), not wherever "database" appears. If nothing fits, propose a new plugin in an issue first; a new plugin also needs a manifest, a marketplace entry and maintainer agreement.

Name rules (Agent Skills format plus what the Claude API enforces on upload): lowercase letters, digits and single hyphens; 1-64 characters; no leading or trailing hyphen; identical to the directory name; must not contain `anthropic` or `claude`; no XML-like tags in the name or the description (a placeholder such as `<plugin>` counts). Prefer a verb-object name a user could guess (`review-migration`, `write-adr`): when the listing is over budget the name may be all the model sees. Avoid generic names (`helper`, `tools`), product or company names, and names that shadow built-in commands.

### 5. Draft the skill

Create `plugins/<plugin>/skills/<name>/SKILL.md` from the skeleton in [references/skill-skeleton.md](references/skill-skeleton.md). It follows this marketplace's CONTRIBUTING.md; in another repo, that repo's rules win.

**Frontmatter.** `name` and `description` are the portable minimum. Add another key only for a concrete reason, and only if the repo validator allows it:

- `argument-hint`: the skill takes an argument when typed as a command; the hint shows in autocomplete.
- `when_to_use`: extra trigger phrasing appended to the description in the listing. It counts toward the same 1,536-character entry cap and the same shared budget, so it is not free space; one tight description is usually better.
- `disable-model-invocation: true`: heavy side effects; the skill runs only when the user types its command.
- `allowed-tools`: pre-approves read-only commands only, written as one comma-separated string of `Bash(command:*)` rules (`Bash(git diff:*), Bash(git log:*)`, or the skill's own read-only script through the skill-directory variable). A rule matches the start of the command, so write the command in the body exactly as the rule spells it. Grants last only for the turn that invoked the skill. Never pre-approve anything that writes files, stages, commits, pushes, posts, spends money or deletes.
- `paths`: globs that limit automatic loading to matching files, for stack-specific skills.

**Description.** Write it as a trigger, not a summary: one sentence of what the skill does and produces, then the three to five strongest phrasings users actually type, then a short "Not for X (sibling)" list naming the skill that owns each nearby request (bare sibling names, to save space). Aim for about 450 characters; this marketplace's validator warns above 500 and 1,024 is the hard limit. Claude Code sizes the whole skill listing at about 1% of the model's context window and, once over, drops descriptions starting with the least-used skills, so a newly installed skill loses its description first; every character you add also squeezes your siblings. Extra phrasings belong in `evals/trigger-evals.json`, where they are tested instead of paid for in every session. Good and bad examples, the budget mechanics, and a symptom-to-fix table: [references/description-guide.md](references/description-guide.md).

**Body.** Write for a capable engineer who has never seen this repo:

- The repo's skeleton. In this marketplace: an opening paragraph, `## Workflow` with `### N. <verb phrase>` steps, `## Report format` when the result is a report, `## Related skills`, then `## Reference files`. Extra sections (common mistakes, a worked example) may sit between them. Report titles inside a template are H2.
- Imperative steps in the order they happen. Give the reason for any rule that is not obvious; a model that knows why a rule exists applies it to cases you did not foresee. Keep absolute language for real invariants (data loss, security, irreversible actions).
- A recommended default at every decision point, plus when to deviate. A menu with no default produces dithering.
- Every command and flag real and checked (`<tool> --help`, the official docs, or a dry run). Short multi-stack examples (`npm test` / `pytest -q` / `go test ./...`) rather than one ecosystem's idiom.
- An explicit **output format**: the exact template of what the user receives, saying what was verified and what was not.
- A **common mistakes** section built from failures you saw, not from guesses.
- Confirmation points before anything destructive, remote, shared or paid (push, publish, delete, send, batch model runs).
- Other skills named as `plugin:skill` (`review-suite:pr-review`), matching the installed listing. A skill that hands off ends `## Related skills` with CONTRIBUTING.md's fallback sentence, copied word for word.
- Nothing private: no internal hostnames, home paths, employer or product names, tokens or customer data. This repo is public.

**Shared blocks.** If the skill reviews code from a PR, can run a target's code, or reads PR text, code comments or CI logs, it uses the repo's shared blocks (here: `severity` for review skills, `trust-gate` for anything that executes a target's code, `untrusted-input` for anything that reads a PR or a log) instead of its own wording. Copy each one byte-for-byte, markers included, from an existing skill that carries it; the validator fails when two copies differ. Put domain examples after a block, never inside it, and do not paste a block that does not apply.

**SKILL.md is pre-processed when it loads; reference files are not.** The skill-directory variable (and the other CLAUDE_-prefixed path variables) is replaced everywhere in SKILL.md, prose and code alike, with no way to escape it, and a dollar sign followed by a digit is replaced by the skill's arguments. Reference files reach the model verbatim, and these are not variables you can rely on in the Bash environment. So: keep runnable commands that need the skill's own path in SKILL.md; in references, use a placeholder that SKILL.md resolves (as step 1 does here); keep shell snippets with positional parameters in `scripts/`. The literal spellings are in [references/skill-skeleton.md](references/skill-skeleton.md) section 2.

**Depth goes in references.** Keep SKILL.md well under 500 lines; once loaded it stays in context for the whole task. Move long checklists, per-stack details, templates and worked examples into `references/*.md`, one level deep, each linked from SKILL.md with a note on *when to read it*. A reference over ~300 lines gets a contents list at the top. Put deterministic, repeated work (parsing, validation, scaffolding) in `scripts/`: standard library only, run with `python3 -I` through the skill-directory variable so it works wherever the plugin is installed, printing usage for both `-h` and `--help`, and carrying a built-in `--selftest`.

Before testing, run the self-review checklist at the end of the skeleton reference and `<check-skill>` on the new directory (step 8 shows the command). Both take a minute and catch most loading and linking errors before any paid run.

### 6. Test triggering in fresh sessions

The session that wrote the skill cannot test it: it already knows the skill exists and what it is for. Every trigger test runs in a new `claude -p` process with all of the repo's plugins loaded, so siblings compete as they will for real users. Run sessions from a directory that looks like where users invoke the skill: the checker's default (a fresh empty temp directory) for general skills, a small fixture project passed with `--cwd` for skills whose trigger depends on the project. Never run them from the authoring checkout.

1. Extend `<scratch>/cases.json` with two paraphrases of the should-trigger prompts, and give every near miss its `should_route_to`. Write two more of each into a **separate held-out file** that you do not run until the end.
2. Get the go-ahead on cost, then run the checker. Each session has write tools and shell removed, refuses anything else that would need approval, and stops at the first skill the model chooses:
   ```bash
   args=(); for d in plugins/*/; do args+=(--plugin-dir "$d"); done
   python3 -I "${CLAUDE_SKILL_DIR}/scripts/trigger_check.py" "${args[@]}" \
     --skill <plugin>:<name> --cases <scratch>/cases.json --runs 3 \
     --json-out <scratch>/trigger-r1.json
   ```
3. Read the `Listing:` line before reading any miss. If it says OVER BUDGET, Claude Code dropped some descriptions, and a new skill's is usually first to go, so a miss may say nothing about wording. Rerun the failing should-trigger cases with `--listing-budget 200000`; if they pass then, tune wording against the full listing and record the budget figure as an open risk (the real fix is shorter descriptions across the repo, not a reworded one).
4. Fix the description one change at a time and rerun the **whole** set each time, because a change that rescues one prompt often breaks another. Use the symptom table in the description guide. Never paste a test prompt into the description; that tunes to the test, not to users.
5. When the tuning set passes, run the held-out file once (`--cases <scratch>/heldout.json`). If it fails, the description is overfitted: generalize the wording (the user's intent, not their phrasing) and write fresh held-out prompts.
6. Rerun each sibling snapshot from step 3 with your skill present, adding `--compare <scratch>/sibling-<sibling>-before.json`; it lists every case whose verdict changed.

Exit codes: 0 all passed; 1 a case failed; 3 nothing failed but a run errored or a case was inconclusive (rerun before trusting it); 2 setup problem. If fresh sessions cannot run here (no CLI, no credentials, commands refused), say so plainly, run the closest substitute, and label it weaker evidence in the report and the PR. Never present a simulated routing check as a trigger test.

Pass bar, with descriptions visible: each should-trigger prompt fires in at least 2 of 3 runs; each should-NOT prompt fires in at most 1 of 5 (0 of 3); no case is inconclusive; held-out cases pass; near misses route where `should_route_to` says whenever that sibling is loaded; and the sibling comparisons show no REGRESSION. Isolation details, the listing budget, model choice and troubleshooting: [references/testing-guide.md](references/testing-guide.md).

Commit the cases with the skill so the next editor can rerun them, tuning and held-out together (the next editor writes fresh held-out prompts): `plugins/<plugin>/skills/<name>/evals/trigger-evals.json` (this exact name), an array of `{"query": ..., "should_trigger": true|false, "should_route_to": ...}` (the last key only on near misses). When a sibling could claim one of your phrasings, add it to one skill's file as true and to the other's as false.

### 7. Test behavior against a baseline

Triggering proves the model found the skill, not that the skill helps. Get the go-ahead on cost first: behavior runs are full tasks.

**Default: `claude plugin eval`** (Claude Code 2.1.269 or later; check with `claude plugin eval --help`). It runs each case in an isolated session (temporary home, only your plugin, no personal skills, CLAUDE.md, hooks or MCP servers), adds a no-plugin baseline arm, grades with the graders you write, and reports with-plugin and baseline scores per case.

1. For each of 2-3 representative prompts, create a case directory `plugins/<plugin>/evals/<name>-<case>/` (eval cases cannot live under `skills/`) holding:
   - `prompt.md`: frontmatter with `max_turns` and `allowed_tools`; the body is the plain-language user request.
   - `graders/criterion-<n>.md`: one grader per success criterion, usually `llm` with concrete PASS and FAIL conditions (or `regex` over a produced file).
   - `graders/fired.md`: a `tool_used` grader for `Skill` whose `input_match` names your skill. It reports whether the skill fired and is left out of the score, so the baseline is not penalized for lacking it.
   - `case.yaml` with a `scaffold_script`, only when the task needs fixture files or a git history.

   Exact file contents are in the testing guide, section 4.
2. Run the suite and keep the report local:
   ```bash
   claude plugin eval plugins/<plugin> --case '<name>-*' --runs 3 \
     --max-cost-usd <cap> --no-publish
   ```
   Add `--scaffold` when a case has a scaffold script (it runs your bash as you; only for cases you wrote) and `--allow-tools Bash Edit Write` (narrowed to what the skill needs) when the task must change files.
3. Read the scores. A near-zero difference with `fired` failing means the skill did not fire on that phrasing: that is a step 6 problem. To test the body anyway, add a case whose prompt starts with `/<plugin>:<name>` and run it with `--ablation none`. For a rework, run the same suite from a `git worktree` of the default branch to get the previous version's scores.

**Fallback** for older CLIs: the manual explicit / natural / baseline arms with `claude -p` in the testing guide, section 5.

Grade every run against the step 2 criteria with a quote or file path as evidence, and record it in the worksheet. Pass bar: the skill arm meets every criterion in at least 2 of 3 runs, beats the baseline on at least one criterion that matters to the user, and loses on none. If the baseline already meets everything, the skill is not pulling its weight: narrow it to the part the baseline gets wrong, or drop it. When fixing the body, fix the general cause (a missing step, an unexplained rule, an absent output format) rather than special-casing the fixture.

Commit the behavior cases: the case directories above (runnable), and the same prompts in `plugins/<plugin>/skills/<name>/evals/evals.json` so tools other than Claude Code can read them: `skill_name`, then per case `id`, `prompt`, an optional prose `expected_output` for context, `files`, and an `expectations` list of three to six checkable statements (this marketplace's validator rejects a case without one). Fixture files go under `evals/files/`. If another repo's CONTRIBUTING.md or validator names a different layout or key, follow it.

### 8. Validate

```bash
python3 -I scripts/validate_skills.py                     # the repo validator, when present
python3 -I "${CLAUDE_SKILL_DIR}/scripts/check_skill.py" plugins/<plugin>/skills/<name> \
  --deny '<employer>|<internal-product>|<internal-domain>'
python3 -I "${CLAUDE_SKILL_DIR}/scripts/check_skill.py" --listing .
claude plugin validate . --strict                         # marketplace.json
claude plugin validate plugins/<plugin> --strict          # plugin.json and its skills
claude plugin validate plugins/<plugin>/skills --strict   # SKILL.md frontmatter parse errors
wc -l plugins/<plugin>/skills/<name>/SKILL.md
```

- `check_skill.py` checks name and description rules, links to and from `references/`, misplaced path variables, eval file names and `expectations` lists, stray scratch directories, and private-looking strings (home paths, internal hostnames, private IPs, key or token shapes). Fill `--deny` with your employer, internal product and domain names (case-insensitive) and do not commit that list. If the repo validator also scans a local denylist (this one does; CONTRIBUTING.md says where the file lives), put the same terms there. Then read every example and fixture yourself for borrowed real names, paths and data: no pattern catches a realistic-looking internal ticket.
- `--listing .` totals every skill's description text. Note the total in the PR if it grew.
- Run each bundled script's `--selftest`, and confirm `-h` and `--help` both print usage.
- If the repo validator is missing, say "repo validator absent" in the report and rely on the other checks.

Fix every error your change introduced. Report, do not silently fix, errors that already existed in other skills, and do not loosen the validator to make your skill pass unless changing the rules is the point of the PR (then say so).

### 9. Update the catalog and bump the version

- **README**: add the skill to its plugin's catalog table, matching the existing row format and ordering. The one-line summary should agree with the first clause of the description.
- **Version**: bump `version` in `plugins/<plugin>/.claude-plugin/plugin.json` and in the plugin's entry in `.claude-plugin/marketplace.json`, keeping the two identical. Installed copies are pinned to that string, so without a bump existing users never receive the change. Semver: new skill or capability, minor; wording, description or bug fix, patch; renaming or removing a skill, major (it breaks `/<plugin>:<name>`). If `plugin.json` is missing or has no `version`, say so in the report; do not invent one.
- **Changelog**: add an entry if the repo keeps one.

### 10. Commit and open the PR

1. Stage explicit paths, never everything: the skill directory, its eval case directories, `plugin.json`, the README (and changelog, marketplace file, sibling descriptions you edited). Commit with `git commit -s` when CONTRIBUTING.md asks for a DCO sign-off; follow its CLA instructions if it has them.
2. Confirm the versions agree: `claude plugin tag plugins/<plugin> --dry-run` (it creates nothing, and refuses uncommitted changes, so run it after the commit).
3. Fill the repo's PR template into `<scratch>/pr-body.md` with the evidence: trigger table (final round, held-out, listing state), behavior grading with a before and after on at least one eval prompt, check output, version change, cost. Use the worksheet's section H block.
4. Confirm with the user before pushing; this is a public repo. Then check whether you can push to it:
   ```bash
   gh repo view --json viewerPermission,nameWithOwner
   ```
   - `ADMIN`, `MAINTAIN` or `WRITE`: `git push -u origin <branch>`, then `gh pr create --title "Add <plugin>:<name> skill" --body-file <scratch>/pr-body.md`.
   - Anything else (most outside contributors): push to a fork, then open the PR against the upstream:
     ```bash
     gh repo fork --remote --remote-name fork
     git push -u fork <branch>
     gh pr create --repo <owner>/<repo> --head <your-login>:<branch> \
       --title "Add <plugin>:<name> skill" --body-file <scratch>/pr-body.md
     ```
     `<owner>/<repo>` is the `nameWithOwner` printed above; `<your-login>` comes from `gh api user -q .login`.
   Leave "allow edits from maintainers" on (the default; do not pass `--no-maintainer-edit`) and say so in the report.

The commit and PR prose can come from the skills under Related skills; the evidence tables still come from your runs.

## Report format

```
## <plugin>:<name> (new | extended <existing> | reworked)
Files: <paths created or changed>
Description (<N> chars): <final description>

Triggering (runs per prompt: <R>, model: <model>, CLI: <version>)
Listing: <within budget | over budget: N skills, C chars > B; full-listing rerun: x/y>
| Case | Expect | Hits | Verdict | Route | Other skills that fired |
Held-out: <x>/<y> passed   Sibling regressions: <none | list>

Behavior (<runs> runs per arm, via <claude plugin eval | manual arms>)
| Criterion | With skill | Baseline | Evidence |

Checks: repo validator <pass | errors | absent>   check_skill <pass | errors>   plugin validate <pass | warnings>
Catalog: <README row added>   Version: <old> -> <new | no version in plugin.json>
Cost: <total across all runs>
PR: <url, maintainer edits allowed | "ready, waiting for your go-ahead to push">
Not verified: <anything that could not run here, and the weaker substitute used>
Open risks: <collisions seen, flaky cases, listing budget, untested paths, missing repo files>
```

## Common mistakes

- **Testing in the authoring session or from the authoring checkout.** The session already knows the skill and the checkout primes routing toward it. Only fresh `claude -p` runs from a user-like directory count.
- **Blaming wording for a listing-budget miss.** When the listing is over budget, a new skill's description is the first dropped. Read the `Listing:` line and rerun with `--listing-budget` before rewording.
- **A long or summarizing description.** Every character is paid by every user in every session and squeezes siblings out of the listing, and a table of contents ("covers steps one through nine...") or a synonym list tells the router nothing about the user's situation. Stay near 450 characters of capability, user phrasings and a boundary.
- **Only positive test prompts.** Descriptions fail on near misses. A skill that fires on everything passes every positive test and hijacks its siblings.
- **Tuning to the test set.** Quoting test prompts in the description or adding one-off phrases until each case flips. Held-out prompts exist to catch this.
- **Trusting a run with errors.** A case where runs errored can look like a pass. The checker marks it inconclusive and exits 3; rerun it.
- **Duplicating a sibling** instead of extending it or naming it as the handoff.
- **No baseline.** Without a no-skill arm you cannot tell whether the skill helped, hurt, or only cost context.
- **Invented commands or flags.** Every command in a public skill gets copied into real terminals. Check each one.
- **Path variables in the wrong file.** The skill-directory variable resolves only in SKILL.md (and `allowed-tools`): copied from a reference file into a shell, it expands to an empty path, and in SKILL.md prose it turns into your machine's absolute path. Use placeholders in references.
- **Drifting from the house conventions.** Ad hoc headings, a stale plugin or skill name in a cross-reference, a reworded shared block, or eval checks under a key the validator does not read. Read CONTRIBUTING.md and the validator first (step 1) and let them win.
- **Everything in SKILL.md**, or references nobody can find (unlinked, or linked without a "read when"). `check_skill.py` flags unlinked references.
- **Forgetting the version bump.** Installed users stay on the old copy.
- **Treating `claude plugin validate` as the whole check.** It catches manifest and frontmatter parse errors, not naming, description quality, links or repo conventions.
- **Pushing to the upstream without write access**, or skipping a required sign-off. Use the fork path in step 10.
- **Leaking private context**: internal paths, hostnames, tool names or examples lifted from an employer's codebase.
- **Copying another skill's text.** Learn from other skills' ideas; write your own words, structure and examples. Originality matters in a public marketplace.

## Related skills

- `workflow:commit-message`: drafts the commit message in step 10.
- `workflow:pr-description`: drafts the PR body around the worksheet's evidence block in step 10.
- `workflow:git-worktrees`: builds the skill in an isolated worktree when the checkout has unrelated work in progress (step 1).
- `implementation:docs-lookup`: confirms a frontmatter key, CLI flag or setting against the current Claude Code docs before it goes into a skill.
- `review-suite:pr-review`: reviews someone else's skill PR, rather than authoring one.
- `implementation:brainstorm-spec` and `implementation:build-feature`: take over when the request turns out to be a product feature, not a skill.

If a skill named here isn't installed, give the short version inline and list the deeper pass as a follow-up.

## Reference files

- [references/skill-skeleton.md](references/skill-skeleton.md): read when starting the draft (step 5). Directory layout with the canonical eval files, SKILL.md and reference templates in the house skeleton, the literal path-variable forms, a small worked example, and the pre-test self-review checklist.
- [references/description-guide.md](references/description-guide.md): read when writing or tuning the description (steps 5-6). The listing budget, anatomy, good and bad pairs, sibling boundaries, symptom-to-fix table.
- [references/evaluation-worksheet.md](references/evaluation-worksheet.md): open at step 2 and fill as you go. Intent card, test prompts, trigger rounds, behavior grading, cost, decision log, and the PR evidence block.
- [references/testing-guide.md](references/testing-guide.md): read before the first paid run (steps 3, 6 and 7). What a fresh session loads, the checker and its exit codes, the listing budget, `claude plugin eval` case files, the manual fallback arms, permissions, cost, noisy results, troubleshooting.
- `${CLAUDE_SKILL_DIR}/scripts/trigger_check.py`: the trigger-rate harness (steps 3 and 6). `--help` for options; `--dry-run` prints the command and session count without spending anything; `--selftest` checks its scoring rules against a fake CLI at no cost, and must pass after any change to the script.
- `${CLAUDE_SKILL_DIR}/scripts/check_skill.py`: static checks for a skill directory and the listing total (steps 5 and 8). `--help` for options; `--selftest` checks its rules on throwaway skills, and must pass after any change to the script.
