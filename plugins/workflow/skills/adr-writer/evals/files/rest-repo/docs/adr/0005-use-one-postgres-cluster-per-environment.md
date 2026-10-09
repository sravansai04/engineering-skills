---
status: accepted
date: 2023-09-26
deciders: Backend leads, SRE lead
---

# Use one Postgres cluster per environment

## Context and Problem Statement

Each of the four backend services needs a relational database. Running a cluster
per service would quadruple backup, upgrade, and failover work for a two-person
SRE team. How should services share database infrastructure?

## Considered Options

* One Postgres cluster per service
* One Postgres cluster per environment, with a separate database and role per service

## Decision Outcome

Chosen option: "One Postgres cluster per environment, with a separate database and
role per service", because it keeps operational load within what two SREs can carry
while still isolating each service's data.

### Consequences

* Good, because one set of backups, upgrades, and failover drills per environment
* Bad, because a noisy service can starve the others of connections and I/O
