# Worked Example: Superseding an Earlier Decision

This is a complete, accepted ADR that supersedes an older one. The company, people, systems, and figures are all fictional. Look at the quality and tone, not the specific technology:

- The context describes the problem and gives dated numbers before it names any solution.
- Each driver can be tested, and the must-have is marked.
- The status quo is one of the options, and every option gets its real strengths.
- The outcome points back to the drivers by name.
- The consequences include real costs, follow-ups with owners, and conditions for revisiting.
- Assumptions are stated, so a later reader knows what to re-check.

The second part shows the only edit allowed to the superseded ADR.

---

## The new ADR: `docs/adr/0019-adopt-transactional-outbox-for-order-events.md`

```markdown
---
status: "accepted"
date: 2025-06-12
decision-makers: Order Platform tech lead, Staff engineer (data), Head of SRE
consulted: Payments team, Analytics team
informed: All consumers of order events
---

# 19. Adopt a transactional outbox for publishing order events

In the context of the order service, facing lost and phantom order events whenever
the broker or the service fails mid-request, we decided for a transactional outbox
with a polling relay and against direct publishing, log-based change data capture
and event sourcing, to achieve no lost events without new infrastructure, accepting
a relay process to run and at-least-once delivery for consumers.

## Context and Problem Statement

Since ADR-0007 the order service writes the order and publishes an `OrderPlaced`
event to the message broker from the same request handler. The two writes are not
atomic, and which failure we get depends on their order. Between January and May
2025 we recorded 14 incidents:

- 9 lost events. Most handlers commit the order transaction and then publish, so
  when the broker was unavailable or the pod died between the two steps, the order
  existed with no event and fulfilment never started. The largest incident affected
  1,840 orders.
- 5 phantom events. The checkout handler publishes inside the open transaction,
  before commit, so when the commit then failed, consumers received an event for an
  order that does not exist, and payments tried to charge it.

Peak load is about 1,200 orders per minute (Black Friday 2024). Product expects it to
double by late 2026. Payments and fulfilment both treat these events as the trigger
for real-world actions, so losing one costs money and creates support tickets.

How should the order service publish events so that an event is emitted if and only
if its order transaction commits?

## Decision Drivers

* No lost or phantom events across broker outages, pod crashes or deploys (must-have)
* Added p99 latency on order placement under 10 ms (today's p99 is 180 ms)
* No new stateful infrastructure that SRE must run before Q4 (team capacity)
* Per-order event ordering preserved, because consumers rely on it today
* Works with our current relational database and broker; no rewrite of consumers

## Considered Options

* Keep direct publishing from the handler, adding retries (status quo plus)
* Transactional outbox with a polling relay
* Log-based change data capture (CDC) from the database's replication log
* Event-source the order aggregate (the event store is the source of truth)

## Decision Outcome

Chosen option: "Transactional outbox with a polling relay", because it is the only
option that meets the no-lost-events must-have without new stateful infrastructure.
The extra write measured 2.1 ms p99 in staging on 2025-06-03, well within the 10 ms
budget, and ordering per order is preserved by relaying in insertion order per
order id.

Scope: this applies to all events the order service publishes. It does not decide
how other services publish events. Each team may adopt the pattern with its own ADR
or point to this one. It does not change the broker or the event schemas.

### Consequences

* Good, because an event is now written in the same transaction as the order, so a
  crash can no longer drop or invent one
* Good, because broker outages no longer fail order placement; events wait in the
  outbox table and drain when the broker returns
* Bad, because we run and monitor a new relay worker, and outbox lag becomes a
  critical metric with its own alert
* Bad, because delivery becomes at-least-once: consumers must deduplicate on the
  event id (payments already does; fulfilment and analytics do not)
* Bad, because the outbox table adds write load and needs a retention job
* Neutral, because the event payloads and topics stay the same

### Follow-ups

* [ ] Build the relay worker and outbox lag alert: Order Platform (ORD-311)
* [ ] Add idempotent consumption to fulfilment: Fulfilment team (FUL-88)
* [ ] Add idempotent consumption to analytics ingestion: Analytics team (ANA-140)
* [ ] Add a 7-day retention job for relayed outbox rows: Order Platform (ORD-312)

### Revisit When

* Sustained event volume exceeds roughly 20k events/s, where polling may no longer
  keep lag under 1 s and CDC becomes worth its operational cost
* SRE gains capacity to operate a CDC pipeline for other reasons
* The order service stops being the single writer of order state

### Confirmation

A contract test fails the build if any handler in the order service calls the broker
client directly. The outbox-lag dashboard and its alert (p99 lag over 5 s for
10 minutes) are part of the service's production-readiness review.

## Pros and Cons of the Options

### Keep direct publishing, adding retries

Retry the publish with backoff and log failures for manual replay.

* Good, because no new components and no consumer changes
* Good, because lowest latency of all options
* Bad, because retries cannot help when the pod itself dies between commit and
  publish, so it fails the must-have (6 of the 9 lost-event incidents were pod
  crashes)
* Bad, because it does nothing about phantom events from the checkout handler,
  which publishes before its transaction commits

### Transactional outbox with a polling relay

Write the event to an outbox table in the same transaction as the order. A relay
polls the table and publishes in order.

* Good, because atomic with the business write by construction
* Good, because it uses only the database and broker we already run
* Neutral, because added latency is one small insert (2.1 ms p99 measured)
* Bad, because at-least-once delivery pushes deduplication onto consumers
* Bad, because polling adds a lag floor (median 150 ms at a 100 ms interval in
  staging)

### Log-based change data capture

Stream committed changes from the database's replication log into the broker with a
CDC connector.

* Good, because no application-level polling, low lag, and it scales well past our
  projected volume
* Good, because it also yields a change stream other teams have asked for
* Bad, because it adds a connector cluster and replication-slot management that SRE
  cannot take on before Q4 (fails the infrastructure driver)
* Bad, because it couples the event contract to table structure unless we still add
  an outbox table, which removes much of its advantage

### Event-source the order aggregate

Make an append-only event store the system of record and derive the order tables
from it.

* Good, because events are the source of truth, so the dual-write problem
  disappears entirely
* Good, because it gives a full audit history of every order
* Bad, because it rewrites the order service's persistence and every read path,
  estimated at 3 to 4 quarters
* Bad, because the team has no production experience operating an event store

## More Information

* Supersedes: [ADR-0007](0007-publish-domain-events-from-request-handlers.md)
* Incident list and analysis: INC-2025-031 through INC-2025-077 (summary in ORD-298)
* Staging latency and lag benchmark, 2025-06-03: ORD-305
* Assumptions: one database per service remains the norm; peak load stays under
  5k orders/min through 2026 (Product forecast, May 2025)
```

---

## The superseded ADR: the only permitted edit

In `docs/adr/0007-publish-domain-events-from-request-handlers.md`, only the status metadata changes, plus a one-line pointer to the replacement. The reasoning in the body still says what the team believed in 2023, and that's the point.

This repo follows MADR, where `date` is when the record was last updated, so the date moves and the pointer line keeps the original decision date visible. A repo whose `date` records the decision would leave `date:` alone and write "Superseded by ADR-0019 on 2025-06-12." instead.

```diff
 ---
-status: "accepted"
-date: 2023-02-20
+status: "superseded by ADR-0019"
+date: 2025-06-12
 decision-makers: Order Platform tech lead
 ---

 # 7. Publish domain events from request handlers
+
+Superseded by [ADR-0019](0019-adopt-transactional-outbox-for-order-events.md). Originally accepted 2023-02-20.
```

Commit both files together, and update the ADR index entry for 0007 if the index shows status.

---

## Why this example works (use as a self-check)

- **The problem comes first.** The context says nothing about outboxes until the options section.
- **The status quo is a real option.** Retries are treated seriously and rejected for a specific, evidenced reason: 6 of 9 lost-event incidents were pod crashes, which no retry survives.
- **The evidence is internally consistent.** The context explains how each failure arises (publish after commit loses events; publish before commit invents them), so every number used later in the options traces back to a stated mechanism.
- **No strawmen.** CDC gets credit for scaling better and for being useful to other teams, and it's rejected on a stated driver, not on merit alone.
- **The costs are honest.** The ADR names three real costs and gives each an owner.
- **It's time-stamped.** The measurements carry dates, the forecast is attributed, and the assumptions are listed, so a reader in 2027 can see which one changed.
- **It reopens itself on purpose.** The revisit triggers name the conditions under which CDC wins.
