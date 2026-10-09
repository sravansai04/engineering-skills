---
status: accepted
date: 2023-04-11
deciders: Backend leads
---

# Use REST for internal service calls

## Context and Problem Statement

We are splitting the monolith into four backend services (orders, pricing,
inventory, accounts). They need a common way to call each other. Most of the team
has only built HTTP/JSON APIs, and we already run an API gateway and tracing for
HTTP. Which protocol should internal service-to-service calls use?

## Decision Drivers

* Team familiarity, since we have no time budget for training this year
* Works with the existing gateway, tracing, and debugging tools
* Easy to call by hand while debugging

## Considered Options

* REST over HTTP/JSON
* gRPC with Protocol Buffers

## Decision Outcome

Chosen option: "REST over HTTP/JSON", because the whole team already knows it and
it works with our gateway, tracing, and curl-based debugging unchanged.

### Consequences

* Good, because no new tooling or training
* Bad, because clients are hand-written and contracts are checked only by tests
* Bad, because JSON serialization costs more than a binary format on hot paths

## Pros and Cons of the Options

### REST over HTTP/JSON

* Good, because familiar and debuggable with curl
* Bad, because no generated, typed clients without extra work

### gRPC with Protocol Buffers

* Good, because generated typed clients and compact binary payloads
* Bad, because nobody on the team has run it in production, and our gateway does not support it
