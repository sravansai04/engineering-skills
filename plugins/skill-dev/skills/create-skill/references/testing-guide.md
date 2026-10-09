# Testing guide: fresh-session trigger and behavior runs

Read this before the first paid run (steps 3, 6 and 7 of SKILL.md). Two placeholders recur:

- `<scratch>` is the private temp directory created in step 1.
- `<checker>` is the absolute path of this skill's `scripts/trigger_check.py`, which SKILL.md printed in step 1. This file is not pre-processed the way SKILL.md is, so no variable here would expand; paste the real path.

Every block below is self-contained: each Bash tool call starts a fresh shell, so a block never relies on a variable set in another one. Run them from the repo root. Every flag is a documented Claude Code CLI flag; if one errors on your version, check `claude --help` and upgrade rather than improvising a substitute.

Contents:
1. What a fresh session loads, and the listing budget
2. Trigger tests with the checker
3. One-off manual trigger check
4. Behavior runs with `claude plugin eval`
5. Fallback: manual explicit / natural / baseline arms
6. Permissions for unattended runs
7. Cost and time
8. Reading noisy results
9. Troubleshooting

---

## 1. What a fresh session loads, and the listing budget

A `claude -p` session started from a shell loads built-in skills, the user's personal skills (`~/.claude/skills/`), project skills of the directory it starts in, installed plugins, and anything passed with `--plugin-dir`. The stream's first event lists them:

```bash
REPO=$(git rev-parse --show-toplevel)
args=(); for d in "$REPO"/plugins/*/; do args+=(--plugin-dir "$d"); done
cd "$(mktemp -d)" && claude -p "hi" "${args[@]}" \
  --output-format stream-json --verbose --max-turns 1 < /dev/null \
  | jq -c 'select(.type=="system" and .subtype=="init") | {skills, plugins}'
```

This spends one short session.

What follows from that:

- **Run from a directory that looks like where users invoke the skill.** For a general skill that is an empty temp directory (the checker's default). For a skill whose trigger depends on the project (a framework, a repo layout, this marketplace itself), build a minimal fixture with the files that matter and pass it with `--cwd`; an empty directory would hide the context real routing sees and produce false misses. Never run from the authoring checkout: its own files prime routing toward the skill you are testing.
- **Load every plugin in the repo**, not only yours, so siblings compete for prompts the way they will after release. Each `--plugin-dir` takes one plugin root (the directory holding `skills/` and `.claude-plugin/`). A `--plugin-dir` copy takes precedence over an installed plugin of the same name for that session, so a contributor who also has this marketplace installed still tests the working tree.
- **The listing has a budget, and new skills lose first.** The listing always contains every skill's name, but its descriptions must fit a character budget of about 1% of the model's context window. Over budget, Claude Code drops descriptions starting with the skills the user invokes least, and a skill nobody has invoked yet (yours) is first in line. Consequences:
  - The init event's `skills` list always includes your skill, so "loaded" does not mean "its description was visible".
  - Results depend on the model: recent CLIs logged a budget of about 8,000 characters on a 200K-context model and about 30,000 on a 1M-context model, so `--model haiku` and a 1M default can disagree for this reason alone.
  - Results depend on the contributor's own invocation history and personal skills, which decide what else survives.
  - To see the state: the debug log (`--debug` or `--debug-file <path>`) contains `Skill listing over budget: N skills, C chars > B budget` when it is over; in an interactive session, `/context` shows the Skills row after the budget is applied and `/doctor` estimates the biggest contributors. The checker reads the debug log for you and prints a `Listing:` line.
  - To change it: the `skillListingBudgetFraction` setting (`0.02` = 2%), or the `SLASH_COMMAND_TOOL_CHAR_BUDGET` environment variable as a fixed character count (the checker's `--listing-budget` sets it); `skillListingMaxDescChars` changes the per-entry cap; `skillOverrides` can list a low-priority skill as `"name-only"`. These are user-side settings; a skill cannot rely on users changing them.
- **Personal skills still compete.** That is realistic, but it makes results machine-specific. Record the init skill list in the worksheet header when a personal skill fires on your prompts.
- **Do not use `--bare` or `--safe-mode` for trigger tests.** Both change what loads (and `--bare` changes authentication), so the result no longer reflects a real user's session.
- **Never test in the authoring session.** It knows the skill exists and what it is for.

## 2. Trigger tests with the checker

The checker (standard library only) runs each prompt in a new session and stops it at the first `Skill` tool call. Each session runs with `--permission-mode dontAsk` (anything that would need approval is refused instead of asked), with `Write`, `Edit`, `NotebookEdit` and `Bash` removed, and with `--strict-mcp-config` (your MCP servers stay off; `--with-user-mcp` keeps them). It cannot write files or run shell commands; read-only tools still work, so it can look around before choosing.

```bash
args=(); for d in plugins/*/; do args+=(--plugin-dir "$d"); done
python3 -I <checker> "${args[@]}" \
  --skill <plugin>:<name> \
  --cases <scratch>/cases.json \
  --runs 3 --jobs 4 \
  --json-out <scratch>/trigger-r<round>.json
```

Cases file: a JSON array. The canonical committed form, used by `evals/trigger-evals.json`:

```json
[
  {"query": "...", "should_trigger": true},
  {"query": "...", "should_trigger": false, "should_route_to": "workflow:pr-description"}
]
```

The form `{"id": "t1", "prompt": "...", "expect": "trigger" | "no-trigger"}` is accepted too, so every sibling's committed trigger file runs as-is, whatever it is called (`ls plugins/<p>/skills/<s>/evals/trigger*.json`). A `should_route_to` value starting with `none` means no skill should be needed.

Rerun a sibling's cases with your skill present and compare against the snapshot taken in step 3:

```bash
args=(); for d in plugins/*/; do args+=(--plugin-dir "$d"); done
python3 -I <checker> "${args[@]}" \
  --skill <sibling-plugin>:<sibling> \
  --cases plugins/<sibling-plugin>/skills/<sibling>/evals/<trigger-file>.json \
  --compare <scratch>/sibling-<sibling>-before.json
```

Useful options:

| Option | Default | When to change it |
|---|---|---|
| `--runs` | 3 | 5 for borderline cases and before merging |
| `--jobs` | 4 | lower if you hit rate limits (errored runs make cases inconclusive) |
| `--max-turns` | 3 | the model sometimes reads a file before choosing; raise only if runs end with no decision |
| `--min-hit-rate` | 0.66 | should-trigger and `should_route_to` pass threshold |
| `--max-false-rate` | 0.2 | should-NOT pass threshold (0 of 3, at most 1 of 5) |
| `--model` | CLI default | test with the model most users run; add a second if users vary (the listing budget differs by context size) |
| `--cwd` | fresh empty temp dir | a fixture project, for skills whose trigger depends on the project |
| `--listing-budget` | Claude Code's | a large value (200000) shows every description, to separate wording from listing space |
| `--compare` | off | an earlier `--json-out` file; lists cases whose verdict changed |
| `--dry-run` | off | print the exact command (shell-quoted) and the planned session count without spending anything |
| `--selftest` | off | after editing the checker itself: replays scripted outcomes through a fake `claude` and checks every scoring rule, at no cost |

Output:

```
id           expect       hits err  verdict route      other skills that fired
t1           trigger       3/3    0  PASS    -          -
n1           no-trigger    0/3    0  PASS    3/3        workflow:pr-description x3
n2           no-trigger    0/3    1  ERROR   2/2        workflow:commit-message x2

2/3 cases passed, 0 failed, 1 inconclusive, 1 run errors (runs per case: 3; ...; 2.1.x (Claude Code))
Listing: OVER BUDGET in 9/9 sessions (25 skills, 16921 chars > 8000). ...
Cost: $0.21 across 3 sessions that ran to the end (about $0.07 each); 6 sessions stopped at a Skill call ...
```

How it scores, so you can trust a PASS:

- Hits count against the runs you asked for, not the runs that happened to finish. A case needs at least two thirds of its runs to finish, or it is ERROR.
- Errored runs are tried both ways (as fires and as misses). If the verdict depends on how they resolve, the case is ERROR (inconclusive), never PASS.
- A skill invoked by bare name counts only when exactly one loaded skill has that name, so a personal skill with the same name cannot pass for yours.
- `route` shows how often a near miss went to its `should_route_to` sibling; below `--min-hit-rate` the case FAILs. `n/a` means that sibling was not loaded; `none x/y` counts runs where no skill fired.

Exit codes: `0` every case passed and no run errored; `1` at least one case failed; `3` nothing failed but a run errored or a case was inconclusive (rerun); `2` setup problem. The most common setup problem is "skill was not in the session's skill list", which means the skill failed to load (section 9), not that the description is weak.

The skill id is `<plugin>:<name>`, where `<plugin>` is the `name` in the plugin's `plugin.json` (or the directory name when there is no manifest).

## 3. One-off manual trigger check

For a single prompt, without the script:

```bash
REPO=$(git rev-parse --show-toplevel)
cd "$(mktemp -d)" && claude -p "<prompt>" \
  --plugin-dir "$REPO/plugins/<plugin>" \
  --output-format stream-json --verbose \
  --max-turns 3 --no-session-persistence \
  --permission-mode dontAsk --strict-mcp-config \
  --disallowedTools "Write,Edit,NotebookEdit,Bash" < /dev/null \
| jq -r 'select(.type=="assistant") | .message.content[]
         | select(.type=="tool_use" and .name=="Skill") | .input.skill'
```

Prints the id of each skill the model invoked; no output means none fired. `--output-format stream-json` requires `--verbose` in print mode, and `< /dev/null` stops the CLI from waiting for piped input. Without `--permission-mode`, the session inherits your configured default mode, which may let tools run unprompted.

## 4. Behavior runs with `claude plugin eval`

Requires Claude Code 2.1.269 or later (`claude plugin eval --help` answers) and git 2.31 or later. Each run gets a temporary home, an empty working directory and only the plugin under test: no personal skills, settings, hooks, CLAUDE.md, memory or MCP servers. That makes the with/without comparison clean. It also means the skill competes in a near-empty listing, so the `fired` rate here is optimistic about routing; section 2 measures routing in a crowded one.

Layout (cases live at the plugin level; `--eval-dir` refuses anything under `skills/`):

```
plugins/<plugin>/evals/
└── <name>-<case>/                 # case name = directory name; prefix it with the skill name
    ├── prompt.md                  # frontmatter: run settings; body: the user's request
    ├── case.yaml                  # optional: fixture setup
    ├── fixture.sh                 # optional: builds the workspace (needs --scaffold)
    └── graders/
        ├── fired.md               # did the skill fire (reported, not scored)
        ├── criterion-1.md         # one grader per success criterion
        └── criterion-2.md
```

`prompt.md`. Write the request as a user would, without naming the skill. Read-only tools listed here are granted; anything else also needs `--allow-tools` on the command line.

```markdown
---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Bash, Edit]
---

the orders migration in migrations/0042_add_status.sql keeps timing out on staging. can you check it before I merge?
```

`graders/fired.md`. Passes when the skill was invoked, by bare or namespaced name. In a with/without run it is shown as a plugin-fired indicator and left out of the score, so the baseline is not penalized for lacking your skill.

```markdown
---
type: tool_used
tool: Skill
input_match: '"skill"\s*:\s*"(?:[\w-]+:)?<name>"'
---
```

`graders/criterion-1.md`. An `llm` grader judged by a second model; write concrete PASS and FAIL conditions. For long output (a generated file), prefer a `regex` grader with `target: { source: file, path: <path> }`, which checks the whole file the same way every time.

```markdown
---
type: llm
---

PASS if the reply says that adding a NOT NULL column without a default rewrites or locks the table, and proposes a safe order (add nullable, backfill in batches, then add the constraint).
FAIL if it approves the migration as written, or gives only generic advice without naming the lock.
```

Other grader types: `regex` (`pattern`, `flags`, `match: not_contains`, `target`), `tool_used` (`tool`, `input_match`, `min`, `max`; `min: 0` and `max: 0` with `arm: both` asserts something never happened, in both arms), `tool_order` (`before`, `after`), `file_exists` (`path`, `exists`; counts only files created during the run). There are no custom-code graders.

`case.yaml` plus `fixture.sh`, when the task needs files or history. The script runs in the empty workspace before Claude starts, with a minimal environment (your `PATH`, a temporary `HOME`, `TMPDIR`) and a 120-second limit, so it sets its own git identity:

```yaml
schema_version: "1.1"
name: <name>-risky-migration
context:
  scaffold_script: fixture.sh
```

```bash
#!/usr/bin/env bash
set -euo pipefail
mkdir -p migrations
cat > migrations/0042_add_status.sql <<'SQL'
ALTER TABLE orders ADD COLUMN status text NOT NULL;
SQL
git init -q
git add -A
git -c user.name=fixture -c user.email=fixture@example.com commit -qm fixture
```

Run the suite. The no-plugin baseline arm runs by default (`--ablation with-without`):

```bash
claude plugin eval plugins/<plugin> --case '<name>-*' --runs 3 \
  --max-cost-usd 10 --no-publish --threshold 0.67 \
  --scaffold --allow-tools Bash Edit --json <scratch>/eval-r1.json
```

- `--scaffold` runs your fixture scripts as you; pass it only for cases you wrote. `--allow-tools` grants the gated tools the task needs; keep it as narrow as the skill's real work.
- `--max-cost-usd` stops launching runs at the ceiling and exits 2 with partial results. `--threshold` (default 1.0) sets the score below which a case exits 1.
- `--no-publish` keeps the HTML report on your machine. The JSON file (`--json`) holds per-run grader verdicts for the worksheet.
- `--judge-model sonnet` when the default judge marks a correct but differently formatted answer wrong (a negative difference while `fired` passes is the usual sign).
- The first run in a directory asks you to trust it. Answer once in a terminal; `--trust-plugin` is for CI on a plugin you would run yourself.
- Results are written under `plugins/<plugin>/evals/results/`. Do not commit them.

To test the body even while routing is being tuned, add a case whose prompt begins with `/<plugin>:<name>` and run it with `--ablation none` (a baseline session cannot run your command). For a rework, check out the default branch in a worktree (`git worktree add <scratch>/base origin/main`) and run the same suite there for the previous version's scores.

## 5. Fallback: manual explicit / natural / baseline arms

Use this only when `claude plugin eval` is unavailable. Unlike section 4, these sessions load your personal skills, settings and hooks in every arm, baseline included, so note that in the PR as a contamination risk.

Write the whole block to `<scratch>/arms.sh` (filling the placeholders), then run it in one call with `bash <scratch>/arms.sh`. It builds the fixture once, copies it fresh for every run (runs modify files), and prints the path of each run's JSON result.

```bash
#!/usr/bin/env bash
set -uo pipefail
REPO=/absolute/path/to/your/checkout      # fill in: the repo root
P="$REPO/plugins/<plugin>"
FIX=$(mktemp -d)/fixture
mkdir -p "$FIX" && cd "$FIX" && git init -q
# ...create the files that exhibit the problem here...
git add -A && git -c user.name=fixture -c user.email=fixture@example.com commit -qm fixture

PERMS=(--permission-mode acceptEdits --strict-mcp-config
       --allowedTools "Bash(git diff *)" "Bash(npm test *)"
       --disallowedTools "Bash(git push *)")

run() {  # usage: run <label> <prompt> [extra claude flags...]
  local label=$1 prompt=$2; shift 2
  local dir; dir=$(mktemp -d)/$label && cp -R "$FIX" "$dir" && cd "$dir" || return
  claude -p "$prompt" --output-format json --max-turns 30 \
    --no-session-persistence --max-budget-usd 2 \
    "${PERMS[@]}" "$@" < /dev/null > "$dir.json"
  echo "$dir.json"
}

for i in 1 2; do
  run "explicit-$i" "/<plugin>:<name> <args>" --plugin-dir "$P" --add-dir "$P"
  run "natural-$i"  "<plain-language prompt>"  --plugin-dir "$P" --add-dir "$P"
  run "baseline-$i" "<plain-language prompt>"
done
```

Replace the example `--allowedTools` commands with the ones the skill actually runs, identically for every arm. `--add-dir "$P"` lets the skill arms read their own `references/` and run their own `scripts/`, which sit outside the run's working directory. For a rework, the baseline loads the previous version instead: `--plugin-dir <scratch>/base/plugins/<plugin>` from a worktree of the default branch.

Read each result. `<out>` is a printed `.json` path, and `<run-dir>` is the same path without `.json`:

```bash
jq -r '.result' <out>                                        # what the user would see
jq '{is_error, num_turns, total_cost_usd, permission_denials}' <out>
git -C <run-dir> status --short && git -C <run-dir> diff     # what it changed on disk
```

- **Explicit** tests the body even if routing is still being tuned. **Natural** catches the case where the skill fires but the phrasing leads the body astray. **Baseline** shows what the model does without the skill.
- A non-empty `permission_denials` means the run was hobbled, not that the skill failed: a denied read of `references/` or a denied test command turns the comparison into noise. Fix the permissions (section 6) and rerun before grading. Check this on the first run of each arm, before spending on the rest.
- For the full transcript, rerun an arm with `--output-format stream-json --verbose > run.jsonl` and read the `assistant` and `user` events. Wasted steps (re-reading files, retrying commands) that the final answer hides are signals to trim or clarify the body.

## 6. Permissions for unattended runs

A `-p` run has nobody to answer a permission prompt. What would prompt depends on the user's settings and the permission mode, which is why results differ between machines when the mode is left implicit. Set it explicitly and identically for every arm:

- `--permission-mode dontAsk` refuses anything that would prompt. The trigger checker uses it: routing needs no permissions.
- `--permission-mode acceptEdits` lets a run edit files in its working directory. It does not approve most shell commands, and reads or writes outside the working directory are still refused.
- `--add-dir <path>` adds a directory the run may use: the plugin directory (so the skill can read its references and run its scripts), or a scratch directory.
- `--allowedTools "Bash(npm test *)" "Bash(git diff *)"` pre-approves only the commands the skill needs. Prefer this to broad approval.
- `--disallowedTools "Bash(git push *)"` blocks anything that would leave the machine.
- `--strict-mcp-config` with no `--mcp-config` starts no MCP servers, which removes their side effects and their variance between machines.
- `--dangerously-skip-permissions` removes all checks. Use it only inside a disposable container or VM with no credentials and no network access you care about.

In `claude plugin eval`, the equivalents are `allowed_tools` in `prompt.md` (read-only tools) plus `--allow-tools` on the command line (everything else).

## 7. Cost and time

- Price before you spend. `--dry-run` prints the session count; one `--runs 1` case prices a session (the checker's `Cost:` line). A trigger session is about one model turn with the whole skill listing in context. Show sessions x price to the user and get an OK before a full round.
- A behavior run is a full task. Cap it with `--max-cost-usd` (`claude plugin eval`) or `--max-budget-usd` and `--max-turns` (manual arms), and read the cost from the eval report or `total_cost_usd`.
- Record the actual total in worksheet F and in the report.
- Do not shrink the final round to save money. Tune with `--runs 1` if you must, then confirm with `--runs 3` (or 5 for borderline cases) before the PR.

## 8. Reading noisy results

Routing is not deterministic. Treat rates, not single runs, as the signal:

| Result | Reading | Action |
|---|---|---|
| 3/3 or 0/3 as expected | Stable | Done for that case. |
| 2/3 on a should-trigger | Passing but borderline | Rerun with `--runs 5`; if it drops below 3/5, improve the description. |
| 1/3 on a should-NOT | Leaking | Rerun with `--runs 5`; more than 1/5 is a fail. |
| ERROR (inconclusive) | Errored runs could flip the verdict | Lower `--jobs`, raise `--timeout`, rerun. Never report it as a pass. |
| Fails at the default budget, passes with `--listing-budget 200000` | Listing space, not wording | Keep the wording; record the budget figure as a risk; shorten descriptions repo-wide if the total grew. |
| Different results on a second model | Model-sensitive wording, or a different listing budget | Check the `Listing:` line for both; prefer concrete situations over subtle phrasing; record both models in the PR. |
| Behavior arms split (one run passes, one fails) | The body leaves a decision open | Add a default or an explicit step where the runs diverged; read both transcripts to find it. |

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Checker: "was not in the session's skill list" | Frontmatter failed to parse; `name` differs from the directory; `SKILL.md` not at `skills/<name>/SKILL.md`; `--plugin-dir` one level too high or too low; wrong plugin name in `--skill`. | `claude plugin validate plugins/<plugin>/skills`; compare name and directory; point `--plugin-dir` at the plugin root; check the `plugins` list in the init event. |
| Loads, but never fires even on the most direct prompt | Its description was dropped from an over-budget listing. | Read the `Listing:` line; rerun with `--listing-budget 200000` before rewording. |
| `Error: When using --print, --output-format=stream-json requires --verbose` | Missing flag. | Add `--verbose`. |
| `Warning: no stdin data received in 3s` | Print mode waits briefly for piped input. | Append `< /dev/null`. |
| A run never finishes | No turn cap, or a tool waiting on something. | `--max-turns`, the checker's `--timeout`, `--max-budget-usd`. |
| Every prompt triggers, even unrelated ones | Running from the authoring checkout or session, or a greedy description. | Run from a scratch dir in a new process; then narrow the description. |
| Explicit `/<plugin>:<name>` does nothing | The plugin did not load, or the namespace is wrong. | Confirm the id in the init `skills` list; the prefix is the `name` in `plugin.json`. |
| `claude plugin eval`: "No eval cases found" | Cases not under `plugins/<plugin>/evals/`, or the `--case` glob matched nothing. | Check the directory and the case-name prefix. |
| `claude plugin eval`: no baseline column, or "no plugin resolved" | The case directory is not recognized as inside the plugin (for example, no `plugin.json`). | Add `plugins: ["../.."]` to the case's `prompt.md` frontmatter. |
| `claude plugin eval`: "is not a trusted plugin directory" | First run, and the command cannot ask. | Run once in a terminal and answer, or `--trust-plugin` for your own plugin in CI. |
| Results differ between contributors | Different CLI versions, models, personal skills, invocation history or listing budgets. | Record `claude --version`, the model, the init skill list and the `Listing:` line in the worksheet. |
