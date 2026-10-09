---
status: "accepted"
date: 2023-06-20
decision-makers: Engineering managers
---

# 8. Use feature flags for staged rollouts

## Context and Problem Statement

Risky changes ship to every customer at once, and rolling back means a redeploy.
How can we expose a change to a small group first and switch it off without
deploying?

## Decision Outcome

Chosen option: "a self-hosted feature-flag service", because it gives per-tenant
targeting without sending customer identifiers to a third party.

### Consequences

* Good, because a bad change is switched off in seconds
* Bad, because stale flags pile up unless someone removes them
