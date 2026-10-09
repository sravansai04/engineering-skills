---
name: adr-writer
description: "Writes, accepts, supersedes, deprecates, and reviews Architecture Decision Records in Nygard or MADR style, following the repo's folder, numbering, and template. Use for \"write an ADR\", \"document why we chose X over Y\", \"supersede ADR 12\", \"does this need an ADR\", or to offer one when a discussion settles a hard-to-reverse choice. Not for implementation plans, design docs, or RFCs (plan-feature), postmortems (incident-postmortem), or READMEs."
argument-hint: "[decision topic | ADR number to accept, supersede, deprecate, or review]"
---

# ADR Writer

An Architecture Decision Record covers one significant decision: what forced it, which options were weighed, what was chosen, and what the team accepted as the cost. Its reader is an engineer a year from now who wasn't in the room. Honest reasoning about trade-offs is what makes it useful, not the format.

The user's input is in `$ARGUMENTS`: a topic, an ADR number, or empty. If empty, work out the decision from the conversation.

## Workflow

### 0. Confirm the user wants a file

Continue only if the user asked to write, record, document, or "write up" a decision, or to accept, supersede, deprecate, or review an ADR. If the skill fired because a discussion settled a choice while the user asked for something else (or nothing), create and edit no files. Offer in one sentence that says why it qualifies ("This looks ADR-worthy: it fixes the billing datastore and is hard to reverse. Want me to record it in docs/adr/?"), then carry on with the actual request. Run the workflow only once they agree.

### 1. Decide whether an ADR is warranted

An ADR log full of trivia stops being read. Hold each candidate to this bar:

| Write an ADR when the decision... | Use something lighter when the decision... |
|---|---|
| Is hard to reverse: undoing it means days of work, a data migration, a public contract change, or leaving a vendor | Can be reverted in one PR and affects only local code. Put it in the PR description or a code comment. |
| Is cross-cutting: it constrains code, services, or teams beyond the change that introduces it | Already follows from an existing ADR or standard. Link that record instead. |
| Is contested: reasonable engineers argued for different options, or the choice will look wrong to a newcomer | Is a style, naming, or formatting preference. Encode it in a linter or style guide. |
| Introduces, replaces, or retires a technology, framework, datastore, or architectural pattern | Is a bug fix, a task list, or how-to instructions. Use the tracker, a runbook, or the docs. |
| Accepts a significant trade-off (consistency vs. availability, cost vs. latency, build vs. buy) | Is still being explored and the options aren't known yet. Do a spike or write a design doc first. |
| Deliberately departs from a standard, an earlier ADR, or common practice | |

Quick test: will a capable engineer who joins in a year ask why the team did this, and will the answer be hard to work out from the code? If both, write the ADR. If not, say so in a sentence or two and name the lighter artifact; if the user still wants one, keep it short.

### 2. Detect the repository's existing convention

Read the existing ADRs first. An ADR in a different format or folder splits the log and breaks tooling that parses it.

```bash
# Config files left by ADR tooling
ls -a .adr-dir .log4brains.yml 2>/dev/null; cat .adr-dir 2>/dev/null
# Tracked files in an ADR-like folder
git ls-files | grep -iE '(^|/)(adrs?|decisions|architecture[-_]decisions?)/' | head -50
# ADRs elsewhere: a "## Status" heading, a "* Status:" / "- Status:" bullet, or a status: key
git ls-files -z '*.md' | xargs -0 grep -liE '^(#+ *status *$|[-*] +status:|status:)' 2>/dev/null | head -20
```

Outside a git checkout, use `find . -name '*.md' -not -path '*/node_modules/*'` instead of `git ls-files`.

Open the two or three most recent ADRs and note: the folder, filename pattern (`0007-use-x.md`, `adr-007-use-x.md`, `20240115-use-x.md`) and number width; the metadata style (YAML front matter, `## Status` heading, or `* Status:` bullet), field names (`deciders` or `decision-makers`), and the exact case and spelling of status values; the headings and their order, and any template file (`template.md`, `adr-template.md`, `0000-template.md`, `templates/template.md`); the title style (`# 7. Use X`, `# ADR-0007: Use X`); any index (`README.md` or `index.md` in the folder, a docs-site nav); and any written approval process (CONTRIBUTING, or a README in the folder).

With no existing ADRs, use `docs/adr/NNNN-kebab-case-title.md` starting at `0001` (or `doc/adr/` if the repo has `doc/` rather than `docs/`) and the full template. If this is the team's first ADR, offer to add `0001-record-architecture-decisions.md` and an index too, and get agreement first, because that sets a team process.

For adr-tools, log4brains, each MADR version, monorepos, date-prefixed names, and number collisions, read `references/conventions.md`.

### 3. Pick the number and filename

If step 2 found date-prefixed filenames, skip numbering: name the file `YYYYMMDD-slug.md` with today's date and refer to the ADR by filename (`references/conventions.md`, section 3). Otherwise the next number is the highest existing number plus one. Don't count files: gaps are normal and numbers are never reused.

```bash
ADR_DIR=docs/adr   # whatever step 2 found
ls "$ADR_DIR" | sed -nE 's/^[^0-9]*([0-9]+).*/\1/p' | sort -n | tail -1
```

Check the default branch too, since another branch may have claimed the number (`references/conventions.md`, section 5). Make the slug short lowercase kebab case.

If the repo uses adr-tools or log4brains, scaffold with that tool so its bookkeeping stays consistent (`references/conventions.md` has non-interactive invocations). adr-tools marks every new ADR **Accepted**; change it to Proposed unless the decision really has been accepted.

### 4. Gather the facts before drafting

Pull from the conversation, linked issues and PRs, design docs, the code involved, and existing ADRs on the same subject (`grep -rliE 'keyword|synonym' "$ADR_DIR"`). An accepted ADR the new decision contradicts must be superseded or amended (step 8), not ignored. Establish:

- What problem prompted this, and why now
- The constraints (scale, budget, deadlines, compliance, team skills) and decision drivers
- Which options were really considered, and the evidence for and against each
- What was decided, by whom, and when. If nothing is decided yet, the ADR is **Proposed**.
- What cost the team accepts, and what would make the decision worth revisiting

**Don't invent facts:** deciders, meeting dates, benchmark results, costs, incident counts. Where something is missing, write a visible `TODO(confirm): ...` marker and list it in the report. One made-up number discredits the whole log. An open marker also keeps the ADR at Proposed (step 8). If the decision itself is unclear, ask one direct question rather than guessing.

### 5. Choose the template

- **Full, based on MADR:** the default when there are two or more serious options or several stakeholders. Read `references/template-madr.md`.
- **Short, Nygard style:** for narrow decisions, or repos whose ADRs use Context / Decision / Consequences. Read `references/template-nygard.md`.
- **The repo's own template** always wins. If it lacks a section for options or negative consequences, put that material in the nearest existing section rather than adding headings.

### 6. Draft section by section

The templates carry worked phrasing. What each section must achieve:

- **Title:** the decision, not the topic ("Use gRPC for internal service-to-service calls", not "RPC framework"). If no option is favored yet, phrase it as a question and restate it on acceptance (step 8).
- **Metadata:** status, an ISO 8601 date with the meaning the repo gives it (step 8, "Dates"), deciders by name or role, and optionally who was consulted and informed.
- **Context and problem statement:** the problem before any solution: what is happening, why now, the constraints, the scale in numbers. Someone who disagrees with the outcome should still agree with it.
- **Decision drivers:** the criteria every option is judged against, most important first, testable where possible ("p99 under 50 ms at 2k requests/s", not "fast"), must-haves marked.
- **Considered options:** at least two real ones, including the status quo when plausible, each judged against the same drivers. One that fails a must-have gets one line saying which.
- **Decision outcome:** `Chosen option: "X", because ...`, tied to named drivers, in active voice, plus what it covers and what it leaves undecided.
- **Consequences:** positive, negative, and neutral. Every decision has a real cost (operational load, learning curve, lock-in, migration work, a capability given up). If none turns up, look harder.
- **Follow-ups and revisit triggers:** actions with owners or issue links, and the conditions that would reopen the decision.
- **Confirmation** (optional): how anyone will know it's being followed, such as an architecture test, lint rule, review checklist item, or dashboard.
- **Links:** issues, PRs, design docs, benchmarks, and related ADRs (supersedes, amends, relates to).

### 7. Hold the writing to these standards

Each standard states its reason, so it generalizes to cases not listed.

- **Problem before solution.** Context written to justify a chosen answer anchors the reader, who can no longer judge whether it fits the problem.
- **Steelman the rejected options,** real strengths included. Someone will propose them again, and if they find a strawman they'll dismiss the ADR and restart the debate.
- **Record what was known at the time.** Date the evidence and state assumptions ("assumes traffic grows less than 3x in two years"), so a later reader can tell whether the decision was wrong or the world changed. Don't backfill hindsight; an after-the-fact ADR says so, with roughly when the decision was made.
- **Quantify.** A number with a unit, source, and date is a checkable claim. "Kafka scales better" is an opinion; "the current queue topped out near 8k events/s in the March load test, against a 40k events/s peak expected next year" is a claim. Label estimates as estimates.
- **One decision per ADR,** so a later ADR can supersede exactly the part that changed.
- **Write for a reader with no context.** Spell out acronyms, link the systems named, and drop "as discussed".
- **Keep confidential material out.** ADR folders are often public, mirrored, or readable company-wide, and git history keeps everything. Leave out secrets, internal hostnames and IPs, customer or personal data, vendor pricing under NDA, and exploitable details of accepted security risks. Summarize ("the vendor quote is about twice the self-hosted estimate") and link to an access-controlled document.
- **One or two pages.** Full sentences for context and justification; bullets for drivers, options, and consequences. Link long material (benchmark output, chat logs, diagrams) rather than pasting it.

### 8. Apply the status lifecycle

```
(draft) -> proposed -> accepted -> deprecated
                    \-> rejected   \-> superseded by ADR-NNNN
```

| Status | Meaning | Editing rule |
|---|---|---|
| Proposed | Under discussion, usually in an open PR | Edit freely, including title and filename |
| Accepted | In force | Body frozen (see below) |
| Rejected | Considered and declined | Keep the file, so the debate isn't reopened |
| Deprecated | No longer applies and nothing replaces it (e.g. the component was removed) | Status plus a one-line reason |
| Superseded by ADR-NNNN | Replaced by a newer decision | Status and link only |

**Accepted ADRs are immutable.** Allowed edits: the status line, superseded-by or amended-by links, typo and dead-link fixes, and, if the repo allows, a dated note appended at the end. Any change to the reasoning or decision goes in a new ADR. The record's value is showing what was known and decided at that moment; rewriting it erases why the system looks the way it does, silently invalidates every PR and comment that cites it, and makes the log unauditable. Never delete or renumber an accepted ADR.

**Dates.** MADR defines `date` as when the record was last updated, status changes included; some teams keep the decision date instead. Follow the existing files, and keep the original decision date visible after any later status change: if `date` moves, add "Originally accepted YYYY-MM-DD." to the pointer line; if it stays, date the pointer line ("Superseded by ADR-0019 on 2025-06-12.").

**To accept or reject a Proposed ADR:**

1. Resolve every `TODO(confirm)`. With markers open the ADR stays Proposed, because acceptance would freeze the gaps in.
2. Set the status and date, and fill in the deciders.
3. If the title is a question, restate it as the decision, `git mv` the file to the new slug, and update the index and inbound links.
4. Follow the repo's approval process. Some teams merge Proposed ADRs for visibility; others keep them in the PR until accepted. With no precedent, suggest that PR approval by the named deciders counts as acceptance, with the status flipped in the last commit before merge.
5. To reject, set Rejected, add a sentence on why, and suggest merging the file rather than closing the PR unmerged, so the reasoning reaches the log.

**To supersede an ADR:**

1. Write the new ADR. Its context says what changed since the old one (new facts, a failed assumption, a new scale), and it links `Supersedes [ADR-NNNN](NNNN-old-title.md)`.
2. In the old ADR, change only the status, to `Superseded by [ADR-MMMM](MMMM-new-title.md)`, and handle its date as above.
3. If only part of the old decision changes, link them with "Amends" / "Amended by" and say which parts still apply, or supersede in full when more than a small part changes.
4. Commit both files together and update the index. The old status changes in the same change that accepts the new ADR; never mark an Accepted ADR superseded by one still Proposed.

adr-tools does steps 1 and 2 with `adr new -s` (`references/conventions.md`).

**To deprecate an ADR:** set Deprecated with a one-line reason (what was removed, and when), handle the date as above, and update the index. If something replaces the decision, supersede instead.

### 9. Update the index and validate

- Update the index the way the repo maintains it: by hand (README table, docs-site nav) or with the tool (`adr generate toc` prints to stdout).
- Run the repo's docs checks, if any: `grep -nE 'markdownlint|remark|vale|lychee|mkdocs|docusaurus' package.json Makefile .pre-commit-config.yaml 2>/dev/null`.
- Check that relative links resolve:

  ```bash
  F=docs/adr/0012-use-grpc-for-internal-calls.md
  grep -oE '\]\([^)#]+\.md' "$F" | sed 's/^](//' | grep -v '://' | while read -r p; do
    [ -e "$(dirname "$F")/$p" ] || echo "broken link: $p"; done
  ```

- Checklist:
  - [ ] An ADR is warranted, and it records one decision, not an implementation plan (step lists and tickets go in a linked plan)
  - [ ] Folder, filename, number, metadata style, headings, and status spelling match the repo; the number is unused on the default branch
  - [ ] The title states the decision; the context states the problem first and neutrally
  - [ ] Drivers are testable where possible, not "scalable" or "modern"
  - [ ] At least two real options, steelmanned, judged on the same drivers, none invented afterwards
  - [ ] The outcome cites drivers and states its scope
  - [ ] At least one negative consequence; follow-ups have owners; revisit triggers are stated
  - [ ] Evidence is dated, nothing is invented, every `TODO(confirm)` is in the report, and none remains if the status is Accepted
  - [ ] The status is right (not a tool's default "Accepted" on a draft) and supersession links point both ways
  - [ ] Nothing confidential; long material linked, not pasted
  - [ ] The index is updated and links resolve

### 10. Report back

Use the report under Report format. If no ADR is warranted, report that and the lighter artifact to use.

## Report format

After writing or updating an ADR:

```
ADR: <path>  (ADR-NNNN, status: Proposed|Accepted|...)
Decision: <one sentence: chosen option and the main reason>
Also changed: <old ADR status edits, index file, or "none">
Needs confirmation:
  - <each TODO(confirm) item, or "none">
Suggested next steps: <e.g. open a PR, name the deciders who must approve, follow-up issues>
```

The review format for an existing ADR is in the next section.

## Reviewing an existing ADR

Run the step 9 checklist, then ask: would a dissenter agree with the context as written? Are the rejected options strawmen, or invented to justify the choice? Is any claim undated or unsupported? Does it contradict an accepted ADR without superseding it? Is the decision cheap to reverse, so that it needs no ADR?

Report only: edit the file only if the user asks, and never edit the body of an Accepted ADR (recommend a superseding one). Rate findings **critical** (the record misleads: invented or wrong facts, or it contradicts an accepted ADR), **major** (a required element is missing or hollow: no real alternative, no cost, context that argues for the answer), or **minor** (wording, dates, links).

```
ADR reviewed: <path>  (ADR-NNNN, status: <status>)
Verdict: ready | needs changes | supersede instead
Findings (most severe first):
  - [critical|major|minor] <section>: <problem> -> suggested rewrite: <text>
Checklist gaps: <step 9 items not met, or "none">
```

## Related skills

- `implementation:plan-feature` plans the implementation once the ADR is accepted.
- `data-api:api-design` designs the API contract itself; this skill records the cross-cutting choice behind it, such as REST vs. gRPC or a versioning policy.
- `data-api:db-migration-safety` applies when the decision means changing a schema or migrating data.
- `workflow:pr-description` describes the PR that adds or supersedes the ADR.
- `workflow:incident-postmortem` covers postmortems, whose action items often call for an ADR.

If a skill named here isn't installed, give the short version inline and list the deeper pass as a follow-up.

## Reference files

- `references/template-madr.md`: the full MADR-based template, the default. Read it when drafting any ADR with two or more serious options.
- `references/template-nygard.md`: the short Context / Decision / Consequences template. Read it for narrow decisions or Nygard-style repos.
- `references/conventions.md`: adr-tools, log4brains, each MADR version, monorepos, number collisions, index upkeep, status formats. Read it when step 2 finds tooling or anything unusual.
- `references/example-adr.md`: a complete accepted ADR plus the status-only edit to the ADR it supersedes. Read it to calibrate quality and tone before the first draft in a session.
