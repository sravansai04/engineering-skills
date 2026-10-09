# ADR-006: Use server-side sessions

Date: 2023-01-30

## Status

Superceded by [ADR-007](adr-007-use-signed-jwt-access-tokens.md)

## Context

The web app needs logged-in sessions. Only the monolith reads them today.

## Decision

We will store sessions server-side in PostgreSQL and send the browser an opaque
session cookie.

## Consequences

Sessions can be revoked instantly. Every request costs a session lookup, and any
new service that needs the user's identity must call the monolith.
