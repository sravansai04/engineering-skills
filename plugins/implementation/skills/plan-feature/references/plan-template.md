# Implementation Plan Template

Copy the skeleton below into the plan file or the conversation, then fill it in. Guidance for each section follows the skeleton.

- **Lite plans** (small to medium, reversible changes) use only the sections tagged `[lite]`. A tag such as `[lite: ...]` names the part of that section a lite plan keeps.
- **Full plans** use every section. Write "n/a" with a one-line reason rather than deleting a section, so reviewers can see it was considered.
- Keep each section as short as the change allows. Tables beat paragraphs for anything enumerable.

---

## Skeleton

```markdown
# Plan: [short imperative title, e.g. "Add soft delete and 30-day restore for projects"]

| Field | Value |
|---|---|
| Status | Draft / In review / Approved / In progress / Done |
| Size | Lite / Full |
| Author | [name] |
| Date | [YYYY-MM-DD] |
| Ticket / spec | [link or "none"] |
| Reviewers | [names or teams whose sign-off is needed] |

## 1. Summary [lite]
[2 to 4 sentences: what will change, for whom, and the chosen approach in one line.]

## 2. Problem and goals [lite]
[Who has what problem today, why it matters now, and what "better" looks like.]

## 3. Acceptance criteria [lite]
- AC-1: [observable, testable statement] (delivers: [spec R ids, when planning from a spec])
- AC-2: [include at least one negative criterion: what must NOT happen]

## 4. Non-goals [lite]
- [explicitly out of scope, and where it would go if anywhere]

## 5. Assumptions and open questions [lite]
| ID | Assumption or question | Recommended default | Impact if wrong | Owner | Status |
|---|---|---|---|---|---|
| Q-1 | | | | | open / answered / assumed |

## 6. Context and prior art
| What exists | Where (path:line) | How this plan uses it |
|---|---|---|
| | | reuse / extend / follow convention / deliberately not used (why) |

Conventions to follow: [error handling, validation, logging, naming, test layout]
Related decisions: [ADRs, past plans, notable commits]

## 7. Proposed design [lite: 7.1 and a short 7.4 only]
### 7.1 Components affected
| Component | Change (new / modified / removed) | Owner |
|---|---|---|

### 7.2 Data model changes
[Tables/collections, fields, types, nullability, defaults, constraints, indexes,
lifecycle and retention, backfill needs.]

### 7.3 Contract changes
| Contract | Change | Consumers | Compatibility strategy |
|---|---|---|---|

### 7.4 Key flows
[Numbered steps or a small sequence diagram for the main path and the main failure path.]

### 7.5 Alternatives considered
| Option | Pros | Cons | Why not chosen |
|---|---|---|---|

## 8. Edge cases and failure modes
| Case | Expected behavior | Covered by |
|---|---|---|
| | | AC-n / slice n test |

## 9. Concurrency
[Races, duplicate delivery, ordering; the mechanism that makes each safe.]

## 10. Security and privacy [lite: one line naming each new entry point and its authorization, or "none"]
- Entry points and their authorization checks (including object-level):
- Input validation and output encoding:
- Sensitive data: classification, where it flows, logs, retention, deletion:
- Needs dedicated security review: yes / no (why)

## 11. Scale and performance
| Dimension | Today | 10x | 100x | Breaks first | Mitigation | Now / later |
|---|---|---|---|---|---|---|
Source of "today" numbers: [measured from X on DATE / assumed]

## 12. Rollout and rollback [lite: feature flag and one-way doors lines only]
- Feature flag: [name, type, default, who flips it, stages, removal slice]
- Migration phases: [expand / migrate / contract mapped to slices]
- Deploy order: [what must be live before what]
- Backward compatibility: [old clients, queued messages, cached or stored data; for consumers you do not deploy, the deprecation notice and the usage telemetry that gates removal]
- One-way doors and safeguards:
- Rollback rehearsal: [both flag states covered by tests; flag-off or revert exercised in staging before production]
- Health signals and turn-off threshold:

## 13. Risks and spikes [lite]
| ID | Risk or unknown | Likelihood | Impact | Mitigation or spike (time box, question, decision it drives) |
|---|---|---|---|---|

## 14. Delivery slices [lite]
### Slice 0: [spike or first increment name]
- Goal:
- Changes: [files or components; mark new ones]
- Depends on: [slice ids or "none"]; can run in parallel with: [ids]
- Verification: [tests to add + exact command + any manual or production check]
- Rollback:
- Covers: [AC ids]
- Steps (commit-sized, ids numbered across the whole plan):
  - T1: [step] (check: `[command or observation that proves it]`)
  - T2: ...

## 15. Verification matrix
| AC | Slice | Test or check |
|---|---|---|

## 16. Change log
| Date | Change | Reason |
|---|---|---|
```

---

## Section guidance

**1. Summary.** Written last, read first. A reviewer should be able to approve or push back on direction from this paragraph alone.

**2. Problem and goals.** Describe the problem, not the solution. If the request arrived as a solution, record the underlying need here; it lets reviewers spot a better approach.

**3. Acceptance criteria.** When the plan starts from a spec written with `implementation:brainstorm-spec`, keep the spec's R, SC and C ids and give each AC the R ids it delivers, so a reviewer can trace every requirement to a test. Each criterion should be checkable by a test or a concrete manual step. Avoid "fast", "secure", "user-friendly"; prefer "p95 under 300 ms for accounts with 1M orders on the staging dataset", "returns 404 for a project in another workspace". Negative criteria catch authorization and data-leak gaps early.

**4. Non-goals.** Name the tempting adjacent work that is out of scope. This is the section that ends scope debates in review.

**5. Assumptions and open questions.** Questions are only those where the answer changes the design and cannot be found in the repository. Everything else is an assumption with a default. Keep the status column current as answers arrive; an approved plan should have no open questions that block slice 1.

**6. Context and prior art.** Evidence that the codebase was read. Cite paths with line numbers. Include things deliberately not reused and why (for example, "the existing exporter loads everything into memory; we stream instead"), because a reviewer will otherwise ask.

**7. Proposed design.** Enough detail that two engineers would build roughly the same thing, and no more. Pseudocode only where an algorithm is genuinely subtle. For contract changes, the consumer column comes from searching the code, not from memory.

**8. Edge cases and failure modes.** Every row should point at an AC or a slice test. Rows with no coverage are either accepted risks (say so) or missing work.

**9. Concurrency.** Name the mechanism, not just the worry: unique constraint, conditional update (compare-and-set on a version column), row lock, idempotency key, single-consumer queue partition, or "not needed because X".

**10. Security and privacy.** List every new or changed entry point (endpoint, job, webhook, CLI, message handler) with its authentication and authorization. Even a lite plan keeps this line, because a new entry point that skips its authorization check is one of the most common defects in small changes. If personal or regulated data is involved, state where it is stored, who can read it, how long it is kept, and how it is deleted.

**11. Scale and performance.** State where today's numbers came from, and measure them cheaply (aggregate queries or existing metrics, never a load test against a serving system). "Assumed" is acceptable when marked; silent guesses are not. The "now / later" column is the actual decision.

**12. Rollout and rollback.** Map migration phases and flag stages to specific slices. Every one-way door needs a safeguard or an explicit, named sign-off. Removing something external consumers use waits for evidence (usage of the old shape at zero or below an agreed threshold), not for a date. A rollback that has never been exercised is a hope, so say when and where it was rehearsed.

**13. Risks and spikes.** A spike entry has a question, a time box, and the decision its answer drives. If the answer would not change anything, it is not worth spiking.

**14. Delivery slices.** Each slice: one purpose, main branch stays deployable, own verification with a real command, own rollback. Number from 0 so spikes can be slice 0. Under each slice, list its commit-sized steps with stable ids (T1, T2, ... numbered across the whole plan, never renumbered once the plan is approved), each ending in a check command. `implementation:execute-plan` uses these ids in its ledger and as `Plan-Task` commit trailers, so every commit traces back to a step. A lite plan may give a step only its id, its one-line goal and its check.

**15. Verification matrix.** Derived from 3 and 14. Any AC without a row is a gap to fix before approval.

**16. Change log.** Plans change as spikes land and slices teach things. Record what changed and why, so reviewers who approved an earlier version can see the delta.
