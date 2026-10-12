# Aggregation: validate, dedupe, verify, rank

Read this before step 6 of the workflow. It covers turning the persona results into a single verified, ranked list.

## Contents
1. Validate each persona result and assign review ids
2. Dedupe
3. Choose what to verify
4. Apply verdicts
5. Rank
6. Sanity-read what was not verified

## 1. Validate each persona result and assign review ids

Each result should be a single JSON object that follows `finding-schema.md`. For each persona:

- **Parsed cleanly.** Keep it.
- **Malformed but readable**, for example prose wrapped around the JSON or a missing field. Pull out what you can. Treat a missing `confidence` as `low`. A finding with no `location` or no `failure_scenario` can't be verified, so drop it and record the drop in the coverage notes.
- **Empty `findings` with a sensible `coverage` note.** This is a valid result. Do not re-run a persona just because it found nothing.
- **Coverage says the change could not be viewed** (a denied or failed command, missing files). Treat this as a failed lane, not a clean one, even if `findings` is empty.
- **Failed, timed out, or returned nothing usable.** Re-run that one persona once with the same brief. If it fails again, record the lane as failed in the report's coverage section. A dropped lane that nobody mentions makes the report claim coverage it doesn't have.
- **Launch refused by the runtime's concurrency limit.** The persona never ran. Launch it in the next wave once earlier agents have finished; this does not count as its one retry.

**Assign review ids.** As each result is accepted, give every finding a review-unique id in arrival order (`F-01`, `F-02`, ...) and keep the persona's own id as `source_id` along with the persona name. Personas number their findings independently, so two slices of the same persona both return `SEC-1`; matching verifier verdicts or merges on persona ids would attach them to the wrong finding. From here on, refer to findings only by review id. The neutral id also lets you hand a finding to a verifier without revealing which persona raised it.

**Check every `location` against the pinned head**, not the live checkout: `git show HEAD_SHA:path` prints the file as it was pinned. If a cited line doesn't exist, or doesn't contain anything resembling the evidence, the persona probably read the wrong directory or invented the citation. Re-read the pinned file. If you can't find the code, drop the finding and say so in the coverage notes.

## 2. Dedupe

Personas overlap on purpose: security and data both look at query construction, and performance and data both look at indexes. Merge by **root cause**, not by text similarity.

| Situation | Action |
|---|---|
| Same file, same or overlapping lines (within a few lines), same mechanism | Merge. |
| Same mechanism in several places (the same missing check on four handlers) | Merge into one finding and list the extra places in `also_at`. |
| Same line, different mechanisms (an injection *and* an N+1 in the same query) | Keep separate. They are fixed differently and may have different owners. |
| One finding is a consequence of another (a missing transaction causes the lost-update race) | Keep the root cause and mention the consequence in its failure scenario. |
| Contradictory claims (one persona says a guard exists, another says it is missing) | Keep the stronger-severity claim and send it to verification. The verifier settles it. |

When you merge findings:
- Keep the clearest title, the most concrete failure scenario, and all the evidence.
- Take the highest severity, but only if its reasoning holds. Do not inflate severity just because several personas raised the issue.
- Record every persona that raised it, such as `raised by: security, data-database`. Agreement tells you something about how visible the issue is. It does not prove the issue is real: three personas who misread the same line make the same mistake.
- Keep the review id of the highest-severity source for the merged finding, and note the ids it absorbed.

## 3. Choose what to verify

Verify **every critical and high finding** after dedupe, and also any finding that someone wants to use to block the merge. Run verifiers in parallel (in waves of about 10): one verifier subagent per finding (an Agent tool call in Claude Code), or one per file when several findings in the same file are related. Use the verifier brief in `subagent-briefs.md`. Paste each finding under its review id with `raised_by`, `source_id`, and the persona name stripped, then match the returned verdicts back by review id.

Why this matters: a persona that has just found an issue is anchored on it. A fresh context with an explicit mandate to refute catches what the original reviewer missed. Common examples are an upstream guard, middleware that already validates, a framework default, code that can't be reached, and a pre-existing condition. Each false positive in a review costs triage time and costs credibility for every finding that follows it.

When there are three or fewer high findings and the target is small, you can verify them inline yourself instead of spawning verifiers. You still have to re-read the code from scratch and actually try to refute each one. Don't just re-read the persona's evidence. Verify the same way, one finding after another, when your agent cannot run subagents at all, and say in Coverage that verification ran in the same context as the review.

## 4. Apply verdicts

| Verdict | Action |
|---|---|
| `confirmed` | Keep it. Use the verifier's re-judged severity and add the decisive evidence. Mark it **Confirmed**. |
| `plausible` | Keep it at its current severity, mark it **Likely**, and state the open question in the report so the reader knows what to check. |
| `downgraded` | Keep it at the new severity and note the reason in one line. |
| `pre-existing` | Move it to the report's pre-existing section. It is real, but it should not block this change. |
| `refuted` | Drop it from the findings. List it in the report's refuted appendix with the one-line reason and the citation. Showing what was refuted is part of how the report earns trust. |

If a verifier itself fails, treat the finding as `plausible` and say that verification did not complete. A verifier the runtime refused to launch goes into the next wave.

## 5. Rank

Sort the survivors by the following keys, in order:
1. Severity (critical, high, medium, low).
2. Verification state (Confirmed, then Likely).
3. Confidence (high, medium, low).
4. Blast radius: number of `also_at` locations, how hot the path is, and whether a public surface is affected.

Then apply the report caps: list every critical and high finding; list medium findings up to about 15; collapse low findings into a compact list. A reader who has to scroll past 40 low findings will miss the two that matter.

## 6. Sanity-read what was not verified

Medium and low findings don't get a verifier. Read each one's cited lines once, and drop anything that is obviously wrong, such as a cited line that says something else or a "missing" check that sits two lines above the citation. Mark the rest **Likely**. This quick pass doesn't cost much and stops most of the noise.

Collect every persona's `hardening` entries into the report's Hardening list. Drop duplicates and any entry whose cited line doesn't match, but don't verify or rank them: they carry no severity and don't affect the verdict.
