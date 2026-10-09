# Postmortem Template

Copy everything below the line into the new document. Replace the guidance in
_italics_ and delete it when you're done. Keep headings as they are, because
`scripts/lint_postmortem.py` looks for them. If the team already has a template,
use that one and map these sections onto it.

Contents: full template (sections 1 to 12), customer-facing summary appendix,
lightweight variant for minor incidents and near misses.

---

# Postmortem: _short description of the user-visible problem, not the cause_

_Example: "Checkout failures for 38% of attempts" is better than "Retry storm in
orders-service". The title should still make sense if the analysis later
changes._

| Field | Value |
|---|---|
| Status | Draft / In review / Published |
| Incident ID | _ticket or incident-tool ID, with link_ |
| Severity | _final severity; if it changed, write "SEV-3 at declaration, SEV-2 final"_ |
| Incident window (UTC) | _impact start to impact end, e.g. 2026-03-14 14:02 to 14:49_ |
| Services affected | _services, regions, customer-facing products_ |
| Postmortem owner | _one person, accountable for getting the document to Published_ |
| Contributors | _responders and reviewers who supplied facts_ |
| Incident commander | _role or person who coordinated the response_ |
| Detected by | _the first alert or report that reached someone who acted on it; note earlier signals that didn't reach on-call_ |
| Notifications | _status page, customers, regulators, contractual notices: who was told and when (UTC), or "not required, per <owner>"; note if this document feeds a regulator's or customer's final report_ |
| Tags | _from the team's taxonomy: factor categories, failure modes, services_ |
| Related | _earlier postmortems, ADRs, vendor status reports_ |
| Last updated | _YYYY-MM-DD_ |

## 1. Summary

_Write this last. Three to five sentences a busy reader can stop after: what
users experienced, for how long, how bad, the main contributing factors in one
line, and the state of the most important fixes. No jargon, no names._

## 2. Impact

_Every figure gets a unit, a method or source, and a label: measured or
estimated. Delete rows that truly don't apply, but say "none" explicitly for
data loss and security exposure rather than dropping those rows, since readers
look for them._

| Dimension | Value | Measured or estimated | Source / method |
|---|---|---|---|
| Duration of user impact | | | |
| Users or customers affected | | | |
| Requests or transactions failed | | | |
| Error rate or latency at worst | | | |
| SLO error budget consumed | | | |
| Revenue or SLA exposure | | | |
| Data lost, corrupted, delayed, or exposed | | | |
| Support tickets / escalations | | | |
| Internal cost (responder hours, delayed work) | | | |

_One short paragraph on who was affected and how it felt to them: "Customers
saw a generic error page at the payment step; most who retried within a few
minutes succeeded."_

## 3. Timeline

_All times UTC, in time order, from the first relevant change (which may be
days earlier) through resolution. Bold the milestones. Include dead ends and the
information people had when they decided. Every row has a source._

| Time (UTC) | Event | Source |
|---|---|---|
| YYYY-MM-DD HH:MM | _latent change merged / deployed_ | _deploy log link_ |
| YYYY-MM-DD HH:MM | **Trigger:** _what set it off_ | |
| YYYY-MM-DD HH:MM | **Impact start:** _first user-visible effect_ | |
| YYYY-MM-DD HH:MM | **Detected:** _alert fired / report received_ | |
| YYYY-MM-DD HH:MM | **Acknowledged:** _on-call acknowledged_ | |
| YYYY-MM-DD HH:MM | **Incident declared:** _severity, IC assigned_ | |
| YYYY-MM-DD HH:MM | **Escalated:** _who was pulled in and why_ | |
| YYYY-MM-DD HH:MM | _hypothesis tested, what it showed_ | |
| YYYY-MM-DD HH:MM | **Mitigation started:** _rollback, failover, flag off_ | |
| YYYY-MM-DD HH:MM | **Mitigated / impact end:** _metrics back to baseline_ | |
| YYYY-MM-DD HH:MM | **Resolved:** _durable fix in place, incident closed_ | |

## 4. Detection and response

| Interval | Duration | Notes |
|---|---|---|
| Time to detect (impact start to detected) | | |
| Time to acknowledge (detected to acknowledged) | | |
| Time to mitigate (impact start to impact end) | | |
| Time to resolve (impact start to resolved) | | |

_Two or three sentences each: how we found out (and whether an alert or a human
found it first), how diagnosis went (what slowed it or sped it up), and how
recovery went._

## 5. Contributing factors and root cause

### Trigger

_The event that set things off. Usually ordinary: a deploy, a traffic peak, a
node replacement, a certificate rollover._

### Contributing factors

_The conditions that turned an ordinary trigger into an incident. Group them by
category and give each an ID so action items can point at it. Explain how each
one made sense at the time it was introduced._

| ID | Category | Factor | How it made sense at the time |
|---|---|---|---|
| CF1 | Design / latent condition | | |
| CF2 | Detection | | |
| CF3 | Response / diagnosis | | |
| CF4 | Process / review | | |

### Causal analysis

_A branching why/how tree or short narrative. If the team names a root cause,
state which factor(s) and what "root" means here: fixing it prevents this class
of incident, not only this instance._

```
Checkout requests failed
├── orders-service threads blocked on calls to inventory
│   ├── inventory latency spiked during node replacement   (trigger, normal event)
│   └── retries without backoff multiplied load ~4x        (CF1)
│       └── retry change reviewed as "client-only"; no load test on dependency latency (CF4)
└── 11 minutes passed before anyone was looking            (CF2)
    └── alert needed 5% errors sustained for 10 minutes
```

### Has this happened before?

_Links to earlier incidents with the same factors, and whether their action
items were completed. "No prior incidents found in the postmortem archive,
searched for 'retry' and 'inventory'" is a valid answer._

## 6. What went well

- _Specific things to keep doing, with the reason they worked._

## 7. What went poorly

- _Process, tooling, and system problems. Not people._

## 8. Where we got lucky

- _Things that limited the damage that nobody designed in. Each is a risk that
  may not be there next time; most deserve an action item._

## 9. Action items

_One person per owner cell. Every item links to a ticket in the owning team's
tracker and to the factor it addresses. Detect and prevent items say how
they'll be verified against this incident (replayed metrics, a load test, a
game day). Priority: P0 = before the next change to this system, P1 = this
sprint or the agreed deadline, P2 = backlog._

| # | Action | Type | Addresses | Priority | Owner | Due | Tracking |
|---|---|---|---|---|---|---|---|
| 1 | | prevent | CF1 | P0 | | YYYY-MM-DD | |
| 2 | | detect | CF2 | P1 | | YYYY-MM-DD | |
| 3 | | mitigate | CF3 | P1 | | YYYY-MM-DD | |

_Types: detect, mitigate, prevent, repair, process, investigate._

### Considered and not taken

- _Ideas raised and deliberately not pursued, with the reason. This stops the
  same proposal reappearing in every review._

## 10. Lessons learned

- _Insights another team could use, not a restatement of the action items._

## 11. Supporting information

- _Dashboard snapshots with absolute UTC time ranges, log queries, chat export,
  vendor status report, glossary of terms an outsider wouldn't know._

## 12. Review record

| Date | Reviewers | Outcome |
|---|---|---|
| | | _approved / changes requested; follow-ups_ |

---

## Appendix: customer-facing summary

_Only when customers need an explanation. Keep it separate from the internal
document, and get it approved by whoever owns external communication. No
internal names, hostnames, or speculation. Promise only what has been approved
and scheduled._

- **What happened:** _plain-language description of the symptom and window, UTC
  plus one familiar time zone if the audience expects it_
- **Who was affected:** _which customers and features_
- **Why it happened:** _one or two sentences at the level of "a configuration
  change caused excessive retries between two internal services"_
- **What we're doing about it:** _the approved, scheduled changes_
- **What you need to do:** _"nothing" or the specific steps_

---

## Lightweight variant

For minor incidents and near misses, keep these and drop the rest:

```
# Postmortem: ...
(metadata table: status, severity, window, owner, notifications, tags)
## 1. Summary
## 2. Impact            (a few lines; "none, near miss" is valid)
## 3. Timeline          (milestones only)
## 5. Contributing factors and root cause
## 8. Where we got lucky  (the main section for a near miss)
## 9. Action items
```

Run the linter with `--light` on this variant.
