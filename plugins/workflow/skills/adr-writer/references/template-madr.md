# Template: Full ADR (MADR-based)

This is the default for decisions with two or more serious options or several stakeholders. The structure follows MADR (Markdown Architectural Decision Records, version 4), with explicit follow-ups and revisit triggers added. If the repository has its own template, that template wins. Use this one only to work out what content belongs in each of its sections.

How to use it:

- Copy the block below, replace each `{...}` placeholder, and delete the guidance comments.
- If an optional section would be empty, delete it. Don't write "N/A".
- Match the repo's metadata style. MADR 2 and log4brains files put metadata in a bullet list under the title (`* Status:` in MADR 2, `- Status:` in log4brains) with a `Deciders` field and an optional `Technical Story` line. MADR 3 moved metadata into YAML front matter with a `deciders:` key. MADR 4 keeps the front matter, renames the key to `decision-makers:`, and quotes the status value. The block below is MADR 4; for a MADR 3 repo, rename `decision-makers` back to `deciders`. The bullet header for MADR 2 and log4brains repos follows the template.
- Keep the whole record to one or two printed pages. Link to benchmarks, diagrams, and threads rather than pasting them in.

````markdown
---
status: "proposed"          # proposed | accepted | rejected | deprecated | superseded by ADR-NNNN
date: {YYYY-MM-DD}          # MADR: when the record was last updated; follow the repo if it keeps the decision date
decision-makers: {names or roles accountable for the decision}
consulted: {subject-matter experts whose input was sought}      # optional
informed: {teams or people who need to know the outcome}        # optional
---

# {NNNN}. {Decision as a short imperative phrase, e.g. "Use PostgreSQL for the billing ledger"}

<!-- Optional one-sentence summary (Y-statement). Delete if it does not fit:
In the context of {component or use case}, facing {concern}, we decided for {option}
and against {other options}, to achieve {benefit}, accepting {cost}. -->

## Context and Problem Statement

{Two to five sentences, or a short story, describing the problem. No solution yet.
Cover: what is happening, why it matters now, the hard constraints (scale, budget,
deadline, compliance, team skills), and the scope this decision covers. Use numbers
with units and say where and when they were measured. Ending on a question often
sharpens it: "How should services publish events without losing them when the broker
is unavailable?"}

## Decision Drivers

<!-- Most important first. Make each one testable. Mark knock-out criteria. -->
* {Driver 1, e.g. "No lost events across broker restarts (must-have)"}
* {Driver 2, e.g. "Added p99 latency on the write path under 10 ms"}
* {Driver 3, e.g. "Operable by the current team without a new on-call rotation"}

## Considered Options

* {Option A: the status quo, if it is a plausible choice}
* {Option B}
* {Option C}

## Decision Outcome

Chosen option: "{Option B}", because {justification tied to named drivers, e.g. "it is
the only option that meets the no-lost-events must-have without adding new
infrastructure, and it fits the 10 ms latency budget (measured 3 ms p99 in staging on
{date})"}.

{Scope: what this applies to and, explicitly, what it does not decide.}

### Consequences

* Good, because {positive outcome, e.g. "a crash between write and publish can no longer drop an event"}
* Bad, because {cost accepted, e.g. "a relay process to deploy, monitor and scale"}
* Bad, because {another cost, e.g. "consumers must now tolerate duplicate deliveries"}
* Neutral, because {a change that is neither, e.g. "event ordering stays per-aggregate, as today"}

### Follow-ups

* [ ] {Action}: {owner or issue link}
* [ ] {Action}: {owner or issue link}

### Revisit When

* {Condition that would reopen this decision, e.g. "sustained event volume exceeds 20k/s"}
* {Assumption whose failure invalidates it, e.g. "the database stops being the single system of record"}

### Confirmation

{How compliance is checked: an architecture or dependency test, a lint rule, a review
checklist item, a dashboard or alert. Remove the section if nothing applies.}

## Pros and Cons of the Options

<!-- Steelman every option: describe it as its strongest advocate would.
Use the same drivers for each. Use "Neutral" for points that cut neither way. -->

### {Option A}

{One or two sentences describing it, or a link.}

* Good, because {real strength}
* Bad, because {weakness, tied to a driver}

### {Option B}

{Description.}

* Good, because {...}
* Neutral, because {...}
* Bad, because {...}

### {Option C}

{Description.}

* Good, because {...}
* Bad, because {...}

<!-- Optional when there are three or more options: a comparison matrix. Keep cells
short. Prefer measured values to symbols where you have them. -->

| Driver | Option A | Option B | Option C |
|---|---|---|---|
| {Driver 1 (must-have)} | {fails: reason} | {meets} | {meets} |
| {Driver 2} | {value} | {value} | {value} |
| {Driver 3} | {...} | {...} | {...} |

## More Information

* Supersedes: {[ADR-NNNN](NNNN-old-title.md), or delete}
* Related: {[ADR-NNNN](NNNN-title.md): how it relates}
* Evidence: {benchmark report, cost model, spike branch, dated}
* Discussion: {issue or PR link, design doc}
* Assumptions: {stated explicitly, so a future reader knows what to re-test}
````

## Alternative header: MADR 2 / log4brains bullet metadata

Use this header in repos whose existing ADRs have bullet metadata and no YAML front matter. Match the existing bullet marker (`*` in MADR 2, `-` in log4brains) and drop the `Technical Story` line if the existing files don't have one. log4brains files are date-prefixed, so they carry no number in the title.

```markdown
# {NNNN}. {Decision as a short imperative phrase}

* Status: proposed
* Deciders: {names or roles}
* Date: {YYYY-MM-DD}

Technical Story: {issue or ticket link}
```

## Status line formats for later changes

Apply these edits to an accepted ADR and leave the body alone. Keep the original decision date visible, as SKILL.md step 8 ("Dates") describes.

```markdown
status: "superseded by ADR-0019"      # MADR 4 front matter: quoted, identifier only, no link
status: superseded by [ADR-0019](0019-adopt-transactional-outbox.md)   # MADR 3 front matter allows a link
* Status: superseded by [ADR-0019](0019-adopt-transactional-outbox.md)  # MADR 2 bullet ("-" in log4brains)
status: "deprecated"                  # nothing replaces it; add a one-line reason under the title
```

In MADR 4, where the status carries no link, put the clickable link in a pointer line under the title: `Superseded by [ADR-0019](0019-adopt-transactional-outbox.md).`
