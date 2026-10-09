---
name: brainstorm-spec
description: "Turns a rough idea into a spec the user approves before any plan or code, via one multiple-choice question at a time, scope cuts, and 2-3 compared approaches. Use for \"I'm thinking about adding...\", \"help me figure out what to build\", \"let's brainstorm this feature\", \"spec this out\", or an idea too vague to plan. Not for settled requirements (plan-feature), building a defined feature (build-feature), bugs (debug-root-cause), or recording one decision (adr-writer)."
argument-hint: "[rough idea, problem statement, or issue link]"
allowed-tools: Bash(git log:*), Bash(git ls-files:*), Bash(git grep:*), Bash(gh issue list:*), Bash(gh issue view:*), Bash(date +%F), Bash(python3 -I ${CLAUDE_SKILL_DIR}/scripts/spec_lint.py:*), Bash(python3 -I "${CLAUDE_SKILL_DIR}/scripts/spec_lint.py":*), Read, Grep, Glob
compatibility: The bundled spec linter needs Python 3.8 or later (standard library only).
---

# Brainstorm to Spec

An idea is cheap to change while it is still words. It gets expensive once it
is a plan and very expensive once it is code. This skill turns "I'm thinking
about..." into a spec file the user has read and approved, by way of a short
dialogue: one question at a time, options offered, scope cut hard, real
alternatives compared, and the design checked one piece at a time.

**The gate.** Until the user approves the written spec, produce no
implementation plan, no scaffolding, no code, no dependency installs and no
"quick prototype to explore". Reading the repo is encouraged; writing anything
other than the spec file is not. Once code exists, people defend it, and the
conversation shifts from "what should this be" to "how do we make this work".
Two exits are sanctioned: the fast path (under Special cases), when the user
explicitly wants to skip ahead, and a throwaway spike outside the repo, with
the user's OK, when an unknown technical fact decides the approach (step 4).

Idea to explore: $ARGUMENTS

If `$ARGUMENTS` is empty (as it is when this skill loads on its own), take the
idea from the conversation.

## Before you start: is the *what* still open?

Use this skill when the *what* is unsettled: the user has a problem, a hunch,
or a feature name, but not agreed success criteria and scope. Typical
openings: "I'm thinking about adding...", "help me figure out how we should
handle...", "what should we build for...", "we need something for X, not sure
what".

| Situation | Use instead |
|---|---|
| Requirements are known (even if not yet written down); the user wants steps or a technical design | `implementation:plan-feature` |
| A well-defined feature to build end to end | `implementation:build-feature` (it hands fuzzy problems to this skill, then resumes) |
| Something is broken or behaving wrongly | `implementation:debug-root-cause` |
| A single architectural choice among known options needs recording | `workflow:adr-writer` |
| The open question is the exact shape of an API contract | `data-api:api-design` |
| Visual direction for an interface | `frontend:ui-design-direction` |
| A brainstorm that is not about what to build (names, slogans, bug hypotheses) | Not this skill: answer directly, or use `implementation:debug-root-cause` for hypotheses about a fault |

If the first answers show the user already knows exactly what they want, say
so and offer the fast path straight into `implementation:plan-feature`.
Running a full dialogue on a settled idea wastes the user's time.

## Working principles

1. **One question per message, then stop and wait.** A list of five questions
   gets three half-answers, and the answer to the first usually changes the
   other four.
2. **Offer options.** Reacting to concrete choices is faster than composing an
   answer, and your options expose your assumptions so the user can correct
   them. Mark a recommended option and say why in a clause.
3. **Never ask what the repo can answer.** Check docs, code and history first.
   Each question should need the user's knowledge, judgment, or authority.
4. **Separate what was said from what you assumed.** Every fact in the ledger
   carries a provenance tag, so the spec cannot quietly turn a guess into a
   requirement.
5. **Cut scope ruthlessly.** A capability stays only if a success criterion or
   a hard constraint fails without it. Everything else becomes a named
   non-goal, which costs nothing to ship.
6. **Scale the ceremony.** A small idea gets a few questions and a half-page
   spec; a large one gets the full treatment and may be split.
7. **Invent nothing silently.** Anything you add that the user did not say
   (an edge case, a number, a requirement) is labeled and confirmed.

## Workflow

### 0. Sweep the project context before the first question

Spend a few minutes learning what already exists. The aim is better questions
and an honest size call, not a full code map; deep exploration belongs to
planning.

```bash
git log --oneline -n 20                                  # what has been changing lately
git log --oneline --since="90 days ago" -- path/to/area  # recent work where the idea lands
git ls-files '*.md' | grep -iE 'spec|rfc|design|adr|proposal' | head -40   # existing design docs
git grep -n -i "export" -- '*.md'                        # prior discussion of the idea's key term
gh issue list --search "export" --state all --limit 20   # related issues, if the project uses GitHub and gh
```

Then read: the README; CONTRIBUTING or any documented proposal/RFC process;
one or two existing specs (to copy their location, naming and template); the
code entry points the idea touches (enough to know what exists, not how every
line works); and any linked issue or ticket.

If the folder is empty or not a repository, say "greenfield, nothing to sweep"
and move on. If an existing spec or open issue already covers the idea, ask
whether to revise or extend it before starting a new one.

### 1. Size the effort

Pick a size from what the sweep showed, using these signals:

| Size | Signals | Questions | Approaches | Spec |
|---|---|---|---|---|
| Spark | One behavior, one place, easy to undo | 1-3 | 2, briefly | The Spark layout in the template, a few lines per section |
| Feature | Several components, a real design choice, existing data or users affected | 4-8 | 2-3 with table | Full template, skipping sections that cannot apply |
| Initiative | Several independently shippable parts, multiple teams or systems, weeks of work | 8-15, possibly over several sessions | 3 per major decision | Split it: one spec per slice |

Report the sweep and the size together in at most eight lines, before asking
anything. The size goes last so the user can override it:

```text
Context: orders service (Python/FastAPI), exports built synchronously in
orders/export.py; specs live in docs/specs/ as YYYY-MM-DD-topic.md; issue
#482 reports export timeouts; no prior spec on this. Unknown: who exports
and how large exports get.
Size: Feature, because it changes how existing exports behave. Override?
```

For an Initiative, decompose before going deep. Agree with the user on the
parts, pick the first slice that delivers value on its own, and spec only
that. The other slices go into Non-goals as "later slices", each with one line
on what it covers. One spec trying to describe five subsystems gets approved
without being read.

### 2. Build shared understanding, one question at a time

Ask about the dimensions in this order, because each constrains the next:
**purpose** (the problem, without a solution in it), **users** (including who
else must sign off before it is built), **success criteria** (observable, with
numbers or yes/no), **scope edges and non-goals**, **constraints** (hard limits
with a source), **behavior at the edges** (empty, huge, concurrent, failing),
and **rollout**. Skip whatever step 0 or an earlier answer already settled.

Shape every question like this, then end your turn:

```text
You mentioned admins re-click when exports hang, so duplicates matter.
What should happen when someone starts an export identical to one already running?
  A. Reuse the running one and tell them so  (recommended: removes the duplicate load)
  B. Queue a second copy
  C. Refuse with a message
  D. Something else, or "your call"
```

With a structured choice tool such as `AskUserQuestion`, the escape option and
the recommendation are expressed differently; follow the tool-mode rules in
`references/question-bank.md` section 1.

Keep a **ledger** and show it after every three or four answers, and always
before step 3:

```text
Ledger (Feature)
Problem      Large exports time out; admins re-click, doubling DB load   [stated]
Users        Account admins, ~1,200, monthly, desktop                   [stated]
Sign-off     dana; ravi (DB on-call lead)                               [stated]
SC1          500k-row export completes with the tab closed              [stated]
SC2          Zero duplicate export queries at month start               [default]
Non-goals    Scheduled exports [stated]; new file formats [default]
C1           Links unguessable, same account only   [inferred: docs/security.md]
Open         Page on-call on failures? (non-blocking, owner: dana)
```

Provenance tags: `stated` (the user said it), `inferred` (you deduced it; cite
the source), `default` (you proposed it and the user accepted or delegated).

A dimension is done when it is answered, defaulted, or parked as an open
question with an owner. Stop asking when every dimension is done; more
questions past that point are stalling. If you blow well past the size budget,
the idea is bigger than you sized it: re-size and tell the user.

If the dialogue may span sessions (typical for an Initiative), write the spec
file early with `Status: Draft` and keep the ledger in its optional "Working
ledger" section, with the decision log and open questions in their own
sections. The next session resumes from the file, provenance tags included,
instead of from anyone's memory.

For per-dimension question ideas, exit conditions, and how to follow up on
answers like "it should be fast" or "for everyone", read
`references/question-bank.md`.

### 3. Cut scope with a YAGNI pass

Before designing anything, list every capability that has come up, including
ones you were about to propose. For each, ask: *which SC or C fails if this is
missing?* If none does, it moves to Non-goals with a reason ("revisit when
...").

Present the cut list in one message and ask the user to confirm it, with
options like "accept all cuts" or "restore one of them (which?)". Riders are
the most common reason small features run long: each one adds design, tests,
and maintenance forever, and none of them was the point.

### 4. Compare 2-3 approaches and let the user choose

Generate options that differ on an axis the success criteria care about
(build vs reuse vs buy, sync vs async, compute on read vs precompute, narrow
fix vs general mechanism), not three flavors of one idea. Include the smallest
thing that could meet the success criteria and, when credible, the option of
not building software at all.

Show a comparison table (how it works, cost, main risk, reversibility, which
SC/C ids it meets), then recommend in three sentences: the pick, the deciding
reason tied to ids, and what would change your mind. Then **let the user
choose** and end your turn; do not start the design in the same message.
Proceed on your own recommendation only if the user explicitly delegates, and
log that. Salvage good ideas from losing options into the spec's planning
notes.

If the choice hinges on a technical fact no document answers ("can the mailer
take a 1,000-message burst?"), do not guess and do not prototype in the repo.
Either run a time-boxed throwaway spike in a scratch directory outside the
working tree, with the user's explicit OK, keeping only the finding; or record
a conditional decision ("A, unless spike S1 shows X, then B") that holds under
both branches. Both are spelled out in `references/approaches-and-design.md`
section 4, along with axes, table conventions and worked examples.

### 5. Present the design in sections

Walk through the chosen approach in short sections (overview, behavior and
flows, data, interfaces, edge cases and failure behavior, security and
privacy, observability, rollout and rollback), only those the size calls for.
Give each section that holds a real decision its own message, lead with the
decision, and end with a **targeted check** on its riskiest choice, never a
bare "looks good?". Combine sections that only restate defaults into one
message. Fold each answer back in and log it before moving on.

```text
Design 2 of 4: behavior and flows
Decision: Export queues a job and returns at once; the admin is emailed a
link when the file is ready, and the Downloads page lists it.
1. Admin clicks Export -> "We'll email you" plus a link to Downloads.
2. A worker streams rows to a file, then emails a signed link.
3. An identical export already queued or running is reused, not repeated.
Check: "identical" means same account and same filters. Should a different
sort order still count as identical?
  A. Yes, same rows  (recommended: sort does not change the content)
  B. No, treat it as a new export
```

An "ok" to a section check settles that section only; the spec is approved
once, in step 8. Section length, diagrams, which sections each size needs, and
how to combine sections are in `references/approaches-and-design.md`
section 6.

### 6. Write the spec

**Location.** Follow the convention step 0 found (directory, naming, front
matter, template). If there is none, use `docs/specs/YYYY-MM-DD-<topic>.md`,
with today's date from `date +%F` and a two-to-five-word kebab-case topic. If
the repo has its own spec or RFC template, use it and map this skill's sections
into it, keeping the SC/C/R ids so traceability survives.

**Content.** Start from `references/spec-template.md` and fill it from the
ledger and the validated sections, not from memory of the conversation. Write
requirement text in plain present tense; put strength in the Priority column.
Every requirement gets a given/when/then acceptance check and the SC/C ids it
serves, and every behavior the design promises gets a requirement. A success
criterion that can only be read after release is tagged `(outcome)` with a
baseline and a measurement source. If a Working ledger section exists, fold
its rows into sections 2-5 and delete it. Set `Status: In review`.

`references/example-spec.md` shows a finished Feature-size spec if you want a
calibration point.

Do not commit unless the user asks. If they do, follow the repo's commit
conventions (`workflow:commit-message` covers that).

### 7. Self-review before asking for approval

Run the bundled linter on the file (standard library only, Python 3.8+):

```bash
python3 -I "${CLAUDE_SKILL_DIR}/scripts/spec_lint.py" docs/specs/2026-03-14-export-notify.md
```

Claude Code substitutes `${CLAUDE_SKILL_DIR}` with this skill's directory in
this file only; in other hosts, use the absolute path to the directory that
holds this SKILL.md. Exit 0 means no errors, 1 means errors (or warnings under
`--strict`), 2 means the file could not be read. What each check means, and
the flags, are in `references/self-review.md`.

Then do the reading passes the linter cannot: traceability in every direction
(problem to SC to R to acceptance check, and design back to R), contradictions,
ambiguity, gaps, and fidelity to the dialogue. The same reference has the
checklist and before/after rewrites of untestable requirements.

Fix what you can. Then report the review in a few lines: linter result, what
you fixed, what you added that needs confirmation, and what needs the user's
call.

### 8. Get explicit approval and hand off

Give the user the file path and ask them to read it and either approve it or
request changes. Approval must be explicit and about the spec ("approved",
"LGTM", "ship the spec"); "ok" in reply to some other question is not
approval. On changes, edit, re-run the linter, and ask again.

**Other approvers.** If `Sign-off needed from` names anyone besides the user,
the user's approval is not enough. Record it in `Approved by / on`, keep
`Status: In review`, add a blocking open question per missing approver
("Sign-off from ravi", owner ravi), and offer to open a pull request or issue
for their review. Never record an approval on someone's behalf.

When every required approver has approved, set `Status: Approved` with each
name and date, then run the linter once more (a blocking open question or a
missing approver is now an error). Hand off with the settled parts named, so
the next skill builds on them instead of reopening them:

```text
Spec docs/specs/2026-03-14-export-notify.md is Approved.
Closed: the chosen approach (section 6) and the decision log (section 11).
Confirm them against the code; reopen one only if the code contradicts it,
and say which.
Keep the R/SC/C ids: map every plan slice or acceptance criterion to the R ids
it delivers. Non-blocking questions to settle during planning: Q1.
Planning notes: section 12 (slices, spikes, salvaged ideas).
```

- **Called from `implementation:build-feature`:** return the path and that
  message. The spec already contains a chosen design, so its Design phase
  should confirm the approach fits the code rather than generate new options.
- **Otherwise:** offer `implementation:plan-feature` with the same message.

Stop there. Planning and code belong to the next skill.

## Special cases

### Fast path: the user wants to skip ahead

When the user says "just build it", is under time pressure, or turns out to
know exactly what they want, do not drag them through the full dialogue.
Write a mini-spec in the template's **Spark layout** (problem; one to three
success criteria with numbers; non-goals; a two-row approaches table with the
chosen option and one rejected; the requirements table with acceptance checks
and Serves; open questions, where a single `none` row is fine), with every
assumption tagged `default`. Save it in the same location, lint it, then show
it and ask for one confirmation, listing what was skipped (for example "no
edge-case discussion; no rollout plan"). On confirmation, set
`Status: Approved` with the approver and date, lint again, and hand off as in
step 8. If the user declines any spec at all, that is their call: stop using
this skill, state the assumptions you would have checked, and hand off.

### No human in the loop

When nobody can answer (you are a subagent, a headless or scheduled run, or the
caller says no one is available), the dialogue cannot happen and approval
cannot be given. Do not stall and do not approve your own work:

1. Do the step 0 sweep and size the effort as usual.
2. Write the spec with every answer the repo could not supply tagged `default`,
   and every logged decision marked "author default".
3. Record each unknown that would change the design (the problem framing,
   users, a success threshold, the approach choice) as a blocking open question
   owned by the requester.
4. Run the linter. Leave `Status: Draft` (or `In review` if no blocking
   questions remain) and `Approved by / on: pending`.
5. Return the path, the blocking questions, and the defaults to the caller,
   stating that the spec is not approved and must not be treated as approved.

Only a person's explicit words set `Approved`.

## Report format

After approval, end with this report:

```text
Spec: docs/specs/2026-03-14-export-notify.md  (Status: Approved by dana, ravi)
Size: Feature | Questions asked: 7 | Approaches compared: 3 (chosen: A, background job + email link)
Success criteria: SC1 500k rows with tab closed; SC2 zero duplicate queries (outcome); SC3 <5 tickets/quarter (outcome)
Non-goals: scheduled exports; new formats; non-admin roles; in-app notification center
Self-review: linter clean; 2 fixes; 1 addition confirmed (R2 dedupe)
Unconfirmed: defaults still standing, or "none"; outcome SCs (SC2, SC3) can only be checked after release
Open (non-blocking): Q1 page on-call on failure? (owner: dana)
Next: implementation:plan-feature with this spec as input.
```

Question and ledger formats are shown in step 2; the design-section format in
step 5; the hand-off message in step 8; the self-review report in
`references/self-review.md` section 8.

## Common mistakes

- **Batching questions.** Several questions in one message, or asking a
  question and answering it yourself in the same turn.
- **Asking what the repo knows.** "What language is this in?" after skipping
  the sweep.
- **Weak options.** Overlapping choices, a single "option" that is really a
  leading question, or qualities ("fast/medium/slow") instead of behaviors
  and numbers.
- **Accepting vague success criteria.** "It should be fast" is a starting
  point; follow up until there is a number and a load.
- **Designing the user's first solution.** They said "dashboard"; you
  designed a dashboard before learning what decision it should support.
- **Fake alternatives.** Three variants of one approach, or omitting the
  smallest option and the do-not-build option.
- **Deciding for the user.** Moving on with your recommendation when they
  never chose it.
- **The design dump.** The whole design in one message, ending "thoughts?".
- **Writing from memory.** Requirements in the spec that never came up,
  without being flagged.
- **Design prose with no requirement.** A retry policy, a limit or an email
  described in the design but missing from the requirements table, where
  planners and testers will never see it.
- **TBD instead of a question.** Unknowns belong in Open questions with an
  owner and a blocking flag, not scattered as TBD.
- **Treating silence as approval,** treating approval of a section as
  approval of the whole spec, or filling in "Approved by" yourself.
- **Exploratory code in the repo before the gate.** Even a throwaway
  prototype anchors the design. If an unknown fact decides the approach, use
  the scratch-directory spike or the conditional decision from step 4.
- **Wrong size.** A twelve-section spec for a one-line behavior, or one spec
  for five subsystems.

## Related skills

- `implementation:plan-feature`: the default next step once the spec is
  approved; it turns the R/SC/C ids into slices. Also the right skill when the
  requirements are already settled.
- `implementation:build-feature`: when it called this skill, return the
  approved spec to it and let it resume.
- `workflow:adr-writer`: record a hard architectural choice that outlives the
  feature, and link it from the spec.
- `data-api:api-design`: the exact contract once this skill has settled the
  behavior. `frontend:ui-design-direction`: visual direction for UI-heavy ideas.
- `implementation:debug-root-cause`: when the "idea" turns out to be a fault
  to explain.
- `workflow:commit-message`: if the user asks you to commit the spec.

If a skill named here isn't installed, give the short version inline and list the deeper pass as a follow-up.

## Reference files

- `references/question-bank.md`: read in step 2 when choosing the next
  question, phrasing options (including with a structured choice tool),
  following up on vague answers, or judging the question budget.
- `references/approaches-and-design.md`: read in steps 4 and 5 for generating
  real alternatives, the comparison table, unknown facts that decide the
  approach, and presenting and combining design sections.
- `references/spec-template.md`: read in step 6 and on the fast path for the
  template, the Spark layout, and the id conventions the linter relies on.
- `references/example-spec.md`: read in step 6, once, to calibrate the level
  of detail of a finished spec.
- `references/self-review.md`: read in step 7 for what the linter checks, the
  reading passes, untestable-to-testable rewrites, and the review report
  format.
- `scripts/spec_lint.py`: the spec linter (Python 3.8+, standard library
  only). Run it in step 7, on the fast path, and after approval:
  `python3 -I "${CLAUDE_SKILL_DIR}/scripts/spec_lint.py" <spec.md> [--strict] [--no-sections] [--vague-everywhere]`.
  `--help` prints usage; `--selftest` runs its fixture cases, including a
  check that `references/example-spec.md` lints clean. Run `--selftest` after
  changing the linter.
