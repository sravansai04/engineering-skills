---
status: "accepted"
date: 2023-11-02
decision-makers: Partner Experience tech lead, Staff engineer (API)
---

# 9. Use a GraphQL gateway for the partner dashboard

## Context and Problem Statement

The partner dashboard renders each page from 6 to 9 REST calls across four
services, and its p95 page load was 2.8 s in October 2023 (RUM dashboard). How can
the dashboard fetch what a page needs without many round trips?

## Decision Drivers

* Page load p95 under 1 s for the five busiest dashboard pages
* No changes to the four backend services' REST APIs

## Considered Options

* Keep calling the REST APIs directly from the dashboard
* A backend-for-frontend REST service owned by the dashboard team
* A GraphQL gateway in front of the four services

## Decision Outcome

Chosen option: "A GraphQL gateway in front of the four services", because it lets
each page fetch its data in one round trip without changing the backend APIs.

### Consequences

* Good, because the busiest pages need one request instead of six to nine
* Bad, because the gateway is one more service to run, and its resolvers must be
  kept in step with four backend APIs
* Bad, because per-field authorization rules move into the gateway
