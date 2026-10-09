# Evaluation worksheet

Open this at step 2 of SKILL.md and fill it as you go. Keep your copy in the task's scratch directory (`<scratch>/worksheet.md`), out of the commit; section H is what goes into the PR. Write each section before running the step that uses it, so the criteria cannot drift toward whatever the runs happened to produce.

Contents:
- A. Header
- B. Intent card
- C. Overlap check
- D. Test prompts (with guidance on writing them)
- E. Trigger rounds
- F. Behavior grading
- G. Decision log
- H. PR evidence block

---

## A. Header

| Field | Value |
|---|---|
| Skill | `<plugin>:<name>` |
| Mode | contribute / rework / standalone |
| CLI version | output of `claude --version` |
| Model(s) tested | e.g. the default, plus any `--model` used |
| Listing state | the checker's `Listing:` line (within budget, or N skills, C chars > B) |
| Repo files present | validator, CONTRIBUTING.md, PR template, plugin.json version (note any missing) |
| Budget agreed with the user | e.g. "$5 for trigger rounds, $15 for behavior runs" |
| Date | |

## B. Intent card

| Field | Value |
|---|---|
| Problem (failure without the skill) | |
| Moment (when a user reaches for it) | |
| Output (artifact and shape) | |
| Side effects and their confirmation points | |

Success criteria (graded in section F, and committed as each case's `expectations` in `evals/evals.json`; each must be observable in a transcript or a file):

| # | Criterion | How to check |
|---|---|---|
| S1 | | |
| S2 | | |
| S3 | | |

## C. Overlap check

| Item | Value |
|---|---|
| Nearest existing skills | |
| What fired today for the should-trigger prompts | paste the checker table from step 3 |
| Decision | extend `<skill>` / new skill with boundary / reference file in `<skill>` / do not build |
| Why | |
| Sibling descriptions edited in this PR | |

## D. Test prompts

Each prompt should read like something a contributor would actually type in the middle of their work, not like a test. Two contrasts show the difference:

- **Realism.** "Help me with a skill" tests little: it is so thin that the model may answer it without consulting any skill. "Our on-call runbook for rotating TLS certs is a 40-line doc nobody follows; can we turn it into something Claude runs step by step when a cert is about to expire?" carries a real situation, a real artifact and an indirect phrasing that never says "skill".
- **Near misses.** A negative is only useful if it could plausibly fool the router. For a migration-review skill, "convert this CSV export to JSON" shares nothing and so proves nothing; "add a migration that drops the legacy_status column from orders" shares the vocabulary but asks for authoring rather than review, which is exactly the line the description has to hold.

Vary the set on purpose: terse and long, with and without file paths, one with shorthand or a typo, one that describes the problem without naming the task. Give every near miss the place it should go instead: a sibling id or `none`.

| ID | Set | Expect | Prompt | Should route to |
|---|---|---|---|---|
| t1 | tuning | trigger | | |
| t2 | tuning | trigger | | |
| t3 | tuning | trigger | | |
| n1 | tuning | no-trigger | | `<sibling>` or none |
| n2 | tuning | no-trigger | | |
| n3 | tuning | no-trigger | | |
| h1 | held-out | trigger | | |
| h2 | held-out | no-trigger | | |

Cases file for the checker (tuning and held-out in separate files, so the held-out set runs only once at the end):

```json
[
  {"query": "...", "should_trigger": true},
  {"query": "...", "should_trigger": false, "should_route_to": "workflow:pr-description"},
  {"query": "...", "should_trigger": false, "should_route_to": "none (a quick factual answer)"}
]
```

This is the same shape as the committed `evals/trigger-evals.json`, so the tuning file can be committed as-is at the end. The checker also accepts `{"id", "prompt", "expect": "trigger" | "no-trigger"}` if you prefer stable ids while tuning.

## E. Trigger rounds

One row per round. Change one thing per round; rerun every tuning case.

| Round | Description change | Should-trigger passed | Should-NOT passed | Regressions | Notes |
|---|---|---|---|---|---|
| 1 | initial draft | x/y | x/y | - | |
| 2 | | | | | |

Held-out (run once, after tuning passes): x/y passed. If it failed, record what you generalized and the new held-out prompts.

Listing over budget? ___ If yes, failing cases rerun with `--listing-budget 200000`: x/y passed.

Sibling comparisons (`--compare` against the step 3 snapshots): regressions ___

Final description character count: ___ (aim for about 450; the validator warns above 500; limit 1024). Repo listing total before / after: ___ / ___

## F. Behavior grading

Runner: `claude plugin eval` (case directories under `plugins/<plugin>/evals/<name>-*`) or manual arms (testing guide section 5, with the contamination caveat).

Fixture: what it contains and how it reproduces the problem.

Grade every run against every criterion. Evidence is a short quote, a file path, or a command result, never "looked fine". If you can, grade blind (section F.1).

| Prompt | Arm | Run | S1 | S2 | S3 | Turns | Cost | Evidence / notes |
|---|---|---|---|---|---|---|---|---|
| p1 | explicit | 1 | | | | | | |
| p1 | explicit | 2 | | | | | | |
| p1 | natural | 1 | | | | | | |
| p1 | baseline | 1 | | | | | | |
| p1 | baseline | 2 | | | | | | |

With `claude plugin eval`, the arms are "with" (natural prompt, plugin loaded) and "without" (baseline); an explicit `/<plugin>:<name>` case, if you add one, runs with `--ablation none`. Copy each grader verdict into the table and keep the `--json` file.

Summary per arm:

| Arm | Criteria met (all runs) | Beat baseline on | Lost to baseline on |
|---|---|---|---|
| explicit | | | |
| natural / with | | | |

Cost: trigger rounds $___, behavior runs $___, total $___ (from the checker's `Cost:` line and the eval report or `total_cost_usd`).

### F.1 Blind grading (recommended when the call is close)

1. Copy each pair of outputs (skill arm, baseline arm) into `A.md` and `B.md`, assigning the arm to A or B by coin flip; record the key somewhere you will not look.
2. Grade A and B against the criteria, and note which you would rather receive and why.
3. Unblind. If you preferred the baseline, or could not tell them apart, the skill is not yet earning its context cost.

## G. Decision log

Each change to the body or description, with the observation that caused it. This is what a future maintainer needs when a later edit regresses something.

| # | Change | Triggered by (case / run / criterion) | Result after rerun |
|---|---|---|---|
| 1 | | | |

## H. PR evidence block

Paste into the PR template's testing or verification section.

```markdown
### Evaluation

Model: <model>  CLI: <claude --version>  Runs per prompt: <R>  Cost: <total>

**Triggering** (final round, all repo plugins loaded, fresh sessions, user-like working directory)

Listing: <within budget | over budget: N skills, C chars > B; failing cases with full listing: x/y>

| Case | Expect | Hits | Verdict | Route | Other skills that fired |
|---|---|---|---|---|---|

Held-out: <x>/<y> passed. Rounds of tuning: <n>. Sibling regressions: <none | list>.

**Behavior** (<runs> runs per arm via <`claude plugin eval` | manual arms>; criteria written before the first run)

| Criterion | With skill | Baseline | Evidence |
|---|---|---|---|

Skill fired in <x>/<y> with-plugin runs (`tool_used: Skill` indicator, isolated listing).

**Checks**
- Repo validator: <pass | errors | absent>
- `check_skill.py`: <pass>; listing total <before> -> <after> chars
- `claude plugin validate plugins/<plugin>/skills --strict`: <pass>
- SKILL.md lines: <n>; description chars: <n>
- Version: <old> -> <new> (<minor/patch/major> because <reason>) | plugin.json has no version

**Known limits**
- <flaky cases, untested stacks, sibling collisions left as-is and why, listing-budget risk>
```
