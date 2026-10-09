# Example: A Complete Postmortem

Read this once per session before your first draft, to calibrate the level of
detail, sourcing, and tone. The company, services, people, and numbers are
fictional. It follows `template.md`. It is shown at status "In review" on
purpose: `scripts/lint_postmortem.py` reports no errors and one warning, the
open `TODO(confirm)` on the revenue figure, and that open item is why it isn't
Published yet. Once finance confirms the range, the marker comes out, the
document passes `--strict`, and it can be published.

---

# Postmortem: Checkout failures for 38% of attempts

| Field | Value |
|---|---|
| Status | In review (approved; publish once finance confirms the revenue range) |
| Incident ID | INC-2026-0314-01 |
| Severity | SEV-3 at declaration, SEV-2 final (error rate exceeded the SEV-2 threshold for a core flow) |
| Incident window (UTC) | 2026-03-14 14:02 to 14:49 |
| Services affected | Web and mobile checkout (orders-service, inventory-service) |
| Postmortem owner | A. Rivera (orders team) |
| Contributors | Orders on-call engineer, inventory on-call engineer, incident commander, support lead |
| Incident commander | SRE on-call |
| Detected by | CheckoutErrorRateHigh alert (14:13). A customer ticket arrived at 14:09 but had no route to on-call (CF8). |
| Notifications | Status page from 14:21 UTC. Account management notified the two marketplace partners on 2026-03-16 under their contracts' notice terms. No regulatory notice required (no personal data involved, no regulated service affected), per the compliance lead. |
| Tags | Factors: design, detection, process, organizational. Failure modes: retry amplification, dependency saturation. Services: orders-service, inventory-service. |
| Related | PM-2025-031 (search-service retry storm, November 2025) |
| Last updated | 2026-03-20 |

## 1. Summary

On Saturday 2026-03-14 from 14:02 to 14:49 UTC (47 minutes), 38% of checkout
attempts failed at the payment step, affecting about 6,100 customers. A routine
node replacement briefly slowed the inventory service. A retry policy shipped
two days earlier made orders-service retry each slow call three times
immediately, which roughly quadrupled load on inventory and saturated it.
Detection took 11 minutes and diagnosis another 26, because nothing on the
dashboards connected the symptoms to the earlier deploy. Rolling back
orders-service ended the impact. The retry fix shipped the next day, and the
remaining action items cover alerting, support escalation, canary analysis,
and adoption of the shared resilient client.

## 2. Impact

| Dimension | Value | Measured or estimated | Source / method |
|---|---|---|---|
| Duration of user impact | 47 minutes (14:02 to 14:49 UTC) | Measured | Checkout error-ratio SLI, saved query Q-118 |
| Users or customers affected | 6,100 customers saw at least one failure; 2,350 of them completed a purchase within 60 minutes | Measured | Distinct account IDs on failed checkout requests, log query L-77 |
| Requests or transactions failed | 11,400 of about 30,000 checkout attempts (the baseline error rate accounts for about 45) | Measured | Q-118 over the window |
| Error rate or latency at worst | 41% peak, 38% mean over the window | Measured | Q-118 |
| SLO error budget consumed | About 95% of the 28-day budget (99.9% SLO, 12.0M requests per window, so a budget of 12,000) | Measured | SLO report for the window ending 2026-03-14 |
| Revenue or SLA exposure | $96k to $130k in lost orders, net of later successful retries. Two marketplace partners have monthly checkout SLAs; flagged to account management. | Estimated | Same hour on the previous four Saturdays minus actual. TODO(confirm): finance validation of the range |
| Data lost, corrupted, delayed, or exposed | None lost or exposed. 37 orders had payment captured with the order left pending; all reconciled by 16:10 UTC. | Measured | Reconciliation query R-12 returns zero orders pending over 30 minutes |
| Support tickets / escalations | 212 tickets, 2 partner escalations | Measured | Support tool report |
| Internal cost | About 14 responder-hours | Estimated | Incident channel participation |

Customers saw a generic "something went wrong" message after entering payment
details. Most who retried a few minutes later succeeded. The 37 customers whose
payment was captured without a confirmed order received a confirmation email
after reconciliation, up to two hours late.

## 3. Timeline

| Time (UTC) | Event | Source |
|---|---|---|
| 2026-03-11 16:20 | Change merged: the inventory client in orders-service moves from 1 retry with backoff to 3 immediate retries, to cut user-visible errors from short inventory 503 bursts seen in February | PR #4812 |
| 2026-03-12 10:05 | orders-service v2026.03.12-1 to 5% canary. Canary analysis (orders error rate and latency) passes after 30 minutes. | Deploy log D-5521 |
| 2026-03-12 10:41 | v2026.03.12-1 at 100% | Deploy log D-5521 |
| 2026-03-14 13:58 | Weekly node-pool maintenance starts draining inventory-service nodes | Cluster events export |
| 2026-03-14 14:01 | One of three inventory replicas terminated. Inventory p99 latency rises from 80 ms to 900 ms. | Inventory dashboard snapshot |
| 2026-03-14 14:02 | **Trigger / impact start:** orders-service calls to inventory start timing out. Retries raise inventory inbound traffic from about 1,200 to 4,700 requests/s. Checkout error ratio passes 5%. | Q-118, inventory inbound-rate query Q-121 |
| 2026-03-14 14:06 | Replacement inventory replica ready. Latency does not recover: all replicas at 100% CPU. | Cluster events export, inventory dashboard |
| 2026-03-14 14:09 | First support ticket: "can't complete payment". It enters the normal support queue; support has no path to page on-call. | Support tool, support lead interview |
| 2026-03-14 14:13 | **Detected:** CheckoutErrorRateHigh fires (more than 5% for 10 minutes), paging orders on-call | Alerting history |
| 2026-03-14 14:15 | **Acknowledged:** orders on-call | Paging log |
| 2026-03-14 14:18 | **Incident declared** at SEV-3. Orders on-call sees inventory timeouts in logs; working hypothesis is inventory capacity. | Incident channel |
| 2026-03-14 14:21 | Raised to SEV-2 once the error-ratio graph shows 38%. Incident commander assigned. Status page set to "investigating". | Incident channel, status page history |
| 2026-03-14 14:24 | **Escalated:** inventory on-call paged | Paging log |
| 2026-03-14 14:31 | Inventory scaled from 3 to 6 replicas. Error ratio drops to 22%, then plateaus as the new replicas saturate. | Incident channel, Q-118 |
| 2026-03-14 14:36 | Inventory on-call notes inbound traffic about 4x normal while checkout traffic is normal, and asks what changed in callers | Incident channel |
| 2026-03-14 14:39 | Deploy history shows the 03-12 retry change. Incident commander decides to roll back orders-service. | Incident channel, deploy log |
| 2026-03-14 14:41 | **Mitigation started:** rollback to v2026.03.10-2 | Deploy log D-5540 |
| 2026-03-14 14:44 | Rollback complete on all instances | Deploy log D-5540 |
| 2026-03-14 14:49 | **Mitigated / impact end:** checkout error ratio back at baseline (under 0.2%) | Q-118 |
| 2026-03-14 15:05 | Status page set to "monitoring". Reconciliation finds 37 orders pending with payment captured. | Status page history, R-12 |
| 2026-03-14 16:10 | All 37 orders reconciled and customers emailed | Ticket ORD-1420 |
| 2026-03-15 16:30 | **Resolved:** v2026.03.15-1 deployed with exponential backoff, jitter, and a 10% retry budget. Incident closed. | PR #4831, deploy log D-5561 |

## 4. Detection and response

| Interval | Duration | Notes |
|---|---|---|
| Time to detect | 11 minutes | Impact start to the alert. A customer ticket arrived 4 minutes earlier but had no route to on-call (CF8). |
| Time to acknowledge | 2 minutes | |
| Time to mitigate | 47 minutes | 26 minutes of it between detection and the rollback decision |
| Time to resolve | 26 hours 28 minutes | Durable fix the next day |

**Detection.** The alert's 10-minute sustain window meant an error ratio of
38% paged no sooner than one at 6%. Support saw the problem first, but a ticket
has no way to reach on-call, so it didn't count as detection.

**Diagnosis.** The visible evidence (inventory timeouts, saturated inventory
CPU, a node replacement minutes earlier) all pointed to inventory capacity, and
the runbook begins with capacity checks. Scaling inventory was a reasonable
first move and partly helped. What broke the deadlock was the inventory
engineer comparing inbound traffic with checkout traffic. No dashboard showed
that ratio, and none showed deploy markers, so a two-day-old change wasn't on
anyone's list.

**Recovery.** Once decided, the rollback took 3 minutes using the standard
tooling, and the reconciliation runbook covered the stuck orders.

## 5. Contributing factors and root cause

### Trigger

Routine weekly node maintenance removed one of three inventory replicas,
raising inventory latency for a few minutes. Before the retry change, the same
maintenance ran on 2026-03-07 with no customer impact.

### Contributing factors

| ID | Category | Factor | How it made sense at the time |
|---|---|---|---|
| CF1 | Design / latent condition | The inventory client retried up to 3 times immediately, with no backoff, jitter, or retry budget | It targeted real user-facing errors from short inventory 503 bursts, and it did reduce them under normal conditions |
| CF2 | Detection | The checkout alert required more than 5% errors sustained for 10 minutes | Tuned a year earlier to stop pages from brief blips during deploys |
| CF3 | Design / latent condition | Inventory had no per-caller limits or load shedding, and its capacity plan covered losing one replica at normal load only | All callers were internal and had been well-behaved. The plan predates the retry change. |
| CF4 | Process / review | The change was reviewed as client-only. Load tests mock inventory, so nothing exercised dependency latency. | The review checklist has no prompt for "changes outbound request volume". Mocks keep load tests stable. |
| CF5 | Detection (rollout) | Canary analysis compared only the canary's own error rate and latency. A 5% canary can't produce enough extra load to show amplification. | Standard canary configuration across services |
| CF6 | Response / diagnosis | Dashboards had no deploy markers or per-caller inbound rates, and the runbook starts with capacity checks | The capacity hypothesis fit every signal that was visible |
| CF7 | Organizational | After PM-2025-031, a shared resilient-client library was published, but adoption was optional and nobody tracked it. orders-service hadn't migrated. | Migration competed with roadmap work, and nothing marked it as urgent |
| CF8 | Process / detection | Support had no fast path to on-call. A cluster of checkout-failure tickets enters the normal queue like any single ticket. | Ticket triage was built for individual customer issues, and earlier checkout incidents had been caught by alerts first |

### Causal analysis

```
Checkout failed for 38% of attempts for 47 minutes
├── orders-service threads blocked waiting on inventory
│   ├── inventory slowed during node replacement (trigger, routine)
│   │   └── no headroom or load shedding for a caller surge            CF3
│   └── retries multiplied inventory load about 4x                     CF1
│       ├── shipped as client-only; nothing tested dependency latency  CF4
│       ├── canary couldn't show amplification                         CF5
│       └── shared resilient client existed but wasn't adopted         CF7
├── 11 minutes to detect                                               CF2
│   └── first customer ticket (14:09) had no route to on-call          CF8
└── 26 minutes from detection to rollback decision                     CF6
```

We treat CF1 and CF7 together as the root cause, in this sense: fixing them
prevents retry amplification from any orders-service client, not just this
one. CF2, CF5, CF6, and CF8 decided how long the incident lasted and how many
customers it reached.

### Has this happened before?

Yes. PM-2025-031 (search-service retry storm) produced the shared
resilient-client library. That action item was completed, but adoption was
left to each team and wasn't tracked (CF7). We searched the postmortem archive
by the "retry amplification" tag and for "retry" and "inventory", and found no
other related incidents.

## 6. What went well

- The rollback took 3 minutes once decided, because the rollback tooling is
  exercised on every release.
- Comparing inbound traffic with caller traffic found the amplification. That
  check is now in the runbook (action 4).
- The status page was updated 3 minutes after the incident was declared.
- The reconciliation runbook covered captured-payment orders, so no customer
  was charged without an order.

## 7. What went poorly

- Support found the problem before monitoring did, and had no way to page
  on-call.
- The incident was declared at SEV-3 while the error ratio was over 30%, which
  delayed assigning an incident commander by 3 minutes.
- Scaling inventory added replicas that the amplified traffic saturated as
  well. Adding capacity can't keep up with a load multiplier.
- Nothing in the tools offered recent changes as a hypothesis, so a two-day-old
  deploy was effectively invisible.

## 8. Where we got lucky

- It happened on Saturday afternoon, at about 40% of weekday peak traffic.
  At peak, doubling inventory would likely not have reduced the error ratio at
  all (estimated from the per-replica saturation point).
- The inventory on-call engineer had debugged a retry storm before and
  recognized the traffic ratio. That knowledge wasn't written down anywhere.
- Node maintenance runs during staffed hours. Overnight, a single responder
  without inventory experience would have been on call.

## 9. Action items

| # | Action | Type | Addresses | Priority | Owner | Due | Tracking |
|---|---|---|---|---|---|---|---|
| 1 | Replace immediate retries in the inventory client with exponential backoff, jitter, and a retry budget capped at 10% of requests (done) | prevent | CF1 | P0 | A. Rivera | 2026-03-16 | ORD-1421 |
| 2 | Migrate all orders-service outbound clients to the shared resilient-client library, and add a CI check that fails on retry config without backoff or a budget | prevent | CF1, CF7 | P1 | J. Okafor | 2026-04-10 | ORD-1425 |
| 3 | Replace the checkout threshold alert with a multiwindow burn-rate page (1h and 5m windows at 14.4x). By the detection-time formula it pages about 2.3 minutes into a 38% error ratio (the old alert took 11) and about 8.6 minutes into a 10% one. Done when a replay of the 2026-03-14 metrics through the new rule pages within 3 minutes. | detect | CF2 | P1 | M. Chen | 2026-03-27 | OBS-310 |
| 4 | Add deploy and flag-change markers and per-caller inbound-rate panels to the orders and inventory dashboards. Make "list changes in the last 72 hours" and "compare inbound with caller traffic" the first runbook steps. | detect | CF6 | P1 | S. Patel | 2026-03-27 | OBS-311 |
| 5 | Extend canary analysis to compare downstream request rate per upstream request against baseline. Done when a staging canary of the 03-12 build fails the new check. | detect | CF5 | P1 | J. Okafor | 2026-04-17 | DEL-88 |
| 6 | Add per-caller rate limits and load shedding to inventory, and re-plan capacity for one-replica loss at weekday peak. Done when a load test at weekday peak with one replica removed and 4x retry traffic keeps checkout errors under 1%. | mitigate | CF3 | P1 | D. Novak | 2026-04-24 | INV-512 |
| 7 | Add a dependency-latency fault scenario (inventory p99 at 1 s) to the checkout pre-release load test | prevent | CF4 | P2 | A. Rivera | 2026-04-30 | ORD-1426 |
| 8 | Track adoption of shared reliability libraries on the engineering scorecard, with an owner per service | process | CF7 | P2 | L. Romero | 2026-04-30 | ENG-204 |
| 9 | Page the orders on-call when 5 or more checkout-failure tickets arrive within 10 minutes, and add a "page on-call" action to the support tool. Done when a replay of the 2026-03-14 ticket stream would have paged, and a month of normal ticket volume would not have. | detect | CF8 | P2 | K. Osei | 2026-04-30 | SUP-77 |

### Considered and not taken

- **Pause weekly node maintenance.** Not taken. Losing one replica is a normal
  event the system has to tolerate, and pausing maintenance would hide the
  condition rather than remove it.
- **Require a load-test sign-off on every client configuration change.** Not
  taken. Too broad and slow. Action 2's CI check targets the specific risk.

## 10. Lessons learned

- Retries multiply load. A client-side change can be a capacity change for
  another team's service, and needs reviewing as one.
- A change can lie latent for days. "It's been fine since Thursday" says
  nothing about whether it's related. Recent changes belong in the first five
  minutes of diagnosis.
- When a dependency saturates because of amplified traffic, reduce load at the
  source. Adding capacity downstream can't keep pace.
- An action item that publishes a library doesn't fix anything until the
  library is adopted. Track adoption, not publication.

## 11. Supporting information

- Saved queries Q-118 (checkout error ratio), Q-121 (inventory inbound rate),
  L-77 (affected accounts), R-12 (pending orders), all pinned to 2026-03-14
  13:30 to 15:30 UTC
- Incident channel export, attached to INC-2026-0314-01
- Glossary: **retry budget**, a cap on retries as a fraction of total requests,
  so retries can't multiply load without limit. **Burn-rate alert**, an alert on
  how fast the error budget is being consumed, rather than on a fixed error
  threshold.

## 12. Review record

| Date | Reviewers | Outcome |
|---|---|---|
| 2026-03-19 | Orders and inventory engineering managers, SRE lead, support lead | Approved with changes: added CF7 and action 8 after the history check, and CF8 and action 9 for the support escalation path. Publish once finance confirms the revenue range. |
