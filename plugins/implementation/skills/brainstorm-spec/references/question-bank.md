# Question bank

Read this during Step 2 (the dialogue) when you are unsure what to ask next,
how to phrase a multiple-choice question, or how to follow up on a vague answer.
It is a pool to draw from, not a script: skip anything the repo, the issue, or
an earlier answer already settled.

## Contents

1. Anatomy of a good question
2. Order of dimensions (and why)
3. Questions by dimension, with exit conditions
4. Turning weak answers into usable ones
5. Question budget by size

---

## 1. Anatomy of a good question

Every question message has four parts:

```text
<why this matters, one clause, tied to something the user said>
<the question, one sentence>
  A. <concrete option>  (recommended: <one-clause reason>)
  B. <concrete option>
  C. <concrete option>
  D. Something else, or "your call" (I'd go with A and record it as a default)
```

Rules that make the options useful:

- **Mutually exclusive.** If two options can both be true, the user's answer
  tells you nothing. "A. Email  B. In-app  C. Both" beats "A. Email  B. Notifications".
- **Concrete.** Options name a behavior or a number, never a quality.
  "Under 1 s / under 10 s / minutes are fine" beats "Fast / Medium / Slow".
- **Two to four real options.** One option is a leading question. Five or more
  means you have not done the thinking; narrow first.
- **Recommendation with a reason.** Mark one option and say why in a clause.
  It lets a busy user answer "A" in two seconds, and it exposes your
  assumption so they can correct it.
- **An honest escape.** Always allow "something else" and "your call". When the
  user picks "your call", take the recommended option and log it as a
  `default` in the ledger, so it shows up for review in the spec.
- **No compound questions.** "Who uses it and how often?" is two questions.
  Ask the one whose answer changes the most downstream.

Use an open question (no options) when you genuinely cannot enumerate the
answer space: the opening "what prompted this?", requests for evidence
("is there a ticket, metric, or quote?"), and names of people or systems.

**Tool mode.** If the host offers a structured multiple-choice tool (Claude
Code's `AskUserQuestion`, for example), use it for discrete choices and keep
plain text for open questions. Such tools differ from the text format above,
so adapt:

- Drop the "Something else" option. The tool adds its own free-text choice
  (`AskUserQuestion` shows it as "Other"); a hand-written one duplicates it and
  uses up a slot.
- Respect the option limit. `AskUserQuestion` takes 2 to 4 options per
  question. Put the recommended option first, end its label with
  "(Recommended)", and put the one-clause reason in its description.
- Offer "Your call (take the recommendation)" as an option only when you have
  fewer than 4 real options. Otherwise mention in the question text that the
  user can type "your call" in the free-text choice.
- Ask one question per call even though the tool accepts several. The answer
  to the first usually changes the others.

Either way, ask one question and end your turn.

## 2. Order of dimensions (and why)

Ask roughly in this order, because each answer constrains the next:

1. **Purpose** - what problem, for whom, and why now. Without it, every later
   answer is a guess about the wrong thing.
2. **Users** - who acts, how often, in what situation.
3. **Success criteria** - what observable change means it worked.
4. **Scope edges and non-goals** - what is deliberately out.
5. **Constraints** - hard limits: compatibility, policy, budget, platform, date.
6. **Behavior at the edges** - empty, huge, concurrent, failing.
7. **Rollout** - who gets it first and how it is undone.

Jump ahead only when the user's answer opens a door ("it has to ship before the
audit on the 30th" is a constraint, so log it now rather than re-asking later).

## 3. Questions by dimension, with exit conditions

Each dimension ends when its **exit condition** holds. Stop asking about a
dimension the moment it does.

### Purpose

Exit condition: you can state the problem in one sentence, without naming a
solution, and the user agrees with that sentence.

- "What prompted this now?" (open)
- "Which of these is closest to the pain?
  A. People can't do X at all  B. X is possible but slow or error-prone
  C. X works but costs us too much (support, infra)  D. Something else"
- "Is there evidence we can cite: a ticket count, a metric, a quote?" (open)

Red flag: the answer describes a solution ("we need a dashboard"). Ask what
decision the dashboard would let someone make, then restate the problem.

### Users

Exit condition: a named primary user, their frequency, and their context, plus
the list of people who must sign off (often just the user).

- "Who is the main person doing this?
  A. End customers  B. Internal staff (which team?)  C. Developers or
  integrators via an API  D. Several of these (which one first?)"
- "How often does that person hit this?
  A. Many times a day  B. Weekly  C. Monthly or rarer"
- "Where are they when it happens?
  A. Desktop, focused work  B. Phone, on the move  C. Unattended, automated"
- "Who else must agree before this is built?
  A. Nobody, your approval is enough  B. A tech lead or architect (who?)
  C. Security, legal or a data owner (who?)  D. Several of these"
  Ask this once, early. Record the names in the spec's `Sign-off needed from`
  header; Step 8 keeps the spec In review until each of them approves.

### Success criteria

Exit condition: two to four outcomes, each with a number or a yes/no check,
each something you could measure after release.

- "If this works, what changes that we could measure?
  A. Time to do X drops (from what to what?)  B. Errors or tickets drop
  C. A new capability exists (yes/no)  D. Something else"
- "What volume does it need to hold up at?
  A. Today's peak (what is it?)  B. 10x today  C. Unknown, measure first"

### Scope edges and non-goals

Exit condition: at least one explicit non-goal the user agreed to, and every
"maybe later" item parked in Non-goals with a reason.

- "Here are three things people might expect this to also do: P, Q, R.
  Which are in for the first version? A. None (recommended: smallest useful
  slice)  B. P only  C. P and Q  D. All three"
- "Is this the first slice of something bigger? A. No, it is the whole thing
  B. Yes, and later slices are already known (list them as non-goals now)"

### Constraints

Exit condition: every hard limit is written down with its source, and nothing
is listed as a constraint that is really a preference.

- "Does this have to work with existing data or clients without changes?
  A. Yes, no breaking changes  B. Breaking is fine with a migration
  C. There is no existing data or client"
- "Is there a date that matters? A. A hard external date (what?)
  B. A soft target  C. No date"
- "Any policy that applies: retention, privacy, accessibility, audit?" (open
  only if the repo docs don't already say)

Probe "constraints" that sound like taste: "must use the new framework" -
is that a team decision on record, or a preference? Preferences go in the
decision log, not the constraints list.

### Behavior at the edges

Exit condition: you know what the user sees for empty input, oversized input,
a concurrent duplicate, and a failure midway.

- "What should happen if the same action is triggered twice at once?
  A. Second one is ignored  B. Second one waits  C. Both run (is that safe?)"
- "If it fails halfway, what does the user see?
  A. An error and nothing changed  B. Partial result, marked as partial
  C. It retries silently and tells them only if retries fail"

### Rollout

Exit condition: who gets it first, how you know it is working, how to undo it.

- "How should this reach users? A. Everyone at once  B. Behind a flag, pilot
  group first (recommended for anything touching existing data)  C. Opt-in"
- "If it misbehaves in production, what is the undo? A. Flag off
  B. Revert the release  C. Needs a data fix (then we should plan that now)"

## 4. Turning weak answers into usable ones

| The user says | Why it is not usable yet | Follow-up |
|---|---|---|
| "It should be fast" | No threshold, no load | "Under 200 ms / under 2 s / under a minute / doesn't matter, at what volume?" |
| "For everyone" | No primary user, so no trade-off can be made | "If only one group could have it first, who?" |
| "Both" (to an either/or) | Doubles scope silently | "Which one first? The other becomes a non-goal for this version." |
| "Whatever is standard" | You will guess, and the guess becomes a requirement | Offer the standard option as A with your reason; log their pick as a default |
| "I don't know" | Fine; unknowns are normal | Offer a safe default, log it as `default`, or record it as an open question with an owner |
| An answer that contradicts an earlier one | Silent contradictions become bugs | Quote both answers back: "Earlier you said X, now Y. Which wins?" |
| A long brief that answers many things at once | Good, but easy to lose details | Fold every fact into the ledger, show it, ask only about the gaps |

## 5. Question budget by size

Budgets keep the dialogue proportionate. They are a smell detector, not a cap:
if you exceed one, either the idea is bigger than you sized it (re-size and
tell the user) or you are asking things the repo could answer.

| Size | Typical questions before approaches |
|---|---|
| Spark | 1-3 |
| Feature | 4-8 |
| Initiative | 8-15, spread across several sessions if needed |
