# API Design: {API or capability name}

| | |
|---|---|
| Status | Draft / In review / Approved / Superseded |
| Authors | {names} |
| Reviewers | {API owners, security, client teams} |
| Last updated | {YYYY-MM-DD} |
| Contract | {path to openapi.yaml / .proto / schema.graphql, or PR link} |
| Related | {tickets, ADRs, prior designs} |

## 1. Summary

{Two or three sentences: what the API lets clients do, and why now.}

## 2. Consumers and use cases

| Consumer | Use case | Volume / payload size | Latency need | Upgrade cadence |
|---|---|---|---|---|
| {mobile app} | {list my orders} | {N req/s, ~2 KB} | {p95 < 300 ms} | {old versions live for 12+ months} |

**Non-goals:** {what this API deliberately doesn't do}

## 3. Resource model

| Resource | Identifier | Owned by / parent | Lifecycle states | Notes |
|---|---|---|---|---|
| {Order} | {`ord_` + opaque string} | {Account} | {draft → submitted → fulfilled / canceled} | {transitions via actions, not PATCH} |

{A state diagram or relationship sketch, if helpful.}

## 4. Operations

| Method and path | Purpose | Auth / scope | Idempotent? | Success | Problem types |
|---|---|---|---|---|---|
| `GET /v1/orders` | List orders | `orders:read` | yes | 200 | invalid-cursor |
| `POST /v1/orders` | Create order | `orders:write` | via `Idempotency-Key` | 201 + Location | validation-failed, idempotency-key-reused |
| `POST /v1/orders/{id}:cancel` | Cancel | `orders:write` | yes (repeat = no-op) | 200 | order-not-cancelable (409) |

## 5. Representations

Schemas are in the contract file. List only the decisions a reviewer needs to see:

| Field | Type / format | Required | Nullable | Writable | Notes |
|---|---|---|---|---|---|
| `id` | string, opaque | yes | no | read-only | |
| `created_at` | RFC 3339 UTC | yes | no | read-only | |
| `total` | `{amount: decimal string, currency: ISO 4217}` | yes | no | read-only | server-computed, rounding: {rule} |
| `status` | string enum (open-ended) | yes | no | via actions only | unknown values → treat as {fallback} |

## 6. Cross-cutting behavior

- **Errors:** RFC 9457 Problem Details. New problem types: {list with status and meaning}
- **Pagination:** {cursor; default N, max M; sort keys plus tie-breaker}
- **Filtering and sorting:** {allowlisted fields; index backing each}
- **Partial updates:** {merge-patch / JSON Patch / not supported; read-only fields rejected}
- **Concurrency:** {ETag + If-Match on which resources; 428 required?}
- **Idempotency:** {which operations; key scope; retention window}
- **Long-running work:** {202 + operation resource? polling interval; webhook?}
- **Rate limits:** {limits per credential; headers used}
- **Caching:** {Cache-Control per operation}

## 7. Security

- **Authentication:** {scheme (OAuth 2.0 bearer tokens, API keys for server-to-server); token lifetime and scopes; unauthenticated operations, if any, and why}
- **Function-level authorization:** {for each action and admin operation: the role or permission required, enforced server-side, deny by default; how it's tested with a low-privilege token}
- **Object-level authorization:** {for each operation that takes an ID: who may access which objects, and where the check lives}
- **Property-level:** {fields hidden or read-only per role; response allowlists}
- **Sensitive data:** {PII or secrets in payloads; kept out of URLs and logs}
- **Browser access:** {CORS origin allowlist and exposed headers, or "not browser-facing"}
- **Abuse cases:** {enumeration, scraping, expensive queries, business-flow abuse; and the mitigations}

## 8. Compatibility and versioning

- **Change type:** {new API / additive / breaking}
- **Breaking changes, if any:** {each one, who is affected, and the migration path}
- **Version:** {scheme and the version this lands in}
- **Deprecations:** {element, `Deprecation` date, `Sunset` date, migration guide link}

## 9. Events and webhooks

{Event types emitted, payload (thin or full), signing scheme, retry policy. Or "none".}

## 10. Observability and SLOs

{Latency and availability targets, per-client usage metrics (needed later for deprecations), the key logs and traces.}

## 11. Alternatives considered

| Option | Why not |
|---|---|
| {offset pagination} | {deep pages slow; unstable under inserts} |

## 12. Rollout

{Feature flag or beta audience, docs and changelog, SDK and codegen updates, client migration steps, the contract-check CI gate (lint and breaking-change diff), and how the implementation is kept conformant to the contract (generated types or stubs, request and response validation in tests, contract tests).}

## 13. Open questions

- {question} ({owner}, needed by {date})

## Appendix: examples

{One full request and response for each operation, including at least one error response with the `application/problem+json` body.}
