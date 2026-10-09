# Approaches and design sections

Read this in Step 4 (comparing approaches) and Step 5 (presenting the design
section by section): it covers how to generate options that really differ, how
to compare them honestly, and how to walk a user through a design without
burying them.

## Contents

1. Generating approaches that are actually different
2. The comparison table
3. Making the recommendation
4. When an unknown fact decides the approach
5. Worked examples across stacks
6. Presenting the design in sections

---

## 1. Generating approaches that are actually different

Three variations of the same idea ("Postgres table", "Postgres table with an
index", "Postgres table with a cache") are one approach. Real alternatives
differ on an **axis that the success criteria care about**. Pick the axis
first, then generate one option per pole:

| Axis | Poles |
|---|---|
| Build or not | Build new / extend an existing component / configure a tool you already run / buy or adopt / change a process, not software |
| When work happens | Synchronously in the request / asynchronously in a job / precomputed on a schedule |
| Where work happens | Client / server / database / an external service |
| Data shape | Compute on read / precompute on write / store events and derive |
| Generality | Narrow fix for this case / general mechanism others can reuse |
| Automation | Fully automated / automated with human review / manual first, automate later |

Two options are worth including whenever they are credible, because they are
the ones most often skipped and most often right:

- **The smallest thing that could meet the success criteria.** It anchors the
  cost of everything else.
- **Not building it** (reuse, configure, buy, or change a process). If this
  option wins, you just saved the team weeks.

Drop options that violate a hard constraint before presenting them, or show
them with the violated constraint named, so the user sees why they are out.

## 2. The comparison table

Use the same columns every time so options are comparable at a glance:

| Column | What to write |
|---|---|
| How it works | One line a non-expert could follow |
| Cost | S (days), M (a week or two), L (more), for this team, including tests and rollout |
| Main risk | The single thing most likely to make it fail or hurt |
| Reversible? | Yes (cheap to undo), Partly, No (data or public contract changes that are hard to undo) |
| Meets | Which SC/C ids it satisfies; flag any it misses |

Irreversible choices deserve more scrutiny than reversible ones; say so when
one option is a one-way door and the others are not.

## 3. Making the recommendation

State it in three sentences:

1. **Pick:** "I recommend B."
2. **Deciding reason, tied to ids:** "It is the only option that meets SC1
   without breaking C3."
3. **What would change your mind:** "If the 10x volume in SC2 is real within
   a year, A's precompute wins and I'd switch."

Then ask the user to choose. Do not proceed on your own recommendation unless
the user explicitly delegates ("your call"), and log that delegation in the
decision log. Salvage good ideas from losing options into "Notes for
planning" instead of discarding them.

## 4. When an unknown fact decides the approach

Sometimes the choice hinges on a technical fact that no document answers: can
the library stream a 2 GB file, can the mailer take a 1,000-message burst, does
the device keep a background task alive. The gate forbids prototypes before
approval, and an approved spec may not carry a blocking question, so name the
fact and use one of these two exits rather than guessing:

1. **Throwaway spike, with the user's explicit OK.** Agree a time box (an hour,
   not a day) and the exact question it answers. Work in a scratch directory
   outside the repository's working tree (for example one made with
   `mktemp -d`), commit nothing, and delete it afterwards. Record only the
   finding and its evidence (the command run, the measured number) in the
   ledger and the decision log. The code itself is never the starting point
   for the real implementation.
2. **Conditional decision.** Approve the spec with the branch written down:
   "Chosen: A, unless spike S1 shows the mailer drops messages above 500 per
   minute; then B." Make S1 the first item in Notes for planning and mark the
   question non-blocking, because the spec already says what happens either
   way. This only works when the success criteria, constraints and
   requirements hold under both branches; if they differ, the question is
   genuinely blocking and exit 1 is the way through.

If the fact only affects how something is built, not which approach wins, it
is not blocking at all: put it in Notes for planning as a spike.

## 5. Worked examples across stacks

Short sketches showing options that differ on a real axis.

**Public API rate limiting (backend service).** Axis: where work happens.
A. Configure limits in the API gateway already in front of the service (S,
reversible, but per-client rules may be impossible there). B. Middleware in
the service with counters in a shared store (M, precise per-client rules,
adds a hard dependency on that store). C. Per-instance in-memory limiter (S,
no new dependency, limits drift as instances scale out). Recommendation hinges
on whether per-client rules are a success criterion.

**Config format migration (CLI tool).** Axis: automation. A. Auto-migrate on
load and write a backup next to the file (S, invisible to users, surprising if
the file is version-controlled). B. Explicit `tool migrate` subcommand plus a
warning on old files (S, user stays in control, some never run it). C. Read
both formats indefinitely (M, no migration, permanent maintenance cost).

**Duplicate customer records (data pipeline).** Axis: automation. A. Exact
match on normalized email and phone, auto-merge (S, misses fuzzy duplicates).
B. Fuzzy matching with a human review queue for medium-confidence pairs (L,
catches more, needs reviewers). C. Adopt an existing entity-resolution
library or service (M, fast start, opaque merge decisions). Reversibility
matters most here: merges destroy information, so any option needs an undo.

**Offline notes (mobile app).** Axis: data shape. A. Read-only cache of
recent notes (S, solves "can't read in the field", not "can't write").
B. Queue edits offline, last write wins on sync (M, simple, silently loses a
concurrent edit). C. Full sync with conflict prompts (L, no data loss, more UI
and testing). Which one is right depends on whether two people edit the same
note, so that becomes the deciding question.

## 6. Presenting the design in sections

Present the chosen approach as a sequence of short sections, each validated
before moving on. Long design dumps get skimmed and approved without being
read; short sections get real answers.

**One message per section that holds a real decision.** Sections that only
restate defaults or the obvious consequence of earlier choices go together in
one message, with one targeted check naming the riskiest item among them.
Common pairings: observability with rollout; security with interfaces when
access rules do not change. At Feature size this usually means three to five
design messages, not eight. If the user starts answering "fine" without
reading, you are sending too many; combine more.

**Per-section rules**

- Keep each section to what fits on one screen (roughly 150-300 words).
- Lead with the decision, then the detail: "Duplicate clicks reuse the running
  job. Here is how..."
- Use a small diagram when a flow has more than three hops. Mermaid renders on
  most code hosts; ASCII works everywhere:

  ```text
  Admin --click--> App --enqueue--> Queue --> Worker --> Storage
                    |                            '-----> Mail --> Admin
                    '--"we'll email you"--> Admin
  ```

- End with a **targeted check**, not "looks good?". Name the riskiest choice
  in the section: "This reuses an in-flight job when filters match exactly.
  Is a near-match (same filters, different sort) a duplicate too?"
- Fold the answer back in, note any decision in the ledger, and only then
  move on. If the answer invalidates an earlier section, say so and revisit it.
- An answer to a section check approves that section's choice, not the spec.
  Approval of the whole spec happens once, in Step 8, on the written file.

**Which sections, by size**

| Section | Spark | Feature | Initiative |
|---|---|---|---|
| Overview | yes | yes | yes |
| Behavior and flows | combined with overview | yes | yes |
| Data (ownership, migration, retention) | if data changes | yes | yes |
| Interfaces (API, CLI, events, UI entry) | if any | yes | yes |
| Edge cases and failure behavior | short list | yes | yes |
| Security and privacy | if access or sensitive data is touched | yes | yes |
| Observability | rarely | yes | yes |
| Rollout and rollback | rarely | yes | yes |

For UI-heavy ideas, describe behavior and states here and leave visual
direction (layout, typography, palette) to `frontend:ui-design-direction`.
For an API whose shape is the main question, settle the behavior here and let
`data-api:api-design` work out the contract details. For a single hard
architectural choice that outlives this feature, record it with
`workflow:adr-writer` and link it from the spec. If one of these skills isn't
installed, note the follow-up in the spec's Notes for planning instead.
