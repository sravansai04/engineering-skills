# Clarifying questions and design options

Read this when drafting the Phase 3 questions or the Phase 4 comparison.

## Contents

1. What makes a clarifying question worth asking
2. Question bank by category
3. Handling the answers
4. Generating real design options
5. The comparison template
6. One-way and two-way doors

---

## 1. What makes a question worth asking

A question earns its place when all three hold:

- **The code cannot answer it.** If an explorer could have found it, go find
  it.
- **The answer changes what you build.** If every plausible answer leads to the
  same code, decide it yourself and log the decision.
- **A wrong guess is expensive.** Contract, data, security, and user-facing
  behavior questions qualify; internal naming does not.

Shape each question so the user can answer it in seconds:

| Weak | Strong |
|------|--------|
| "How should errors be handled?" | "If the export hits a row the user may not see, should we (a) skip it silently, (b) skip it and add a count to the footer, or (c) fail the export? I'd pick (b): the user learns the file is partial without being blocked." |
| "Any performance requirements?" | "The largest customer account has ~2M orders. Should export of the full set work this release (needs a background job, about two extra days), or is a 50k-row cap with a clear message acceptable for v1? I'd cap it." |
| "What about permissions?" | "List visibility today is gated by `orders.view`. Should export use the same permission, or a separate `orders.export` so admins can grant viewing without bulk download? Separate is safer for data-loss reviews." |

The pattern: the concrete situation, the options, your recommendation, and a
one-line reason. "Defaults are fine" becomes a complete answer.

## 2. Question bank by category

Scan these for gaps; ask only the ones that pass section 1.

**Scope**
- Which users, roles, or callers get this? Anyone explicitly excluded?
- Is there an existing workaround this replaces, and must it keep working?
- What is explicitly not part of this release?

**Inputs and edge cases**
- Empty: no data, no selection, a first-time user.
- Huge: the largest realistic input, and is a limit acceptable?
- Malformed or hostile input: who can send it, and what happens?
- Concurrent: two users or two retries acting at once.
- Time: time zones, daylight-saving boundaries, effective dates, clock skew.
- Internationalization: locales, currencies, right-to-left text, long strings.

**Failure behavior**
- What does the user see when a dependency is down or slow?
- Retry automatically, ask the user, or fail?
- Partial success: all-or-nothing, or best effort with a report?

**Access and data**
- Who may see the output, and does it expose anything the source screen hides?
- Is any of the data personal, regulated, or secret?
- Must actions be auditable, and by whom?

**Compatibility**
- Existing clients, stored data, or integrations that depend on current
  behavior?
- Does old data need migrating, or can it be read in place?
- Version skew during deploy: old and new code running side by side?

**Operations and rollout**
- Behind a feature flag? Default on or off?
- What should be logged or measured to know it works in production?
- Any deadline or release train that constrains the design?

## 3. Handling the answers

- **Direct answer:** fold it into the brief and adjust the acceptance criteria.
- **"Defaults are fine":** apply every proposed default; list them once in the
  brief so the user sees what they accepted.
- **"You decide":** state the specific choice and the reason in one sentence,
  log it, and continue. Do not re-ask.
- **An answer that opens a new question:** ask the follow-up only if it passes
  section 1; otherwise decide and log.
- **An answer that conflicts with the code:** show the conflicting `file:line`
  and ask which wins. Do not silently pick one.
- **No answer, or a prompt that timed out:** you have no approval. Keep
  waiting, or, if the user asked you to proceed unattended, follow the
  unattended rules in `sizing-and-modes.md`.
- **Nothing left to ask:** at size M, do not stop just to say so. Carry the
  brief and draft acceptance criteria into the G3 design message so the user
  confirms both at once.

## 4. Generating real design options

Look for the axes along which this problem genuinely forks. Common ones:

| Axis | Example fork |
|------|-------------|
| Where the logic lives | In the existing service, in a new module, at the edge (client, gateway) |
| When work happens | Inline in the request, deferred to a background job, precomputed |
| Data shape | New column on an existing table, a new table, derived on read |
| Abstraction | Extend the existing abstraction, add a sibling, generalize both |
| Build versus reuse | Hand-written, an existing internal utility, a new dependency |
| Contract | Additive change, new versioned endpoint, change in place behind a flag |

Pick the one or two axes where the choice matters for this feature and build
the options from them. A good set usually includes the smallest change that
satisfies the criteria and at least one option that buys something real
(scale, safety, reuse) at a stated cost.

For L features, you can dispatch one subagent per option (all in one
message), each told to sketch that option against the real code. These run
before the user has approved anything, so they must not touch the repo:

- Use a read-only agent type (in Claude Code, the built-in `Explore` or
  `Plan` subagent). If only a general-purpose agent is available, open the
  prompt with the no-write clause from the explorer preamble in
  `explorer-briefs.md` section 2.
- Ask for the sketch back as text: files to touch, new types and signatures,
  the test strategy, the hardest part, and optionally a pseudo-diff. Never as
  files written to the repo; a "sketch" left in the working tree becomes
  debris and anchors the decision.

Compare the sketches yourself; do not let an agent pick the winner.

## 5. The comparison template

```markdown
### Option A: <name> (recommended)
<Two-line sketch naming files and seams from the codebase map.>

### Option B: <name>
<Sketch.>

### Option C: <name> (only if genuinely different)
<Sketch.>

| | A | B | C |
|---|---|---|---|
| Follows existing pattern | yes, mirrors `<file>` | partly | no, new abstraction |
| Change surface | ~4 files | ~9 files + migration | ~12 files |
| Meets criteria | all | all | all + future X |
| Main risk | <...> | <...> | <...> |
| Reversible | easily | needs data rollback | easily |
| Testability | unit + 1 integration | needs job-runner fixture | <...> |
| Runtime impact | <...> | <...> | <...> |

**Recommendation:** A, because <reason tied to the brief>.
**Choose differently if:** <condition that would flip it>.
**Decision needed:** reply with A, B, or C, or with changes.
```

Keep cells concrete. "Better maintainability" is not a trade-off; "one place to
change when a new format is added, at the cost of an extra interface" is.

## 6. One-way and two-way doors

Ask of each decision: if this proves wrong in three months, what does undoing
it cost?

- **Two-way door** (cheap to reverse: internal structure, private names, an
  algorithm behind a stable interface): decide quickly and log it.
- **One-way door** (expensive to reverse: public contract, persisted data
  shape, an external dependency others will build on, a security model):
  slow down. Put it explicitly in the design checkpoint, record it with
  `workflow:adr-writer`, and prefer the option that keeps the door open (additive
  fields, versioned endpoints, data you can backfill) unless the user chooses
  otherwise.
