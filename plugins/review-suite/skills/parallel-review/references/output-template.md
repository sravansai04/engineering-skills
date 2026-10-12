# Output template (the final prioritized result)

Fill this in for step 9. Put it in the chat by default. Only write it to a file if the user asks for one (for example, `parallel-review-YYYY-MM-DD.md`). Leave out any section that would be empty, except Coverage, which always appears.

````markdown
## Parallel review: [target, e.g. "branch feature/refunds vs main" or "module src/billing/"]

**Revisions:** base `[BASE_SHA short]` → head `[HEAD_SHA short]` · **Scope:** [N] files, +[A]/-[D] lines (or "[N] files, ~[L] lines" for a module)
**Personas run:** [correctness, security, ...] · **Verifiers run:** [n] · **Lanes failed:** [none / list]

### Verdict

**[Block | Fix before merge | Merge with follow-ups | Merge]**: [one sentence explaining why, naming the top finding if there is one].

| Severity | Confirmed | Likely |
|---|---|---|
| critical | [n] | [n] |
| high | [n] | [n] |
| medium | [n] | [n] |
| low | [n] | [n] |

### Findings

#### 1. [critical] [title] - `path:line` (Confirmed | Likely)
- **Scenario:** [concrete input or state → wrong outcome]
- **Evidence:** [citations; for a Confirmed finding, add the verifier's decisive fact]
- **Fix:** [smallest change]
- **Verify:** [the regression test to add]
- **Also at:** [`path:line`, `path:line`, if any]
- **Raised by:** [persona(s)]
- **Open question** (Likely only): [what a human should check]

#### 2. [high] ...

[...every critical and high finding, then medium findings up to about 15...]

#### Low-severity items
- `path:line`: [title] ([persona])
- ...

### Pre-existing (not introduced by this change)
- [high] [title] - `path:line`: [one line on why it still matters]. Not counted in the verdict.

### Hardening (no failure or exploit path today)
- `path:line`: [what is weak, and why it matters later] ([persona])

### Refuted during verification
- ~~[title]~~ (`path:line`, [persona]): refuted. [One line naming the guard or fact that prevents it, with a citation.]

### Coverage and gaps
- **Personas not run:** [persona]: [why, e.g. "no UI files in scope"]
- **Lanes failed:** [persona]: [what happened; that area is unreviewed]
- **Not checked statically:** [runtime-only concerns, e.g. "actual query plans", "screen-reader behavior", "load under production traffic"]
- **Assumptions:** [e.g. "assumed the orders table is large; no scale was given"]
- **Slices:** [for sliced runs, which persona saw which slice, and how many waves ran]
- **Trust and execution:** [e.g. "fork PR: no project commands run, verification by reading only" / "ran the unit tests for src/orders/ in a worktree"]
- **Untracked files included:** [for working-tree targets: new files that have no history]

### Suggested next steps
1. [Highest-leverage action, e.g. "Fix #1 and #2 before merge; both are one-line scoping changes."]
2. [Routing, e.g. "Write regression tests for #1 and #3 first (`implementation:tdd`)."]
3. [e.g. "After the fixes, re-run only the security persona, not the whole review."]
````

## Choosing the verdict

Use the verdict ladder in `finding-schema.md`, the same one every review skill uses. A Confirmed or Likely finding counts; a refuted one doesn't, and neither do pre-existing issues or hardening notes. With only medium findings, list them as follow-ups. For Merge, still include Coverage so the reader knows what "no issues" covered.

## Style rules

- Put the verdict first. Readers decide in the first three lines whether to keep reading.
- Write each finding as a failure scenario, not a category. "A signed-in user can read another customer's order" gets fixed. "Possible IDOR" gets argued about.
- Cite `path:line` in backticks so the location can be clicked or searched. For a PR that the user wants to post as a comment, add permalinks that use the full head SHA. Never link a snapshot SHA from a working-tree target; it exists only locally.
- Never include a secret value. If a finding is about an exposed credential, show at most its first four characters followed by "…" and the `path:line`, especially before posting anywhere others can read.
- Leave out praise filler and summaries of what the code does. The author already knows both.
- Keep the refuted section short, one line per item. It shows that the review checked its own claims, and it stops the same false alarm from being raised again later.
