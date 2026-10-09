# Spec template

Read this when you reach Step 6 (write the spec), or earlier if a long
dialogue needs a Draft file to resume from. Copy everything below the line into
the spec file, then replace every `[fill: ...]` marker. The
`scripts/spec_lint.py` checker fails on any marker you leave behind, so an
unfilled section can never slip through as "done".

Conventions the checker relies on (keep them even if you restyle the rest):

- **Sections are H2 headings** (`## ...`). The H1 is the title and never counts
  as a section.
- **Success criteria** carry ids `SC1`, `SC2`, ... in the Success criteria
  section. A criterion that can only be read after release (tickets, adoption,
  a production rate) is tagged `(outcome)` and states a baseline, a target, a
  `measured by` source and when it is read; the Observability subsection then
  says how that number is collected. An outcome criterion needs no requirement
  row if the measurement source already exists. Every other criterion must be
  served by at least one requirement.
- **Constraints** carry ids `C1`, `C2`, ... in the Constraints section.
- **Requirements** live in a table whose header includes `ID`, `Acceptance check`
  and `Serves`. Every row names the `SC`/`C` ids it exists for, individually
  (`SC1, SC3`) or as a range (`SC1-SC3`). A requirement that serves nothing is
  scope creep: cut it or name what it serves. The acceptance check is a
  given/when/then with a number or a yes/no result.
- **Open questions** live in a table whose header includes `Question`, `Owner`
  and `Blocks approval`. A spec cannot be `Approved` while a row says `yes`.
  Bullets work too, but then the checker can only guess at blocking status.
- `Status:` is one of `Draft`, `In review`, `Approved`. `Approved` requires a
  name and a date in `Approved by / on`, for every person listed in
  `Sign-off needed from`.
- Tables may be written with or without leading and trailing pipes.

Delete the `<!-- ... -->` guidance comments as you fill sections. Scale the
document to the effort; drop sections that cannot apply outright rather than
writing "N/A" padding.

**Spark layout** (also the fast-path mini-spec): sections 1, 3, 4, 6 (a
two-row table: the chosen option and one rejected), 8 and 10 (one `none` row is
fine), plus 2 and 5 only when they say something the others do not. Keep the
header block. A few lines per section.

---

```markdown
# [fill: feature name, as a user would say it]

- **Status:** Draft
- **Author(s):** [fill: names or handles]
- **Date:** [fill: YYYY-MM-DD]
- **Sign-off needed from:** [fill: everyone who must approve before build, e.g. "requester only" or "dana; ravi (database owner)"]
- **Approved by / on:** pending
- **Related:** [fill: issue links, prior specs, ADRs, or "none"]

## 1. Problem

<!-- One or two paragraphs. Who hurts today, how, and what evidence says so
(support tickets, metrics, a quote). No solution language here. -->

[fill: the problem in plain words]

## 2. Users and context

<!-- Who uses this, how often, in what situation, with what skill level.
Name the primary user first. Note anyone affected who never touches it
(operators, support, downstream systems). -->

- **Primary:** [fill: role and situation]
- **Also affected:** [fill: secondary roles or systems, or "none"]

## 3. Success criteria

<!-- Observable outcomes that tell you this worked, each with a threshold or
a yes/no check. Not features. "Export of 50k rows finishes in under 60 s",
not "export is fast". Tag a criterion (outcome) only when it cannot be checked
before release; give it a baseline, a source and a reading time, and mention
its id in 7.7 Observability. -->

- **SC1:** [fill: observable result with a threshold or a yes/no check]
- **SC2 (outcome):** [fill: baseline] -> [fill: target], measured by [fill: data source], read [fill: when, e.g. 30 days after full rollout]

## 4. Non-goals

<!-- Things a reasonable reader might expect that this deliberately does NOT
do, each with a one-line reason. This list is where YAGNI cuts land. -->

- [fill: excluded capability] (reason: [fill: why not now])

## 5. Constraints and assumptions

<!-- Hard limits (compatibility, regulation, budget, deadlines, platforms).
Assumptions carry provenance: (stated) the user said it, (inferred) you
deduced it from the repo or conversation, (default) you picked it and the
user accepted. -->

- **C1:** [fill: constraint]
- **Assumption:** [fill: assumption] (stated | inferred | default)

## 6. Approaches considered

| Approach | How it works | Cost | Main risk | Reversible? | Meets |
|---|---|---|---|---|---|
| A. [fill: name] | [fill: one line] | [fill: S/M/L] | [fill: risk] | [fill: yes/no/partly] | [fill: SC/C ids met; name any missed] |
| B. [fill: name] | [fill: one line] | [fill: S/M/L] | [fill: risk] | [fill: yes/no/partly] | [fill: SC/C ids met; name any missed] |

**Chosen:** [fill: letter and name], because [fill: the deciding reason, tied to SC/C ids].
**Rejected:** [fill: why each other option lost, one line each].

## 7. Design

<!-- Keep only the subsections this effort needs. Each should be checkable
against the success criteria. Prefer a small diagram (Mermaid or ASCII) over
a paragraph when describing a flow. -->

### 7.1 Overview
[fill: how the pieces fit, in a few sentences]

### 7.2 Behavior and flows
[fill: the main path, step by step, plus what the user sees]

### 7.3 Data
[fill: new or changed data, ownership, retention, migration or backfill]

### 7.4 Interfaces
[fill: APIs, CLI flags, events, files, or UI entry points, and who calls them]

### 7.5 Edge cases and failure behavior
[fill: empty, huge, concurrent, partial-failure, and retry behavior; what the user sees on error]

### 7.6 Security and privacy
[fill: who may see or do this; sensitive data touched; abuse cases]

### 7.7 Observability
[fill: how you will know it works in production (metrics, logs, alerts), and how each (outcome) SC id is collected]

### 7.8 Rollout and rollback
[fill: flag, phased release, migration order, and how to undo]

## 8. Requirements

<!-- One behavior per row, in plain present tense; strength goes in the
Priority column, not in "shall/should/may". Every behavior that sections 7 and
9 promise needs a row here, because planners and testers work from this table.
The acceptance check must be something a tester or an automated test can run
and get a yes/no answer from. -->

| ID | Requirement | Acceptance check | Serves | Priority |
|---|---|---|---|---|
| R1 | [fill: one observable behavior, present tense, e.g. "Starting an export returns within 2 s"] | [fill: given / when / then, with numbers] | [fill: SC or C ids] | Must |
| R2 | [fill: one observable behavior, present tense] | [fill: given / when / then, with numbers] | [fill: SC or C ids] | Should |

## 9. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| [fill: what could go wrong] | [fill: L/M/H] | [fill: L/M/H] | [fill: action or "accept"] |

## 10. Open questions

<!-- Anything unresolved. A "yes" in Blocks approval keeps Status below
Approved. Non-blocking questions travel to planning. -->

| ID | Question | Owner | Blocks approval |
|---|---|---|---|
| Q1 | [fill: question] | [fill: who answers] | [fill: yes/no] |

## 11. Decision log

<!-- Decisions made during the dialogue, so nobody re-litigates them. -->

| Decision | Chosen | Why | Decided by |
|---|---|---|---|
| [fill: topic] | [fill: option] | [fill: reason] | [fill: user / author default] |

## 12. Notes for planning

<!-- What the planner needs that is not a requirement: suggested slicing,
known-hard parts, files or modules likely touched, things to spike first. -->

[fill: hand-off notes]

## Working ledger (delete before In review)

<!-- Optional. Only for a Draft written early so a later session can resume.
Fold each row into sections 2-5 and the decision log, then delete this
section before setting Status: In review (the checker warns if it remains). -->

| Item | Value | Provenance |
|---|---|---|
| [fill: e.g. Users] | [fill: what was said or assumed] | [fill: stated / inferred: source / default] |
```
