# Testing a skill

A skill can fail in two independent ways, and each needs its own test:

- **Routing.** Claude reads every installed skill's `description` and decides whether to load one. A skill that never loads does nothing; a skill that loads for its sibling's requests does harm. Trigger evals measure this.
- **Behavior.** Once loaded, the body has to produce visibly better work than Claude does with no skill at all. Behavior evals measure this, always against a baseline.

Test both in fresh sessions. The session that wrote or edited a skill already knows the skill exists and what it is for, so whatever it does proves nothing about a real user's session.

The [`skill-dev:create-skill`](../plugins/skill-dev/skills/create-skill/SKILL.md) skill runs this whole process for you: it writes the cases, prices the runs, drives the trigger checker and the behavior comparison, and drafts the evidence for your pull request. Install the `skill-dev` plugin (or load it with `--plugin-dir ./plugins/skill-dev`) and run `/skill-dev:create-skill path/to/the/skill`. This page explains what it does, so you can run the steps by hand or judge someone else's results. The deeper reference is its [testing guide](../plugins/skill-dev/skills/create-skill/references/testing-guide.md).

Run every command below from the repository root unless it says otherwise.

## 1. Static checks first

They are free and catch most loading problems before you spend anything on model runs.

```bash
python3 -I scripts/validate_skills.py
claude plugin validate . --strict
for p in plugins/*/; do claude plugin validate "$p" --strict; done
```

- The repository validator checks frontmatter keys and limits, that `name` matches the folder, links and `references/` coverage, the size of `SKILL.md`, the shape of both eval files, the manifests and their versions, and that every copy of a shared block is identical. With a local denylist present it also scans every file for terms that must never be published (see CONTRIBUTING.md).
- `claude plugin validate .` checks the marketplace manifest. Validating each plugin directory checks its `plugin.json` and also parses every `SKILL.md` frontmatter in it, which is where a YAML mistake would otherwise silently drop all of a skill's metadata at runtime.
- `create-skill` also bundles a static checker for a single skill and for the size of the whole listing:

  ```bash
  python3 -I plugins/skill-dev/skills/create-skill/scripts/check_skill.py plugins/<plugin>/skills/<skill>
  python3 -I plugins/skill-dev/skills/create-skill/scripts/check_skill.py --listing .
  ```

## 2. The two eval files

Every skill commits both files in its own `evals/` folder, so the next person can rerun them.

### `evals/trigger-evals.json`: should it load?

A JSON array of queries, each with `should_trigger`. Every `false` query names where it belongs with `should_route_to`: the `plugin:skill` that should take it, or `none (reason)` when no skill should load. The trigger checker uses it to verify routing, and the validator warns when it is missing:

```json
[
  {"query": "the nightly export job has been timing out since tuesday, can you look at reports/export.sql", "should_trigger": true},
  {"query": "add an index so this migration stops locking the orders table", "should_trigger": false, "should_route_to": "data-api:db-migration-safety"}
]
```

Write queries the way people actually type them: lowercase, abbreviated, with project details, sometimes without naming the task at all. Include near misses that share vocabulary with the skill but belong to a sibling; those are where descriptions fail. When a phrasing could go to two skills, add it to one skill's file as `true` and to the other's as `false`, so both sides are tested.

### `evals/evals.json`: does it do the job well?

```json
{
  "skill_name": "query-review",
  "evals": [
    {
      "id": 1,
      "prompt": "Postgres 16. This report query got 10x slower after we added a filter on status ... (the full request, as a user would write it)",
      "expected_output": "Optional prose describing a good answer, for human readers.",
      "files": ["evals/files/slow-report/query.sql", "evals/files/slow-report/explain.txt"],
      "expectations": [
        "Reads the EXPLAIN output and names the node where the time goes",
        "Proposes an index whose column order matches the filter and the sort",
        "Says how to confirm the fix (rerun EXPLAIN ANALYZE on realistic data)",
        "Does not recommend dropping the existing index without checking what else uses it"
      ]
    }
  ]
}
```

- At least three realistic prompts per skill. Fixture files go under `evals/files/`, and `files` lists them relative to the skill folder.
- Each prompt gets three to six `expectations`. The validator requires a non-empty list and warns outside three to six; a prose `expected_output` alone does not count.
- When a case needs a git history, a dirty working tree, or a fake CLI (a canned `gh`), ship a `setup.sh` under `evals/files/` that builds it into a fresh directory, and list it in `files`, so a rerun starts from the same state.
- Write expectations that someone can check against a transcript without arguing about taste: a fact the answer must state, a command it must run, a file it must or must not change, a section the report must contain. Include at least one negative expectation for anything risky ("does not push", "does not post a comment"), because safe behavior is part of the job.
- Fixtures that need credentials or hostnames use obvious fakes (`example-not-a-real-key-0000`, `db.internal`, `@example.com`).

## 3. Trigger evals: run them in fresh sessions

Three rules make a trigger run mean something:

1. **Load every plugin in the repository**, not only yours, so sibling skills compete for each prompt the way they will for users.
2. **Run from a directory that looks like where users ask.** For most skills that is a new empty temporary directory. Never run from this checkout: its files point Claude straight at your skill.
3. **Take the tools away.** A routing check needs no writes, shell or MCP servers, and removing them makes it safe and cheap.

One prompt, by hand (this prints the id of every skill the session invoked; no output means none did):

```bash
REPO=$(git rev-parse --show-toplevel)
args=(); for d in "$REPO"/plugins/*/; do args+=(--plugin-dir "$d"); done
cd "$(mktemp -d)" && claude -p "why is this postgres query so slow? it filters on date(created_at)" \
  "${args[@]}" \
  --output-format stream-json --verbose --max-turns 3 --no-session-persistence \
  --permission-mode dontAsk --strict-mcp-config \
  --disallowed-tools "Write,Edit,NotebookEdit,Bash" < /dev/null \
| jq -r 'select(.type=="assistant") | .message.content[]
         | select(.type=="tool_use" and .name=="Skill") | .input.skill'
```

`--output-format stream-json` needs `--verbose` in print mode, and `< /dev/null` stops the CLI from waiting for input on stdin. `--max-turns` is accepted by `claude -p` although `claude --help` doesn't list it.

A whole file, several runs per prompt, with `create-skill`'s checker:

```bash
args=(); for d in plugins/*/; do args+=(--plugin-dir "$d"); done
python3 -I plugins/skill-dev/skills/create-skill/scripts/trigger_check.py "${args[@]}" \
  --skill <plugin>:<skill> \
  --cases plugins/<plugin>/skills/<skill>/evals/trigger-evals.json \
  --runs 3 --dry-run
```

`--dry-run` prints the command and the number of sessions it would start, and spends nothing. Drop it to run for real. The checker runs every session in a fresh temporary directory with write and shell tools removed, prints a per-prompt table, a cost line, and a `Listing:` line, and exits `0` when every case passed, `1` when one failed, `3` when a run errored and the result is inconclusive, and `2` on a setup problem.

How to read the results:

- **Pass bar.** A should-trigger prompt fires in at least two of three runs. A should-not prompt fires in none of three (at most one of five on a longer run). Near misses go to the sibling named in `should_route_to`.
- **Check the `Listing:` line before rewording anything.** Claude Code gives all skill descriptions one shared budget of about 1% of the context window, and when it overflows it drops the descriptions of the least-used skills first, which includes any skill nobody has used yet. A miss while the listing is over budget may say nothing about your wording; rerun the failing cases with `--listing-budget 200000` to tell the two apart.
- **Rerun the whole file after every description change.** A change that rescues one prompt often breaks another.
- **Rerun the nearest siblings' trigger files** with your change in place, to show you didn't take their prompts. `--json-out` saves a run, and `--compare <earlier.json>` lists every case whose verdict changed.
- **Never paste a test prompt into the description.** That tunes the skill to the test instead of to users. Keep a few prompts back as a held-out set and run them once at the end.

The review skills share their territory with Claude Code's built-in `/code-review` and `/security-review` commands, which can win generic phrasings such as "review this". Expect that in trigger results, and keep the review skills' trigger prompts specific to what each skill does differently.

## 4. Behavior evals: with and without the skill

The question is not "is the output good" but "is it better than without the skill". Run the same prompt, on the same fixture, with the same permissions, in two arms (with the skill and without it), and grade both against the `expectations` written before you looked at either output.

### Preferred: `claude plugin eval`

`claude plugin eval` runs every case in an isolated session (temporary home, only the plugin under test, no personal skills, settings, hooks, CLAUDE.md or MCP servers) and adds a no-plugin baseline arm by default. That isolation is what makes the comparison clean. Check that your CLI has it with `claude plugin eval --help`.

Its cases are directories under the plugin's `evals/` folder, not inside `skills/`: `plugins/<plugin>/evals/<skill>-<case>/` holding a `prompt.md` (run settings in frontmatter, the user's request in the body) and a `graders/` folder with one grader file per expectation. Running `claude plugin eval init --bare <skill>-<case>` from inside `plugins/<plugin>/` writes a blank case into that plugin's `evals/` folder to start from, and the `create-skill` testing guide shows complete case and grader files, including a grader that reports whether the skill fired without counting it against the baseline.

```bash
claude plugin eval plugins/<plugin> --case '<skill>-*' --runs 3 \
  --max-cost-usd 5 --no-publish
```

- `--no-publish` keeps the HTML report on your machine. Without it the report is published to claude.ai when your account supports that.
- `--max-cost-usd` stops launching runs at the ceiling and reports what finished.
- Add `--allow-tools` (for example `--allow-tools Bash Edit`) only when the task has to run commands or change files, and `--scaffold` only for case setup scripts you wrote yourself, because it runs them as you.
- Results land under `plugins/<plugin>/evals/results/`. Don't commit them.

### Fallback: three arms with `claude -p`

Without `claude plugin eval`, run each prompt in fresh `claude -p` sessions: an **explicit** arm (`/<plugin>:<skill> ...`, which tests the body even while routing is still being tuned), a **natural** arm (the plain request with the plugin loaded), and a **baseline** arm (the plain request with no `--plugin-dir`). Copy the fixture into a new temporary directory for every run, since runs change files, and give every arm identical flags:

```bash
P="$(git rev-parse --show-toplevel)/plugins/<plugin>"
cd "$(mktemp -d)" && cp -R "$P/skills/<skill>/evals/files/<fixture>/." . && \
claude -p "<plain-language request>" --plugin-dir "$P" --add-dir "$P" \
  --output-format json --max-turns 30 --max-budget-usd 2 --no-session-persistence \
  --permission-mode acceptEdits --strict-mcp-config \
  --disallowed-tools "Bash(git push *)" < /dev/null > result.json
jq -r '.result' result.json
```

For the baseline arm, drop `--plugin-dir` and `--add-dir`. `--add-dir` lets the skill arm read its own `references/` and run its own `scripts/`, which sit outside the run's working directory.

These sessions load your personal skills, settings and installed plugins in every arm. If you installed this marketplace's plugins, the "baseline" still has the skill: disable the plugin for the baseline runs (`claude plugin disable <plugin>@engineering-skills`, then `claude plugin enable` it afterwards) or use `claude plugin eval`. Mention any such contamination in the pull request.

### Grading

- Run each arm at least three times; one run of a language model is an anecdote.
- Grade every expectation as met or not met for every run, quoting the line of output or naming the file that shows it.
- **Pass bar:** the skill arm meets every expectation in at least two of three runs, beats the baseline on at least one expectation that matters to the user, and is worse on none. If the baseline already meets everything, the skill isn't earning its place in the listing: narrow it to what the baseline gets wrong, or drop it.
- When the skill arm fails, fix the general cause in the body (a missing step, a rule with no reason, an absent output format), not the specific fixture.

## 5. Cost and safety

- Every trigger or behavior run is a real, billed session. Count sessions before running (`--dry-run`, or cases times runs times arms), and cap spending with `--max-cost-usd` (`claude plugin eval`) or `--max-budget-usd` and `--max-turns` (`claude -p`).
- Run behavior evals on fixtures in temporary directories, never on a real project that holds credentials or a remote you can push to.
- Don't run an eval suite, fixture script or skill script from a pull request until you've read it. An eval run executes the plugin and its cases on your machine as you.
- Don't use `--dangerously-skip-permissions` outside a disposable container or VM with no credentials.

## 6. Put the evidence in the pull request

The review bar in [CONTRIBUTING.md](../CONTRIBUTING.md) asks for a before and after on at least one eval prompt. A compact version:

```markdown
### Evidence

Static: validate_skills.py pass · claude plugin validate --strict pass (all plugins)

Triggering (3 runs per prompt, claude 2.x.y, default model; listing within budget)
| Query | Expect | Before | After |
|---|---|---|---|
| "the nightly export job has been timing out ..." | trigger | 1/3 | 3/3 |
| "add an index so this migration stops locking ..." | no (db-migration-safety) | 0/3 | 0/3 |

Behavior (eval 1, 3 runs per arm, via claude plugin eval)
| Expectation | With skill | Baseline |
|---|---|---|
| Names the plan node where the time goes | 3/3 | 1/3 |
| Index column order matches filter and sort | 3/3 | 0/3 |

Cost: $X.XX total. Not tested: <anything you skipped, and why>
```

"Before" is the current default branch for a change to an existing skill, and the no-skill baseline for a new one. Say what you didn't test; a reviewer can work with an honest gap but not with a hidden one.
