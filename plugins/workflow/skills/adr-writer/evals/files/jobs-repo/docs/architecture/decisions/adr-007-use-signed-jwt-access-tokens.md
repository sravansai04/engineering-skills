# ADR-007: Use signed JWT access tokens

Date: 2024-03-18

## Status

Accepted

Supercedes [ADR-006](adr-006-use-server-side-sessions.md)

## Context

Two new services (search and notifications) need the caller's identity. Under
ADR-006 each would have to call the monolith on every request, which added about
40 ms p95 in the February 2024 prototype.

We considered keeping server-side sessions and adding a session-lookup cache to
each service, which keeps instant revocation but spreads session data across
services.

## Decision

We will issue short-lived (15 minute) signed JWT access tokens with refresh
tokens, and services will verify tokens locally.

## Consequences

Services authenticate without a network call. Revocation is no longer instant: a
revoked user keeps access for up to 15 minutes. Key rotation becomes an
operational task with its own runbook.
