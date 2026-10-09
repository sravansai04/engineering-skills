# Writing a description that routes correctly

Read this while drafting the frontmatter (step 5 of SKILL.md) and again whenever a trigger test fails (step 6).

Contents:
1. What the router actually sees
2. The three-part shape
3. Good and bad pairs
4. Drawing the boundary with siblings
5. Symptom-to-fix table
6. Final checklist

---

## 1. What the router actually sees

At the start of every session the model gets a listing of the available skills: names and descriptions, nothing else. On each request it decides from that listing alone whether loading a skill would help. The body, the references and your careful procedure are invisible at that moment.

Consequences worth designing around:

- **The description competes.** It sits next to every other installed skill: this repo's siblings, built-in skills, and whatever the user wrote for themselves. Words vague enough to fit everything lose to words that fit this request exactly.
- **The listing has a budget, and a new skill is the first to lose.** Claude Code gives the whole listing about 1% of the model's context window. Recent CLIs logged roughly 8,000 characters on a 200K-context model and 30,000 on a 1M-context model. Names always stay. Once descriptions exceed the budget, Claude Code drops them starting with the skills the user invokes least, and a freshly installed skill has never been invoked. A dropped description leaves the model only the name to route on. When this was written, this marketplace's descriptions alone already exceeded the smaller budget, so:
  - Aim for about 450 characters (this marketplace's validator warns above 500; the portable hard limit is 1,024), with the capability in the first sentence. Short does not have to mean weaker: an earlier version of this skill's own description went from 859 to 495 characters and still fired in 16 of 16 runs (8 should-trigger prompts, 2 runs each, full listing, default model), the same as before, and fired on none of its 8 near misses. The first shorter draft did lose hits; the fix was restoring one missing situation (checking a proposed skill for overlap), not adding length back.
  - Put the phrasings that do not fit into `evals/trigger-evals.json`. There they are tested on every change instead of being paid for in every user's session.
  - Do not use `when_to_use` as overflow: it is appended to the description, shares the same 1,536-character entry cap and the same budget.
  - Check the repo-wide total before and after your change (`check_skill.py --listing .`).
  - To see the budget in a session, read `/context` (the Skills row is measured after the budget is applied) or `/doctor`, or look for `Skill listing over budget` in a `--debug` log. Users can raise it with the `skillListingBudgetFraction` setting or the `SLASH_COMMAND_TOOL_CHAR_BUDGET` environment variable, but a skill cannot assume they will.
- **Size test prompts to the job.** The model reaches for a skill when it expects the skill to change the result. A request it can finish in one move (rename a variable, define a term) is normally answered directly whatever the listing says, so a trigger test built from such prompts tells you nothing about your wording. Write test prompts at the scale of the work the skill exists for.
- **The name is the fallback.** When the description survives, a guessable verb-object name (`review-migration`) reinforces it; when it is dropped, the name is all that is left. A clever name (`gatekeeper`) helps in neither case.

## 2. The three-part shape

```
<CAPABILITY: one sentence, what it does + what it produces>.
Use for <TRIGGERS: the 3-5 strongest phrasings users type, quoted, or a situation>.
Not for <BOUNDARY: each nearby job> (<sibling>), <another nearby job> (<sibling>).
```

This marketplace's CONTRIBUTING.md asks for exactly that order, with bare sibling names inside the parentheses to save space (`pr-review`, not the full `plugin:skill` id used in the body).

| Part | Do | Avoid |
|---|---|---|
| Capability | A concrete verb and a concrete artifact: "Drafts an ADR in MADR format", "Finds the root cause of a failing test". | "Helps with", "assists in", "a comprehensive framework for". |
| Triggers | The phrasings users actually type ("review this PR", "why is this query slow"), or the situation they are in ("after CI fails on a PR", "before merging a schema change"). Include an indirect phrasing that never names the task. | A list of synonyms for the skill's own name. Quoting the test prompts. |
| Boundary | A short "Not for X (sibling)" list: each nearby job this skill does NOT do, and the sibling that owns it. | A long list of everything it does not do. Boundaries against things nobody would confuse. |

Optional fourth part, only if it still fits the ~450-character target: a few nouns users type when they ask for a sub-task by name ("lock timeouts, backfills, rollback scripts"). Never a list of the body's steps; that is a table of contents, not a trigger.

Tone: declarative, third person or imperative, no marketing adjectives, no capitals for emphasis. An absolute instruction to the router ("ALWAYS use this for ANY code change") reads as a greedy claim and makes collisions worse; describe the situation precisely instead.

## 3. Good and bad pairs

**Too vague**

> Bad: Helps with database stuff.

> Better: Reviews a database migration before it merges for lock risk, backfill cost, rollback path and deploy ordering, and returns a go/no-go with fixes. Use when a PR adds or edits migration files, when someone asks whether a schema change is safe to ship, or before running a migration against production. Not for writing ad-hoc queries (query-review).

Why: names the artifact (migration), the moment (before merge or prod), the user words (safe to ship) and the output (go/no-go).

**A summary of the body instead of a trigger**

> Bad: A rigorous seven-phase methodology combining hypothesis generation, bisection, instrumentation and regression testing, with templates and checklists.

> Better: Finds the root cause of a bug before any fix is written, by reproducing it, narrowing it down and proving the cause with a failing test. Use when something is broken and the reason is unknown, a test fails intermittently, or an earlier fix did not hold. Not for CI-only failures caused by the pipeline itself (ci-failure-triage).

Why: the router does not care how many phases there are. It cares whether this request is a "broken, cause unknown" request.

**Keyword soup**

> Bad: Git, GitHub, PR, pull request, merge request, review, diff, code, commit, branch, comments, feedback, approve.

> Better: Works through review comments on your open pull request: groups them, decides accept/push back/ask for each, makes the changes, and drafts replies. Use when a reviewer left comments you need to address or a PR is blocked on requested changes. Not for reviewing someone else's PR (pr-review).

Why: a bag of keywords matches every Git-adjacent request and steals traffic from three siblings. The better version is anchored on the user's role (the author, not the reviewer).

**Missing boundary**

> Bad: Writes clear, well-structured technical documents for engineering decisions.

> Better: Records an architecture decision as an ADR: context, options considered with trade-offs, decision and consequences, numbered into the repo's ADR folder. Use when a team has chosen between technical options and wants the reasoning written down, or asks for an ADR or design-decision record. Not for incident write-ups (incident-postmortem) or PR descriptions (pr-description).

Why: "technical documents" also describes postmortems and PR descriptions; without the boundary all three collide.

**Only fires when named**

> Bad: Use when the user runs /accessibility-review.

> Better: Audits a page or component for accessibility barriers (keyboard traps, missing labels, contrast, focus order, screen-reader names) and returns prioritized fixes mapped to WCAG criteria. Use when building or changing UI, before releasing a page, or when someone asks whether a screen works for keyboard or screen-reader users. Not for visual design direction (ui-design-direction).

Why: users rarely type the skill's name. They describe the work.

**Overreaching**

> Bad: Use this skill for ALL coding tasks to ensure the highest quality.

> Better: Simplifies recently changed code without changing behavior: removes duplication, dead branches and needless indirection, keeping tests green. Use after a feature works and before review, or when someone says code is hard to follow or over-engineered. Not for performance tuning or bug fixing.

Why: a skill that claims everything triggers on everything, and the user loses the specialized sibling that should have run.

## 4. Drawing the boundary with siblings

Pick the boundary from your should-NOT prompts: each near miss names a job and where it belongs. Write the one or two most likely confusions into the description; leave the rest to the body's "hand off instead" section.

Boundary dimensions that separate skills cleanly:

| Dimension | Example split |
|---|---|
| Role | author of the PR vs reviewer of the PR |
| Moment | planning vs executing vs verifying |
| Artifact | ADR vs postmortem vs PR description |
| Scope | one function vs a whole module vs a release |
| Trigger source | a human request vs a failing pipeline |

If your skill and a sibling still collide after the boundary is written, the sibling's description may be too broad. Fix it in the same PR and rerun the sibling's trigger cases too; a fix that helps your skill by breaking a sibling is a regression.

## 5. Symptom-to-fix table

Read the trigger checker's output per case. Change one thing per round and rerun the full set.

| Symptom | Likely cause | Fix |
|---|---|---|
| Should-trigger prompt: 0 hits, no other skill fired | The situation or user vocabulary is missing; the opening clause is abstract. | Add the situation in the user's words ("when CI is red"). Lead with the concrete capability. |
| Should-trigger prompt: 0 hits, a sibling fired | The sibling's description is a closer match for that phrasing. | Add the distinguishing situation to yours; add a boundary to the sibling if it is overreaching. Or accept it: maybe the sibling is right. |
| Should-trigger prompt fires only when the skill is named | Description describes the skill, not the request. | Rewrite triggers as situations, add an indirect phrasing. |
| Should-trigger prompt fires 1 of 3 | Borderline match. | Make the situation explicit; confirm with `--runs 5` before and after. |
| Should-NOT prompt fires | A broad word ("code", "review", "docs") matches it, or no boundary. | Narrow the broad word to the artifact or moment; add a boundary clause naming where it belongs. |
| Every prompt fires, including obvious negatives | Description is greedy, or tests ran inside the authoring context. | Rerun from a scratch dir; remove absolute claims; narrow the capability. |
| Tuning set passes, held-out fails | Overfitted to the tuning phrasings. | Replace phrase-level additions with the underlying situation; write new held-out prompts. |
| Loads, but never fires even on the most direct prompt | The listing was over budget and this description was dropped. | Read the checker's `Listing:` line and rerun with `--listing-budget 200000` before rewording; if it passes then, shorten descriptions rather than reword. |
| Results change between contributors | Different models (different listing budgets), personal skills or invocation history. | Record `claude --version`, the model, the init skill list and the `Listing:` line; test with the model most users run. |

## 6. Final checklist

- [ ] First clause states the capability and artifact.
- [ ] Three to five triggers in the words users type (quoted phrasings or situations), including one indirect phrasing; the rest live in `evals/trigger-evals.json`.
- [ ] A "Not for X (sibling)" list naming the sibling that owns each nearby request, with bare names.
- [ ] No test prompt copied into it (a short, generic phrasing such as "review this PR" is fine; a specific prompt from the cases file is not); no keyword lists; no capitals for emphasis.
- [ ] About 450 characters (the validator warns above 500; hard limit 1,024), capability in the first sentence.
- [ ] No XML-like tags or `<placeholder>` text in the description; the Claude API rejects them.
- [ ] The repo-wide listing total (`check_skill.py --listing .`) is known before and after the change, and noted in the PR.
- [ ] Still accurate after the body changed during testing.
