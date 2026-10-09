# ADR-005: Use PostgreSQL as the primary datastore

Date: 2022-11-14

## Status

Accepted

## Context

The product stores orders, invoices, and customer accounts with strong
relationships between them and needs multi-row transactions for invoicing. The
team has years of relational experience. We considered MySQL, which the team also
knows, and a document store, which fits the catalogue data but not invoicing.

## Decision

We will use PostgreSQL as the primary datastore for all transactional data.

## Consequences

We get transactions, foreign keys, and mature tooling. We take on running
backups, upgrades, and failover ourselves until we move to a managed offering.
