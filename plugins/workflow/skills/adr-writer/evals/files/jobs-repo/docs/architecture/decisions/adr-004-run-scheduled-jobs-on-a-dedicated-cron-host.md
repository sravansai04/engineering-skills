# ADR-004: Run scheduled jobs on a dedicated cron host

Date: 2022-08-09

## Status

Accepted

## Context

We have 11 scheduled jobs (invoice generation, nightly exports, cache warmers).
They currently run as crontab entries on whichever application server was set up
first, so a server rebuild silently drops them. We have one platform engineer and
no budget for a managed scheduler this year.

We considered a hosted job service, which removes the host entirely but costs more
than we can justify for 11 jobs, and in-process schedulers inside the app, which
need leader election we don't have.

## Decision

We will run all scheduled jobs from a single dedicated cron host, built from a
checked-in crontab and provisioning script, and owned by the platform engineer.

## Consequences

Jobs survive application server rebuilds and live in version control. The cron
host is a single point of failure: if it is down or mid-deploy, jobs do not run,
and nothing retries them. Revisit if the job count passes about 50 or a missed
run starts costing money.
