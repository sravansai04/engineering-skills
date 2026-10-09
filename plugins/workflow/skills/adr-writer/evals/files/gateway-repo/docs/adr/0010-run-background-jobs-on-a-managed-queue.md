---
status: "accepted"
date: 2024-05-14
decision-makers: Platform lead
---

# 10. Run background jobs on a managed queue

## Context and Problem Statement

Scheduled and background jobs run on one cron host, and 4 runs were missed during
deploys in Q1 2024. How should jobs run so that a deploy or host failure does not
drop them?

## Decision Outcome

Chosen option: "a managed queue with autoscaled workers", because it retries
failed runs and removes the single host.

### Consequences

* Good, because a deploy or host failure no longer drops a run
* Bad, because jobs must now be idempotent, since delivery is at least once
