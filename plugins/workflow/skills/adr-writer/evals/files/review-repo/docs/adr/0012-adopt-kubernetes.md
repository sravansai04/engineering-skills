---
status: proposed
date: 2025-09-02
decision-makers: Platform team
---

# 12. Adopt Kubernetes

## Context and Problem Statement

We need Kubernetes because our deployment setup is outdated. Deploys take forever
and the VMs are hard to manage. Kubernetes is the industry standard and everyone
uses it now, so it is the obvious next step for us.

## Decision Drivers

* Modern
* Scalable
* Industry best practice

## Considered Options

* Keep the VMs
* Nomad
* Kubernetes

## Decision Outcome

Chosen option: "Kubernetes", because it is the best option and it scales.

We will migrate all 23 services, the build runners, and the old reporting box at
build-01.corp.internal (10.20.4.17) by the end of Q4. The managed control plane
from our cloud vendor was quoted at $41,300 a year under our NDA pricing, which is
fine.

### Consequences

* Good, because deploys will be faster
* Good, because we will be able to scale
* Good, because it will help hiring

## Pros and Cons of the Options

### Keep the VMs

* Bad, because it is legacy and does not scale

### Nomad

* Bad, because nobody uses it

### Kubernetes

* Good, because it is the industry standard
* Good, because it is scalable and modern
