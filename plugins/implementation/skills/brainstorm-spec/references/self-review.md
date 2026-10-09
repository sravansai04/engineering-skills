# Spec self-review

Read this in Step 7, after the spec file exists and before you ask the user to
approve it. The goal is that the user's review is spent on judgment calls, not
on catching typos, missing sections, or untestable sentences you could have
caught yourself.

## Contents

1. Pass 0: the linter
2. Pass 1: traceability
3. Pass 2: contradictions
4. Pass 3: ambiguity
5. Pass 4: gaps
6. Pass 5: scope and fidelity
7. Rewriting untestable requirements (examples)
8. Reporting the review

---

## 1. Pass 0: the linter

Run the linter with the command shown in SKILL.md Step 7. Its script path is
already resolved there; this file is read verbatim, so a path variable copied
from here would not be filled in. In a host that does not resolve it, use the
absolute path to this skill's `scripts/spec_lint.py`. Pass the spec's path
relative to where you run the command.

What it checks:

| Level | Check |
|---|---|
| error | `[fill: ...]` markers, TBD, TODO, FIXME, `???` left in the text |
| error | A missing core section: Problem, Success criteria, Non-goals, Requirements, Open questions (skipped with `--no-sections`) |
| error | A requirement with no acceptance check, serving no SC/C id, citing an undefined id, or a duplicate id |
| error | An SC that no requirement serves, unless it is tagged `(outcome)` with a `measured by` clause and its id appears under the Observability heading |
| error | `Status: Approved` with a blocking open question, with `Approved by / on` blank or `pending`, or without a person listed in `Sign-off needed from` |
| warn | An acceptance check with no given/when/then and no number (e.g. "works") |
| warn | Open questions written as bullets or prose: blocking status is guessed from the wording, so confirm it yourself |
| warn | Vague words ("fast", "scalable", "etc.", "handles") in Success criteria, Constraints and Requirements |
| warn | Fewer than two approaches recorded; an empty Non-goals section; no `Status:`; a Working ledger left in a spec that is In review or Approved |

Fix every `error`. Read every `warn` and either fix it or decide it is
acceptable. Append `<!-- spec-lint: ignore -->` to a line only when the flagged
wording is genuinely precise in context, such as "fast" inside a product name.
Flags: `--no-sections` when the repo has its own spec template with different
headings; `--vague-everywhere` to sweep prose outside the binding sections;
`--strict` to fail on warnings, which suits a CI check.

The linter catches mechanical defects only. A spec can pass it and still
describe the wrong product, or promise behavior in its design that no
requirement carries. The passes below are where judgment lives.

## 2. Pass 1: traceability

Walk the chain in every direction:

- **Problem to success criteria.** Would meeting every SC actually make the
  problem in section 1 go away? If the problem says "duplicates slow the
  database" and no SC mentions duplicates or load, something is missing.
- **Success criteria to requirements.** For each SC, which requirements
  deliver it? (The linter checks that some requirement cites it; you check
  that the cited requirements are enough. "Receive a 500k-row file" needs a
  requirement that proves a 500k-row job completes, not just one that proves
  the job starts.) For an `(outcome)` SC, check the baseline is real, the
  source exists today, and 7.7 says who reads it and when. If measuring it
  needs new instrumentation, that instrumentation is a requirement row.
- **Requirements to acceptance checks.** Could a stranger run each check and
  get an unambiguous yes or no? If the check needs the author to interpret
  it, rewrite it (section 7).
- **Requirements back to purpose.** A requirement that only cites an SC on a
  technicality ("R7 serves SC1 because everything does") is scope creep in
  disguise. Cut it or move it to Non-goals. The same goes for an SC cited only
  to quiet the linter: if it is really a lagging outcome, tag it `(outcome)`
  and measure it instead.
- **Design to requirements.** Read sections 7 and 9 sentence by sentence. Every
  behavior a user, operator or other system can observe (a retry policy, a
  limit, an email, an error page, a mitigation that changes what the system
  does) maps to an R row. If it has none, add one, or move the behavior to
  Non-goals or Notes for planning. Planners and testers work from the
  requirements table, so anything promised only in prose gets dropped.

## 3. Pass 2: contradictions

Contradictions hide between sections, so compare sections pairwise:

- **Non-goals vs everything else.** For each non-goal, search the rest of the
  spec for its key noun. "No in-app notifications" plus a design section that
  shows a toast is a contradiction.
- **Constraints vs the chosen approach.** Re-read each `C` id against section
  6. An approach that "mostly" meets a hard constraint does not meet it.
- **Numbers stated twice.** Search for every number. "7 days" in constraints
  and "30 days" in the retention requirement cannot both be right.
- **One thing, two names.** "Job", "task", and "export" used for the same
  object read as three objects to an implementer. Pick one term and use it
  everywhere; add a short glossary if the domain needs one.
- **Decision log vs body.** Every logged decision should be visible in the
  design or requirements, and nothing in the body should contradict a logged
  decision.

## 4. Pass 3: ambiguity

The linter flags vague words in the binding sections. Look for the patterns
it cannot see:

| Pattern | Example | Ask |
|---|---|---|
| Passive voice hiding the actor | "The admin is notified" | Notified by what, through which channel, when? |
| Unbounded quantifiers | "All records are migrated" | Including deleted, archived, and test records? |
| Undefined terms and acronyms | "Eligible accounts" | Eligible by what rule? Define it once. |
| Pronouns with two candidates | "When the job retries the worker, it logs" | Which one logs? |
| Modal-verb soup | "should", "may", "must" mixed in requirement text | Put strength in the Priority column; write requirement text in plain present tense |
| Conditionals with no else | "If the file is large, stream it" | How large, and what happens otherwise? |
| Time without a clock | "Expires after a week" | 7 x 24 h from creation, or end of the 7th calendar day, in which time zone? |

## 5. Pass 4: gaps

Check each area. Mark it covered, deliberately out of scope (then it belongs in
Non-goals), or missing (then fix it or raise an open question). Skip areas that
cannot apply.

- **Inputs:** empty, maximum size, malformed, duplicate, concurrent.
- **Failure:** partial failure, retries, idempotency, what the user sees.
- **Access:** who can see, do, and undo this; what happens at the boundary.
- **Existing data and clients:** migration, backfill, backward compatibility.
- **Lifecycle:** retention, deletion, archival, export of the new data.
- **Operations:** how you know it works in production, who gets paged, cost.
- **Rollout:** flag or pilot, order of steps, rollback path.
- **People:** accessibility and localization for UI work; support and docs
  for anything users will ask about.

## 6. Pass 5: scope and fidelity

- **Proportion.** Is the spec's length proportional to the effort size? A
  Spark with a twelve-section spec is padding; an Initiative with half a page
  is a wish.
- **YAGNI, once more.** Now that everything is written down, is there a
  requirement nobody would miss in the first version? Move it to Non-goals
  with "revisit when ..." as the reason.
- **Fidelity to the dialogue.** Everything in the spec should trace to
  something the user said, something you inferred and labeled, or a default
  the user accepted. If you added anything new while writing (an edge case,
  a requirement, a number), list it in your review report so the user can
  accept or reject it. Silent additions are the main way a spec drifts from
  what the user agreed to.
- **Open questions.** Each has an owner. Each blocking question is genuinely
  blocking (the design changes depending on the answer); everything else is
  marked non-blocking and travels to planning. A question settled by a
  conditional decision ("A, unless spike S1 shows X, then B") is non-blocking
  only if the spec says what happens in both cases.
- **Sign-off.** Everyone in `Sign-off needed from` either approved or has a
  blocking open question in their name.

## 7. Rewriting untestable requirements (examples)

| Untestable | Testable |
|---|---|
| The page loads fast. | Given a list of 1,000 items on a mid-range laptop over a 10 Mbps link, the page shows its first 50 rows within 1.5 s (p95). |
| The import handles errors gracefully. | Given a file where row 40 is malformed, the import saves rows 1-39 and 41-N, reports row 40 with its error, and returns a non-zero exit code. |
| Search is intuitive. | In a test with 5 first-time users, at least 4 find a known order by customer name in under 30 s without help. |
| The system is scalable. | At 500 requests/s sustained for 10 minutes, error rate stays below 0.1% and p99 latency below 800 ms. |
| Users can easily undo mistakes. | After any bulk edit, an Undo action is shown for 10 s and restores every changed field. |
| Data is kept secure. | A user of account A requesting any resource of account B receives 404, verified by an automated test per endpoint. |
| Notifications are sent in real time. | The notification is delivered within 5 s of the triggering event for 99% of events. |
| Supports large files. | Files up to 2 GB upload successfully; files over 2 GB are rejected before upload with the limit shown. |

Pattern: name the **situation** (given), the **action** (when), and an
**observable result with a number or a yes/no** (then).

## 8. Reporting the review

Tell the user what you checked and changed, briefly, before asking for
approval:

```text
Self-review of docs/specs/2026-03-14-export-notify.md
- Linter: 0 errors, 1 warning kept ("fast" is part of a product name).
- Fixed: R3's check had no time bound (added "within 60 s"); retention said
  7 days in C2 and 30 days in R5 (now 7 everywhere).
- Added while writing, please confirm: R2 (dedupe identical exports). It came
  from the duplicate-click problem but we never discussed it explicitly.
- Needs your call: Q1 (page the on-call on failures?), non-blocking.
```
