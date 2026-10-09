# Risk Checklist for Feature Plans

Prompts for step 4 of the plan-feature workflow. Skim each category, keep the lines that apply to this change, and write a decision or mitigation for each kept line in the plan. Answering every line for every change is not the goal; noticing the two or three that matter is.

## Contents

1. Edge cases
2. Failure modes
3. Concurrency
4. Security
5. Privacy and data handling
6. Scale and performance
7. Compatibility and rollout
8. Operability
9. User-facing quality (UI changes only)

---

## 1. Edge cases

**Inputs**
- Empty, one, many; zero and negative numbers; maximum lengths and sizes.
- Missing versus null versus empty string; whitespace-only values.
- Duplicates in a list; the same request submitted twice.
- Unicode: combining characters, right-to-left text, emoji, case folding in comparisons and uniqueness.
- Very large inputs: a file, a batch, a page size, or a free-text field far larger than expected.

**Time**
- Time zones, daylight-saving transitions (a local hour that occurs twice or not at all), leap days, month-end arithmetic.
- Server time versus user-local time versus business-local time; which one each comparison uses.
- Clock skew between machines; ordering by timestamp when two events share one.

**State and relationships**
- Related records that are deleted, archived, disabled, or not yet created.
- Records in an intermediate state (draft, pending, processing) when the new code path reaches them.
- Existing rows that predate the feature: do they need defaults or a backfill?
- Permissions that change while a long operation is running.

## 2. Failure modes

- A downstream dependency is slow, returns errors, or is unreachable: what does the user see, and does anything retry?
- Timeouts: are they set on every outbound call, and are they shorter than the caller's timeout?
- Partial failure in a multi-step operation (step 2 of 3 fails): is the result consistent, compensated, or resumable? A guard re-checked only in the last step does not protect the steps before it.
- Writes spanning a database and another system (a queue, a cache, an email provider): what if one succeeds and the other fails? Consider the transactional outbox pattern or an idempotent retry.
- Retries: is every retried operation idempotent (an idempotency key, an upsert, a conditional update)?
- Retry policy: retries are bounded, use exponential backoff with jitter, and happen at one layer only (a client, a gateway, and a queue worker that each make three attempts turn one failing call into 27). A failing dependency trips a circuit breaker or sheds load instead of being hammered harder.
- Poison input: a message or record that always fails. Is there a dead-letter path and an alert, or does it block the queue?
- Resource exhaustion: disk, memory, connection pool, file handles, third-party quota.
- A deploy, restart, or scale-down in the middle of a long-running job: does it resume or restart safely?

## 3. Concurrency

- Two users edit the same record: last write wins, a version check (optimistic locking), or a lock?
- Check-then-act races ("if no row exists, insert"): use a unique constraint plus handling of the conflict, not a prior read.
- Read-modify-write on counters, balances, quotas, or limits: use an atomic update or a lock; a read followed by a write in application code races.
- Double submit from a UI or a client retry: idempotency key or natural deduplication.
- Message queues usually deliver at least once and may reorder: are handlers idempotent and order-tolerant?
- Background job versus user action on the same record (for example a cleanup job versus a restore): does the job re-check its condition at write time?
- Lock ordering when multiple locks are taken, to avoid deadlocks; keep transactions short and free of network calls.

## 4. Security

- **Authentication** on every new entry point: HTTP route, RPC method, webhook receiver, message handler, CLI command, scheduled job that acts on behalf of a user.
- **Authorization**, function-level (may this role call this?) and object-level (may this user act on *this* record?). Changing an id in a URL or payload is the most common bypass.
- Input validation at the trust boundary; parameterized queries; no string-built queries, shell commands, or file paths from user input.
- Output encoding for HTML, CSV and spreadsheet exports (formula injection when a cell starts with `=`, `+`, `-`, `@`, a tab, or a line break; see the OWASP CSV Injection page for current escaping advice), and any other rendered format.
- Server-side fetching of user-supplied URLs (request forgery to internal services). Check the resolved address, not just the hostname.
- Cross-site request forgery protection on new state-changing endpoints in apps that authenticate with cookies.
- Mass assignment: new model fields are not writable through existing create or update endpoints unless explicitly allow-listed.
- Cache keys include every dimension that changes the response (user, account, role, locale); a missing one serves one user's data to another.
- File uploads: type and size limits, storage outside the web root, malware scanning if required, safe download headers.
- Secrets: where they live, how they are rotated, never in logs, URLs, or client bundles.
- Abuse: rate limits, enumeration (do responses reveal whether an account exists?), expensive operations a user can trigger repeatedly.
- Audit trail for sensitive actions: who did what, when, to which record.
- New third-party dependencies: maintenance status, license, known vulnerabilities, transitive footprint.
- When several of these apply or money, credentials, or regulated data are involved, schedule a dedicated review (the `review-suite:secure-code-review` skill) rather than relying on the plan alone. A lightweight threat-modeling pass using STRIDE (spoofing, tampering, repudiation, information disclosure, denial of service, elevation of privilege) is a good structure for the plan's security section.

## 5. Privacy and data handling

- Classify new fields: personal data, sensitive personal data, financial, health, credentials, or none.
- Data minimization: is every new field needed, and needed for this long?
- Where the data flows: logs, analytics events, error trackers, caches, search indexes, exports, backups, third parties. Each copy is subject to the same obligations.
- Retention and deletion: how long it is kept, how it is deleted, and whether user deletion or data-subject requests reach every copy (including soft-deleted rows and derived data).
- Access: who inside the company can read it, and is that access logged?
- Residency or contractual constraints on where the data may be stored or processed.
- Consent or notice changes the product or legal team needs to know about.

## 6. Scale and performance

Use the 10x/100x table from the plan template. For each relevant dimension (rows, requests per second, payload size, fan-out, number of customer accounts, items per account), record today's value with its source, the 10x and 100x values, and what breaks first. Get today's values from existing metrics or cheap aggregate queries under a statement timeout; anything load-shaped runs on synthetic or anonymized data outside production.

Common first breaking points:
- Queries without a limit, or offset pagination over large tables (cost grows with the offset; keyset or cursor pagination does not).
- New filters or sort orders without a supporting index.
- N+1 access: one query or remote call per item in a loop.
- Loading a whole collection or file into memory instead of streaming.
- Long transactions or locks held across a large batch; hot rows that every request updates.
- Synchronous per-item work inside a request that should become a background job with chunking and progress.
- Fan-out: one action that triggers a message, email, or webhook per recipient.
- Cache invalidation storms and cold-cache behavior after a deploy.
- Third-party rate limits and quotas at the new volume.
- Batch jobs whose runtime grows past their schedule interval.

A worked capacity estimate is often a single line: "2M rows today, about 200M at 100x; the nightly scan already takes 40 s, so at 100x it takes over an hour and overlaps the next run, so chunk it now." Decide per row whether to mitigate now or record a known limit with the threshold that would trigger the work.

## 7. Compatibility and rollout

- Mixed versions during rolling deploys and rollbacks: can old code read what new code writes, and the reverse?
- Old clients: mobile apps that cannot be force-updated, third-party integrations, scripts customers wrote against the API. Removing what they use waits for a deprecation notice (for HTTP APIs, the `Deprecation` and `Sunset` response headers, RFC 9745 and RFC 8594) and for telemetry showing old-shape usage at zero or below an agreed threshold, not for a date.
- Messages, jobs, or events already queued in the old format when the new consumer deploys.
- Stored data in old formats: files, serialized blobs, cached entries, search documents.
- Schema changes: expand, migrate, contract, each in its own slice; backfills that are idempotent, resumable, throttled, and verified by counts (details in `data-api:db-migration-safety`).
- Feature flag: type, default, stages, owner, removal slice; what happens to data created while the flag was on if it is turned off.
- One-way doors: destructive data changes, external side effects (emails, payments, partner webhooks), published contracts. Each needs a safeguard: dry run, soft-delete window, backup, staged rollout, or named sign-off.
- Rollback is verified, not assumed: tests run with the flag both on and off, and the flag-off or revert path is exercised once in staging before production.
- Events whose meaning changes: every subscriber is found by search, and a new counterpart event (for example "restored" next to "deleted") has a consumer wherever the original one triggers a side effect.

## 8. Operability

- Metrics that show the feature is working and healthy (rates, errors, latency, queue depth, job duration).
- Logs with enough context to debug one failing request, without sensitive data.
- Alerts with thresholds, and who receives them.
- A kill switch for risky paths, and how fast it takes effect.
- A short runbook entry if on-call might need to act: symptoms, checks, safe mitigations.
- Cost: new infrastructure, storage growth, third-party usage fees.

## 9. User-facing quality (UI changes only)

- Loading, empty, error, and partial states, not just the populated one.
- Keyboard access, focus order, screen-reader labels, color contrast.
- Small screens and long translated strings; locale-aware dates, numbers, and currency.
- Destructive actions: confirmation, undo, or a recovery path.
- Copy reviewed for clarity, and translation keys added if the product is localized.
