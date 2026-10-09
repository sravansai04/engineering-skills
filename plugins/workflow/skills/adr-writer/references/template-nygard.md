# Template: Short ADR (Nygard style)

This is the original lightweight format Michael Nygard proposed in 2011, and the one the adr-tools CLI generates. Use it for narrowly scoped decisions, or for repos whose ADRs already use Context / Decision / Consequences. It has no separate options section, but the rejected alternatives and the negative consequences still have to appear. They just go inside the existing sections.

Nygard's guidance worth keeping:

- Write in full sentences and paragraphs. Bullets tend to drop the reasoning that links one point to the next.
- Write the decision in active voice: "We will ...".
- Keep it to one or two pages, and number ADRs in sequence without ever reusing a number.

```markdown
# {N}. {Decision as a short imperative phrase}

Date: {YYYY-MM-DD}

## Status

Proposed

<!-- Later: "Accepted", "Rejected", "Deprecated", or
"Superseded by [{M}. {title}]({MMMM}-{slug}.md)". If this ADR replaces one,
add a line: "Supersedes [{K}. {title}]({KKKK}-{slug}.md)". -->

## Context

{The forces at play: the problem, why it needs a decision now, the technical,
organisational and project constraints, and the numbers that matter (with units and
the date and source of each measurement). Keep the tone neutral. Someone who prefers
a different outcome should still recognise this description.

Then cover the alternatives fairly: "We considered {option X}, which {real strength}
but {decisive weakness against a named constraint}. We also considered keeping
{status quo}, which {...}." Give each rejected option its strongest form.}

## Decision

We will {the decision, stated precisely enough to check compliance against}.

{One short paragraph tying the choice back to the forces above, plus its scope: what
this applies to and what it does not decide.}

## Consequences

{What becomes easier and what becomes harder. Include at least one real cost, such as
operational load, migration work, lock-in, a capability given up, or a learning
curve. Name the follow-up work, with owners or issue links, and the conditions that
would make the team revisit this decision.}
```

## Worked mini-example

```markdown
# 14. Use UTC timestamps with offsets in all public API payloads

Date: 2025-03-04

## Status

Accepted

## Context

Our public API returns timestamps in three formats: epoch seconds in the billing
endpoints, local server time without an offset in reporting, and RFC 3339 UTC in
newer endpoints. Partner integration tickets cite timestamp confusion in 23 of 140
support cases this quarter (support dashboard, 2025-02-28). Two partners in other
time zones have shipped off-by-hours bugs.

We considered epoch milliseconds everywhere. It is compact, unambiguous and cheap to
parse, but nobody can read it in logs or support tickets, and partners asked for
readability. We also considered leaving existing endpoints alone and standardising
only new ones. That avoids breaking changes, but the confusion lives mostly in the
old endpoints, so it would not fix the problem we have.

## Decision

We will emit every timestamp in public API payloads as an RFC 3339 string in UTC
with an explicit `Z` suffix. We will accept any RFC 3339 offset on input. Existing
endpoints change in the next major API version. Until then, current fields keep
their format and we add new `*_at` fields alongside them.

This does not cover internal service-to-service messages or database storage.

## Consequences

Partners get one unambiguous, readable format. Every client library must be
regenerated, and partners pay a migration cost at the next major version. Payloads
grow by about 15 bytes per timestamp, which is negligible at current volumes.
Follow-ups: add a contract test that rejects offset-less timestamps (API-412), and
publish a migration guide (DOCS-88). Revisit if partners need the originating
local time zone (an IANA zone such as America/Chicago), for example to schedule
across daylight-saving changes: a UTC timestamp keeps the instant but not the zone,
so this format cannot carry it.
```
