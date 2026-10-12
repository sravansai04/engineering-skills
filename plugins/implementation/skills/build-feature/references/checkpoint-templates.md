# Checkpoint and status message templates

Read this when writing any message that asks the user for a decision or
reports progress. Each template ends where your turn should end. Keep the
phase tag on the first line so the user always knows where the run stands.

Principles behind every template:

- Put the decision being asked for at the top and again at the bottom. Users
  skim; the ask must not be buried in the middle.
- Attach a recommendation to every choice so "yes" is a complete reply.
- Show evidence as `file:line`, not adjectives.
- One message per checkpoint. Do not split questions across turns. Use a
  structured-question tool if your agent has one (AskUserQuestion in Claude
  Code), otherwise a plain-text message in chat. AskUserQuestion holds at
  most four questions (two to four options each, recommended option first,
  "Other" added for you) and is unavailable inside subagents. With more than
  four, use one numbered plain-text message, or put the four with the largest
  blast radius in the tool and state defaults for the rest in the brief so
  "defaults are fine" covers them.

---

## G1: Early scope check (only when the request is too unclear to explore)

```markdown
[build-feature · Phase 1/8 Discover · size ?]

Before I dig into the code I need one thing settled, because it decides where
I look: <the question>.

My reading: <best interpretation, one or two sentences>.
If that's right, reply "yes" and I'll start exploring. If not, tell me what
the feature should do for the user.
```

## G2: Brief, codebase map, and questions (the usual first checkpoint)

```markdown
[build-feature · Phase 3/8 Clarify · size M]

**Decision needed:** answers to <n> questions below (or "defaults are fine").

**Goal:** <one sentence>
**Acceptance criteria (draft):**
- AC1 Given ..., when ..., then ...
- AC2 ...
**Out of scope:** <bullets>

**What the code tells us**
- Closest analog: <feature> (`path/to/file:line`); I'll mirror it.
- Plugs in at: `path:line`, `path:line`
- Tests: <style>; single test runs with `<cmd>`
- Constraint worth knowing: <...> (`path:line`)

**Questions** (most consequential first)
1. <situation + options>. *Default: <choice>, because <reason>.*
2. ...

Reply with answers or "defaults are fine". I won't design anything until then.
```

## G3: Design approval (with the plan folded in for M)

If Phase 3 had no questions left, put the G2 brief and draft acceptance
criteria at the top of this message instead of stopping twice.

```markdown
[build-feature · Phase 4/8 Design · size M]

**Decision needed:** pick an option (A recommended), approve the plan, and
choose how to deliver it.

<Comparison from clarify-and-design.md, section 5>

**Plan for A** (recommended; if you pick another option I'll re-plan before
building). Each step ends green and becomes one commit.
Slice 1: <name>
  1. Walking skeleton: <thin end-to-end path>. Check: `<cmd>` passes.
  2. <step> (AC1). Check: <...>
Slice 2: <name>
  3. ...
Questions from planning: <each with a default, or "none">

**Delivery** (only when there is more than one slice): one combined PR, or
one PR per slice (sequential or stacked)? *Recommended: <shape>, because
<size or risk reason>.*

Reply "A, go", choose another option, or adjust the plan.
```

## G4: Plan approval (L features, or when the plan changed after G3)

```markdown
[build-feature · Phase 5/8 Plan · size L]

**Decision needed:** approve the plan below or adjust it.

Plan file: <path, if persisted>
Slices: <n> (steps per slice: <a>, <b>, ...); riskiest step is #<k> (<why>),
scheduled early on purpose.
Coverage: AC1 -> steps 2, 5; AC2 -> step 3; AC3 -> step 6.
Questions plan-feature raised: <list, each with a default, or "none">

<Plan or its summary>

**Delivery:** one combined PR, or one PR per slice (sequential or stacked)?
*Recommended: <shape>, because <reason>.*

Reply "approved" (plus a delivery choice) to start implementation on branch
`<name>`.
```

## Dirty working tree (Phase 6 set-up)

```markdown
[build-feature · Phase 6/8 Implement · set-up · paused]

**Decision needed:** what to do with uncommitted changes I didn't make.

`git status --short` shows:
<the listed paths>

I won't stash, reset, or commit them on my own. Options:
1. You commit or stash them yourself, then tell me to continue.
2. I stash them as "build-feature: pre-existing changes" (they stay in
   `git stash list` until you restore them).
3. I leave them where they are and build in a separate worktree.
   *Recommended: nothing of yours moves.*
```

## Deviation stop (contract-level surprise in Phase 6, or a review fix in Phase 7 that would change agreed behavior)

For a review fix, change the tag to `Phase 7/8 Review · paused` and say who
raised the finding in "What I found".

```markdown
[build-feature · Phase 6/8 Implement · step 3 of 7 · paused]

**Decision needed:** how to handle a conflict with the approved design.

What we agreed: <one line>.
What I found: <one line>, see `path:line`.
Why it matters: <consequence if ignored>.

Options:
1. <adjustment>. Cost: <...>. *Recommended, because <reason>.*
2. <alternative>. Cost: <...>.

Committed so far: steps 1-2 (green). Nothing from step 3 is committed.
```

## Re-size notice (a tripwire fired)

```markdown
[build-feature · Phase <n>/8 · size M -> L]

I found <tripwire, with file:line>. That makes this an L change, which adds
<the phases or reviews it adds>. <If it changes an agreed contract: "I've
paused until you confirm." Otherwise: "Continuing; flagging it so it's not a
surprise in review.">
```

## Status pulse (long Phase 6 runs, not a gate)

```markdown
[build-feature · Phase 6/8 Implement · 4 of 7 steps done]
Done: <steps>, all green, <n> commits. Next: <step>. No blockers.
```

## G5: Final report

Fill every section; write "none" rather than dropping one. End with a single
explicit question about the next outward step, for example: "Push
`feat/orders-export` and open a PR with a generated description?" With one PR
per slice, send one G5 per slice. Once the PR is open, red CI goes to
`workflow:ci-failure-triage` and reviewer comments to
`workflow:respond-to-review`.

```markdown
## Built: <feature name>

**Outcome:** <one or two sentences, user-visible>

### Assumptions and open questions
- <decision made without the user's input, and why>  (or "none")
- <blocking question still unanswered>

### Acceptance criteria
| AC | Evidence (test name, command and result, or manual check) | Status |
|----|-----------------------------------------------------------|--------|
| AC1 ... | `orders_export_test::filters_rows`, passing | verified |
| AC2 ... | manual: 10k-row export finished in 3.1 s locally | verified |
| AC3 ... | no automated check, see follow-ups | unverified |

### Decisions
- <decision>: <why>; rejected <alternative> because <reason>

### Changes
- <area>: <files>, <what and why>

### Verification run (this session)
- Base: `<default branch>@<sha>`
- `<command>`: <result>

### Review
- Self-review: fixed <n>
- Independent review (<fresh subagent: skill used | self-review only, why>):
  fixed <n>, disputed <n, one line each>, deferred <n, linked below>

### Delivery
- <slice>: branch `<name>`, <n> commits, <combined PR | own PR>, <status>
- Done inline because a sibling skill was missing: <steps, or "none">

### Follow-ups and risks
- <item>, <why it matters>

### Next step
<e.g. "Push the branch and open a PR?" Await the user's answer.>
```

