# Gathering Evidence for a Postmortem

Read this in step 3, when you are collecting facts for the timeline and the
impact figures. Use only the sections that match the systems the team actually
runs. Find out what they run by reading the incident channel, the runbooks, the
repo's deploy config (`git ls-files | grep -iE 'deploy|helm|argocd|terraform|workflow|pipeline'`),
and by asking. Don't assume a stack.

Contents: what to capture first, time normalization, sources and commands
(changes and deploys, alerts and paging, chat, metrics, logs, traces and
platform events, cloud audit logs, customer signals), interviewing responders,
recording sources.

## Capture perishable evidence first

Some evidence expires within hours or days. Save these before writing anything:

| Evidence | Why it's urgent | How to keep it |
|---|---|---|
| Kubernetes events | The API server keeps events for one hour by default (`--event-ttl`) | `kubectl get events -A --sort-by=.lastTimestamp -o wide > events.txt` as soon as possible. If they're already gone, the cluster's event exporter or log pipeline may have copies. |
| Pod logs from restarted or deleted pods | Gone once the pod is deleted. `--previous` only reaches the last container instance. | `kubectl logs POD -c CONTAINER --previous --timestamps` while the pod still exists. Otherwise use the central log store. |
| High-resolution metrics | Many stores downsample after days or weeks, which flattens short spikes, or delete raw data entirely (Prometheus local storage keeps 15 days by default) | Export the incident window as CSV or JSON, or snapshot the dashboard with an absolute UTC range |
| Dashboard links | Links like "last 6 hours" show a different window next week | Rewrite every link with absolute `from`/`to` times before pasting it anywhere |
| Chat history | Retention policies, edited and deleted messages | Export the incident channel and the relevant threads |
| Memory | Responders forget the reasoning behind decisions within days | Interview responders within a few working days (see below) |

## Normalize every timestamp to UTC

Chat tools, dashboards, and paging tools show local time by default, and
responders in different zones paste times in their own zone. Convert once, at
capture, and keep the original when it was ambiguous.

```bash
# Local wall-clock time to UTC; handles daylight-saving changes correctly (Python 3.9+)
python3 -c "from datetime import datetime; from zoneinfo import ZoneInfo as Z; \
print(datetime(2026,3,14,9,2,tzinfo=Z('America/Chicago')).astimezone(Z('UTC')).isoformat())"

# Unix epoch seconds (common in chat exports and APIs) to UTC
python3 -c "from datetime import datetime, timezone; print(datetime.fromtimestamp(1773496920, timezone.utc).isoformat())"
```

Watch for daylight-saving transitions inside the incident window, clocks that
drift on hosts without time sync (compare the same event across two sources),
and log lines stamped when they were ingested rather than when they happened.

## Sources and commands

### Changes and deploys: what changed before the trigger?

Look back at least 24 to 72 hours before impact start, and further when a
latent change is suspected. Include config, feature flags, infrastructure,
dependency upgrades, and data migrations, not only application deploys.

```bash
# Commits that landed on the default branch in the window (committer date)
git log origin/main --first-parent --since='2026-03-12T00:00:00Z' --until='2026-03-14T15:00:00Z' \
  --format='%cI %h %s'

# Pull requests merged in the window (GitHub). gh returns only 30 by default
# and truncates silently, so raise the limit.
gh pr list --state merged --limit 500 --search 'merged:2026-03-12T00:00:00Z..2026-03-14T15:00:00Z' \
  --json number,title,mergedAt,url

# Deployment records, if the repo uses GitHub deployments
gh api repos/OWNER/REPO/deployments --paginate \
  --jq '.[] | [.created_at, .environment, .sha[0:12], .ref] | @tsv'

# CI/CD runs of a deploy workflow on a given day (default limit is 20)
gh run list --workflow deploy.yml --created 2026-03-14 --limit 500 \
  --json createdAt,conclusion,headSha,displayTitle,url

# Release history in Kubernetes-based delivery.
# helm's table prints local time with no zone; JSON gives RFC 3339 with an offset.
helm history RELEASE -n NAMESPACE -o json
argocd app history APP_NAME
# `kubectl rollout history` shows revisions but no times. ReplicaSets carry both.
# A rollback reuses an old ReplicaSet, so its creation time is not the rollback
# time; get that from the deploy system or the Deployment's events.
kubectl get rs -n NAMESPACE -l app=NAME --sort-by=.metadata.creationTimestamp \
  -o 'custom-columns=REV:.metadata.annotations.deployment\.kubernetes\.io/revision,CREATED:.metadata.creationTimestamp,NAME:.metadata.name'
```

Use the Deployment's own selector labels in place of `app=NAME`.

A merge time is not a deploy time. Get the time the change reached the affected
environment from the deploy system, and the time it reached all instances if
the rollout was gradual. Feature-flag and config-service changes usually appear
only in that tool's audit log. Check it explicitly, because flag flips are a
frequent trigger that never appears in git.

### Alerts and paging: when did we know, and who knew?

- From the alerting system: the alert definition (condition, threshold, window)
  as it was at the time of the incident, and when it went from pending to
  firing to resolved.
- From the paging tool: page sent, acknowledged, escalated, reassigned. Most
  have an incident log API. For example, PagerDuty exposes
  `GET /incidents/{id}/log_entries` in its REST API.
- Record alerts that fired and were not acted on, and alerts you expected that
  never fired. Both are detection findings.

### Chat: what did people see, think, and decide?

- Export the incident channel and any side threads or DMs that responders agree
  to share. On Slack, admins can export channels, and the
  `conversations.history` API takes `oldest` and `latest` as Unix timestamps.
- Pull decisions, hypotheses, and the evidence that changed someone's mind.
  These become the timeline entries that explain why the response went the way
  it did.
- Quote sparingly and without names in the document. The goal is to show what
  information was available, not to put individuals on display.

### Metrics: what did users experience, and when exactly?

Take the impact start and end from the SLI (error ratio, latency over
threshold, throughput), not from the first alert. For Prometheus-compatible
stores, the HTTP API returns raw series for an exact window:

```bash
curl -sG 'http://PROMETHEUS_HOST:9090/api/v1/query_range' \
  --data-urlencode 'query=sum(rate(http_requests_total{job="checkout",code=~"5.."}[1m])) / sum(rate(http_requests_total{job="checkout"}[1m]))' \
  --data-urlencode 'start=2026-03-14T13:30:00Z' \
  --data-urlencode 'end=2026-03-14T15:30:00Z' \
  --data-urlencode 'step=30s'
```

Metric and label names above are placeholders; read the team's dashboards to
find the real ones. Pull a baseline for the same window one week earlier, so
"elevated" has a reference point.

### Logs: what failed, for whom, and how many?

```bash
# Grafana Loki
logcli query --from='2026-03-14T13:30:00Z' --to='2026-03-14T15:30:00Z' --limit=5000 \
  '{app="orders"} |= "timeout"'

# systemd hosts (times are read as UTC because of the suffix; --utc prints UTC)
journalctl -u SERVICE --since '2026-03-14 13:30:00 UTC' --until '2026-03-14 15:30:00 UTC' --utc -o short-iso

# Google Cloud Logging
gcloud logging read 'timestamp>="2026-03-14T13:30:00Z" AND timestamp<="2026-03-14T15:30:00Z" AND severity>=ERROR' \
  --limit=1000 --format=json

# AWS CloudWatch Logs (epoch milliseconds)
aws logs filter-log-events --log-group-name GROUP \
  --start-time 1773495000000 --end-time 1773502200000 --filter-pattern 'ERROR'
```

Use logs for counts that metrics can't give you, such as distinct affected users
or accounts, specific failed transactions, and the first occurrence of a new
error message. For the first occurrence, search a wider window than the
incident, because the first instance often comes well before anyone noticed.

### Traces and platform events: where did time go, and what did the platform do?

- Traces: find a failing request from the window and a healthy one from the
  baseline, and compare where the time went. Remember that sampled traces tend
  to under-represent the rare slow requests.
- Orchestrator and infrastructure: node replacements, autoscaling, OOM kills,
  restarts, failovers, certificate rotations. `kubectl get events`, `kubectl
  describe pod`, and the cloud provider's instance or maintenance history.

### Cloud audit logs: who or what changed infrastructure?

```bash
# Per region, management events only, last 90 days. Run it for every region involved;
# global services such as IAM log to us-east-1. Data events need a trail or a Lake query.
aws cloudtrail lookup-events --region REGION --start-time 2026-03-14T12:00:00Z --end-time 2026-03-14T15:00:00Z
az monitor activity-log list --start-time 2026-03-14T12:00:00Z --end-time 2026-03-14T15:00:00Z
gcloud logging read 'logName:"cloudaudit.googleapis.com%2Factivity" AND timestamp>="2026-03-14T12:00:00Z"' --limit=500
```

Audit logs answer what changed and when. In the postmortem, describe the change
and the system that allowed it, not the identity of whoever made it.

### Customer and external signals

Support ticket counts by hour, status-page update times, social media
mentions, account-manager escalations, and the vendor's status page or public
incident report for any third-party dependency involved.

## Interviewing responders

Talk to each key responder individually, briefly, and soon, before the group
review. People share more when they're alone, and group discussion merges
everyone's memory into one story. Open by explaining that the goal is to
understand the system, and that nothing said will be used to judge anyone.

Ask questions that reconstruct the situation as they saw it, moving forward in
time:

- What were you doing when this started, and how did you first notice?
- What did you think was happening at that point? What made that seem likely?
- What were you looking at (which dashboard, log, or alert), and what did it show?
- What options did you consider? What made you choose the one you did?
- What were you expecting to happen when you did that? What happened instead?
- What was confusing, slow, or missing? Was anything harder than it should
  have been?
- Was there anything you knew, or suspected, that you didn't say at the time?
  What would have made it easier to raise?
- If a new team member had been on call, where would they have got stuck?

Prefer "what" and "how" questions to "why did you", which sounds like a demand
for justification. Write notes in your own words, confirm the key facts with
the person, and attribute them in the document to roles, not names.

## Recording sources

Every timeline row and every impact figure needs a pointer someone else could
follow: a permalink to a chat message, a dashboard URL with absolute times, a
saved log query, a deploy record, a ticket. Where a fact rests only on someone's
memory, write "per on-call engineer interview". Where it's unknown, write
`TODO(confirm): ...` rather than a plausible guess.
