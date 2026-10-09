---
status: accepted
date: 2023-02-07
deciders: API guild
---

# Use OpenAPI for public API contracts

## Context and Problem Statement

Partners integrate against our public API from hand-written documentation that
drifts from the implementation. How should we keep the public contract and the
code in step?

## Considered Options

* Hand-written reference docs (status quo)
* OpenAPI 3.1 spec as the source of truth, with docs and server stubs generated from it

## Decision Outcome

Chosen option: "OpenAPI 3.1 spec as the source of truth", because it lets CI fail
when the implementation and the documented contract disagree.

### Consequences

* Good, because docs and SDKs are generated from one file
* Bad, because every public API change now needs a spec change reviewed first
