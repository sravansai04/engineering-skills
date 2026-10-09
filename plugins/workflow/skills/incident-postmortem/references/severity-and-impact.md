# Severity, Postmortem Triggers, and Impact Math

Read this when the team has no written severity scale, when deciding whether an
incident needs a postmortem, or when turning raw metrics into the Impact table.
If the organization already defines any of this, its definitions win; use this
file only to fill gaps, and say in the document which scale you used.

Contents: example severity scale, when a postmortem is required, duration
definitions and alert detection time, impact calculations (users, requests,
error budget, revenue, SLA, data), notification obligations.

## Example severity scale

Classify by user and business impact, actual or imminent. Don't classify by how
hard the fix was or how alarming the cause looked.

| Level | Typical criteria | Typical response |
|---|---|---|
| SEV-1 Critical | A core function is unavailable or unusable for most users. Or customer data is confirmed lost, corrupted, or exposed. Or a widespread contractual SLA breach is under way. | Page an incident commander now. Notify leadership and external comms. Public status update. |
| SEV-2 Major | A core function is badly degraded for a meaningful share of users, an important feature is completely down, or one large customer is fully down. Data is delayed but not lost. Error budget is burning fast. | Page an incident commander. Notify comms. Status update if customers can see it. |
| SEV-3 Minor | Partial degradation with a workaround, a small subset of users affected, or internal tooling down and blocking teams. No risk to data. | The service owner responds promptly, usually without a formal incident commander. |
| SEV-4 Low | Minimal user impact, a cosmetic problem, or a near miss caught before anyone was affected. | Handle in business hours. Track as a ticket. |

Rules that hold whatever the scale looks like:

- **When unsure during the response, pick the higher level.** Arguing about
  severity mid-incident wastes the response, and downgrading later costs little.
  Record both the declared and the final severity in the postmortem, with the
  reason for any change.
- **Classify by the worst moment**, not the average over the window.
- **Security and privacy incidents** usually have a separate classification run
  by the security team. Record both, and follow the security team's process for
  who may read the document.

## When a postmortem is required

These are common triggers in industry practice. Agree on them before incidents
happen so that writing a postmortem never feels like a punishment.

- Any SEV-1 or SEV-2.
- Any data loss or corruption, or exposure of customer data, at any severity.
- On-call had to intervene: a rollback, failover, traffic reroute, manual data
  repair, or emergency config change.
- Resolution took longer than an agreed threshold.
- Monitoring didn't catch it. A customer, a colleague, or luck found it first.
- A single incident consumed a large share of the error budget. One published
  example policy (Google's SRE workbook) uses "more than 20% of the error budget
  over four weeks" and requires at least one top-priority action item on the
  root cause.
- It repeats an earlier incident, or an earlier postmortem's action items should
  have prevented it.
- Any stakeholder asks for one.

Near misses (it nearly happened, or the impact was tiny only by luck) are
optional but cheap, and often teach the most because nobody is defensive.

## Duration definitions

Measure from the **impact start** taken from the SLI graph or logs, not from
when the incident was declared. Teams define these differently, so put the
definitions you used next to the numbers.

| Interval | From | To |
|---|---|---|
| Time to detect (TTD) | Impact start | First alert or report that reached a human who acted on it |
| Time to acknowledge (TTA) | Detected | A responder acknowledges and starts work |
| Time to mitigate (TTM) | Impact start | User impact ends (metrics back near baseline), even if the fix is temporary |
| Time to resolve (TTR) | Impact start | Durable fix in place and the incident closed |

An alert that fired but that nobody acted on isn't detection. Record it in the
timeline as "alert fired, not acted on", because it points at alert quality,
routing, or on-call load.

Be careful with averages. Mean time to recovery across a handful of incidents of
very different kinds is dominated by one or two long ones and says little. For a
single postmortem, report the durations of this incident and compare them with
the team's targets, if the team has any.

### Checking an alerting action item's detection time

Before promising "pages within N minutes", compute it. For an error-budget
burn-rate alert, the time to fire at a constant error ratio is
(1 - SLO) / error ratio x long window x burn-rate threshold (Google SRE
Workbook, "Alerting on SLOs"). For a 99.9% SLO with the common 1h/5m page at
14.4x, a 38% error ratio pages in 0.001 / 0.38 x 60 x 14.4, about 2.3 minutes,
but a 10% error ratio takes about 8.6 minutes. Faster paging at low error
ratios needs a shorter window or a lower threshold, and both cost precision.
Either way, backtest the rule against this incident's metrics before closing the item.

## Impact calculations

Label every figure as measured or estimated, and write the method in the Source
column. A careful estimate with its method shown is useful. A precise-looking
number with no method gets someone into trouble later.

### Users or customers affected

- Best: count distinct users or accounts with at least one failed request in the
  window, from request logs or traces that carry a user or account ID.
- If logs carry no user ID, first look for a proxy that carries identity:
  session IDs, distinct accounts on support tickets, or client IPs (with the
  caveat that NAT merges users and mobile networks split them).
- Without any proxy, report a range rather than one number, and state the
  assumption behind each end. With U active users in the window, a failure
  ratio p, and n typical requests per user in the window:
  - If failures were concentrated on some users (one shard, region, client
    version, or cohort), about p x U were affected. Retries inflate failed
    requests per affected user, so the true count can be lower still.
  - If failures were independent per request, U x (1 - (1 - p)^n) were
    affected. At p = 38% and n = 3 that's about 76% of users, double p x U.
  - Nothing can exceed min(U, failed requests).
- Label any such figure Estimated, give the range and its assumptions, and say
  which end the evidence favors.
- Say what "affected" means: saw an error, saw a delay over N seconds, or was
  charged twice. These have different consequences.
- Count business customers (accounts, organizations, merchants) separately from end
  users when both exist, because SLA and comms decisions follow customers.

### Failed requests and error rate

- Failed requests attributable to the incident = errors in the window minus the
  errors the normal baseline rate would have produced over the same window.
- Report the peak error rate and the mean over the window, and the denominator
  (all requests, or only one endpoint).
- For latency incidents, report the share of requests over the SLO latency
  threshold, not only the p99. A p99 shows how bad the tail got, but not how
  many users were hit.

### SLO error budget consumed

Budget = (1 - SLO target) x volume over the SLO window.

- **Request-based SLO.** With 99.9% availability over a 28-day window and 12
  million requests in that window, the budget is 12,000 failed requests. An
  incident with 11,400 bad requests consumed 11,400 / 12,000 = 95% of it.
- **Time-based SLO.** With 99.9% over 30 days, the budget is 0.001 x 30 x 24 x 60
  = 43.2 minutes. Over 28 days it's 40.32 minutes. Count a minute as bad
  according to the SLO's own definition (for example, the SLI below target for
  that minute), not according to whether the incident channel was open.
- Use the SLO window and volume the team actually reports against. Projecting
  the window's volume from a quiet week understates the budget.
- If no SLO exists, say so. That fact may deserve an action item.

### Revenue and business impact

- Compare with a baseline: the same weekday and hour over the previous two to
  four weeks, adjusted for any known trend, minus the actual figure. Subtract
  transactions that succeeded on a later retry, or the loss is overstated.
- Report a range when the baseline is noisy. Have finance or the business owner
  confirm before the figure goes to leadership.
- Note costs that didn't show up as lost sales: refunds, credits, overtime,
  delayed launches.

### SLA exposure

Whether contractual credits are owed is a decision for finance, legal, or
account management, based on the actual contract terms. The postmortem records
the facts they need: which customers, which measured availability or latency,
over which contractual measurement period. Flag that a threshold may have been
crossed; don't compute or promise credits in the postmortem.

### Data impact

Pick the precise word, because each one leads to a different remedy:

| Term | Meaning | Record |
|---|---|---|
| Lost | Not persisted, and not recoverable | Record counts, the time range, which entities, and whether customers must re-enter anything |
| Corrupted | Persisted with wrong values | Record counts, how the bad records were identified, and the repair method and status |
| Duplicated | Persisted more than once (double charges, duplicate messages) | Record counts and the reconciliation status |
| Delayed | Processed late but correctly | Record the maximum and typical delay, and anything time-sensitive that was affected |
| Exposed | Seen by, or available to, someone not authorized | Record the scope, the data classes, and whether access is confirmed or only possible |

For any exposure of personal data, bring in the security and privacy owners
immediately, before the postmortem is drafted. See "Notification obligations"
below.

If there was no data impact, write "None: verified by ..." and name the check.
A bare "none" invites the question.

### Secondary impact

Support ticket volume, escalations from named large customers, social media,
internal teams blocked, responder hours (count everyone in the incident, not
only the on-call engineer), and work displaced by follow-up.

## Notification obligations

Whether a notice is owed is decided by legal, compliance, security, or account
management, not by the postmortem. The postmortem's job is to make sure the
question was asked and the answer recorded: in the metadata, list who was
notified and when, or "not required, per <owner>". The examples below are
pointers for asking the right people, not legal advice. Thresholds and
deadlines differ by jurisdiction and change over time.

- **Personal data.** The EU GDPR (Art. 33) requires notifying the supervisory
  authority of a personal data breach without undue delay and, where feasible,
  within 72 hours of becoming aware of it. Many other jurisdictions and sectors
  (health, finance, telecoms) have their own breach rules.
- **Operational resilience, even with no data involved.** Under the EU's
  Digital Operational Resilience Act (DORA, Regulation (EU) 2022/2554, with
  timings in Delegated Regulation (EU) 2025/301, Art. 5), financial entities
  send an initial notification of a major ICT-related incident within 4 hours
  of classifying it as major and no later than 24 hours after becoming aware
  of it, an intermediate report within 72 hours of the initial notification,
  and a final report within about a month after that. Under NIS2 (Directive
  (EU) 2022/2555, Art. 23), essential and important entities owe an early
  warning within 24 hours of becoming aware of a significant incident, an
  incident notification within 72 hours, and a final report within a month of
  the notification. In-scope entities include cloud, data-centre, CDN, DNS,
  and managed service providers. "Significant" includes severe operational
  disruption or financial loss, so an outage can qualify.
- **Securities disclosure.** Listed companies may have to disclose material
  cybersecurity incidents within days of determining materiality.
- **Customer contracts.** Enterprise agreements often require notice within a
  set time, a written RCA within N business days, or both. Suppliers to
  regulated firms often inherit their customers' clocks by contract.

When the postmortem has to feed a regulator's final report or a contractual
RCA, write it with that deadline and audience in mind, and keep a version
that legal has cleared.
