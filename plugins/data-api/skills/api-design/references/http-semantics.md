# HTTP Semantics for API Design

Method and status-code semantics come from RFC 9110 (HTTP Semantics) and RFC 9111 (Caching). Infrastructure relies on these semantics: caches, proxies, retry middleware, SDK generators, and monitoring all read the method and the status code without looking at your body. Getting them right means that machinery works for you instead of against you.

Standards status last verified 2026-10. Check datatracker.ietf.org before citing an Internet-Draft's status.

## Contents

1. Method semantics
2. Status-code decision table
3. 401 vs 403 vs 404, and 400 vs 409 vs 422
4. Conditional requests and optimistic concurrency
5. Caching
6. Long-running operations (202 + status resource)
7. Rate limiting
8. Header cheat sheet
9. CORS for browser clients

---

## 1. Method semantics

| Method | Safe | Idempotent | Request body | Use for |
|---|---|---|---|---|
| GET | yes | yes | no defined meaning; some servers and proxies reject it | Read a resource or collection |
| HEAD | yes | yes | no | Same as GET without the body (existence, size, ETag) |
| OPTIONS | yes | yes | rarely | Capabilities; CORS preflight |
| QUERY | yes | yes | yes | Read with a complex query in the body. Standardized in RFC 10008 (2026). |
| POST | no | no | yes | Create in a collection, trigger an action, anything not covered above |
| PUT | no | yes | yes | Replace the whole representation, or create at a client-chosen URI |
| PATCH | no | not by definition | yes | Partial update (format declared by media type; see conventions.md section 5) |
| DELETE | no | yes | avoid | Remove |

- **Safe** means the client isn't asking for a state change. Logging, metrics, and rate-limit counters are fine. Anything a user would call a change is not.
- **Idempotent** describes the effect on server state, not the response. A second `DELETE /items/7` may return 404 while the first returned 204, and the operation is still idempotent. Clients and proxies may automatically retry idempotent requests after a connection failure, so a PUT that increments a counter or appends to a list is a bug.
- **PUT replaces.** Fields the client omits get reset, so the client has to read the resource first, and `If-Match` keeps two writers from overwriting each other. PUT is also a clean way to do idempotent creation: the client picks the ID (`PUT /devices/{client_generated_id}`), and a retry is harmless.
- **PATCH** isn't idempotent by default. A JSON Patch `add` to an array appends twice. Make it safe to retry with `If-Match` or with an idempotency key.
- **QUERY** fits searches whose criteria don't fit in a URL, and it keeps caching and safe retries intact. Before adopting it, check that every hop supports it: gateway, WAF, load balancer, server framework, and client SDKs. Browsers send a CORS preflight for it. Advertise support with the `Accept-Query` response header, which RFC 10008 also defines. Describing a QUERY operation needs OpenAPI 3.2 (`paths./orders/search.query:`); a 3.1 document can't express it, and some linters, differs, code generators, and gateways still lag 3.2, so check yours first. Where support is missing anywhere in that chain, use `POST /{collection}/search` and document that it's safe and can be retried.
- **Custom actions** (`POST /orders/{id}:cancel`, or a sub-resource such as `POST /orders/{id}/cancellations`) are the honest model for a state transition. Pick one style per API.

## 2. Status-code decision table

Use the most specific code a generic client can act on. Clients mostly branch on the class (2xx, 4xx, 5xx) plus a few specific codes (401, 404, 409, 412, 429, 503). Your Problem Details `type` carries everything finer than that.

| Situation | Code | Notes |
|---|---|---|
| Read succeeded | 200 | |
| Resource created synchronously | 201 | `Location` pointing at the new resource. Body is the representation, unless the client sent `Prefer: return=minimal`. |
| Work accepted, will finish later | 202 | `Location` pointing at a status resource (section 6) |
| Success, nothing to return | 204 | No body. Common for DELETE and for PUT or PATCH with `return=minimal`. |
| Resource moved permanently | 308 | Preserves method and body. Many clients won't follow redirects for unsafe methods, so don't rely on redirects for writes. |
| Look elsewhere for the result | 303 | Valid after async completion, but most clients follow it automatically and the status body is lost. Usually prefer 200 with a result link. |
| Conditional GET, unchanged | 304 | Answers `If-None-Match` or `If-Modified-Since` |
| Body can't be parsed (malformed JSON, wrong content encoding) | 400 | |
| One or more fields fail validation (schema or business rule) | 422 or 400 | One status for all field validation, chosen once per API (section 3) |
| Missing, invalid, or expired credentials | 401 | Must include `WWW-Authenticate` |
| Authenticated but not allowed | 403 | Or 404 when existence itself is sensitive (section 3) |
| No such resource, or the caller may not know it exists | 404 | |
| Method not supported on this resource | 405 | Must include `Allow` |
| Can't produce any media type in `Accept` | 406 | |
| Conflicts with current state | 409 | Duplicate unique value, invalid state transition, idempotency key still in flight |
| Removed on purpose and won't return | 410 | After a deprecation's sunset date |
| `If-Match` or `If-Unmodified-Since` failed | 412 | Lost-update protection worked (section 4) |
| Body too large | 413 | Status name in RFC 9110: "Content Too Large" |
| Unsupported `Content-Type` | 415 | For PATCH, also advertise accepted formats with `Accept-Patch` |
| Well-formed but can't be processed | 422 | Status name in RFC 9110: "Unprocessable Content". Also the reply for an idempotency key reused with a different body. |
| Precondition header required but missing | 428 | When `If-Match` is mandatory (RFC 6585) |
| Rate limit or quota exceeded | 429 | `Retry-After` (section 7) |
| Unhandled server fault | 500 | Never echo exception text |
| Feature not implemented | 501 | Rare in APIs |
| Bad response from an upstream dependency | 502 | |
| Overloaded or in maintenance | 503 | `Retry-After` |
| Upstream timed out | 504 | |

Things that go wrong in practice:
- Verbs in CRUD paths (`POST /createUser`, `GET /getOrders`). The method already says what happens, and verb paths fragment the API into one-off shapes. Reserve explicit action paths for real state transitions (section 1).
- A 2xx with an error in the body (`200 OK` with `{"success": false}`). Monitoring, caching, and retry logic read it as success.
- 500 for bad input, such as malformed JSON that crashes a parser. That's the server blaming itself for the caller's mistake, it pages on-call for someone else's bug, and it hides genuine faults.
- 404 for an empty collection. An existing collection with zero items is `200` with an empty `data` array.
- 401 for "logged in but not allowed". That's 403, or 404 when existence is sensitive.

## 3. Choosing between neighbors

**401 vs 403 vs 404**
- 401: the request carries no valid identity. The client should re-authenticate.
- 403: the identity is known and lacks permission, and it's fine for the caller to learn that the resource exists. An example is a member who can view a project but not delete it.
- 404: the resource doesn't exist, or the caller has no right to know it does. Returning 403 for `GET /accounts/123` belonging to another customer confirms that account 123 exists, which turns enumeration into an attack. Apply the rule the same way to every object-ID route.

**400 vs 409 vs 422**
- RFC 9110 defines 422 for content that is syntactically fine but can't be processed. Many APIs use 400 for every validation failure. Clients rarely tell the two apart, so the important thing is to pick one rule, document it, and apply it everywhere.
- Recommended: 400 only when the body can't be parsed at all, and one status (422, or 400 if that's the API's existing rule) with one `validation-failed` problem type for *every* field-level failure, whether it breaks the declared schema (wrong type, missing required field, below `minimum`) or a business rule (end date before start date).
- Some APIs split schema violations (400) from business-rule violations (422). The cost: a request that fails both kinds can't report all its errors in one response, because the schema stage rejects it before the business rules run. If you keep that split, say so in the docs, and expect clients to need two round trips.
- 409 is for conflicts with the resource's current state: a duplicate unique key, cancelling an already-shipped order, or a concurrent request holding the same idempotency key. Some APIs use 422 for invalid transitions. Again, pick one and be consistent.
- 412 is only for failed conditional headers. Don't use it for business preconditions.

## 4. Conditional requests and optimistic concurrency

Without concurrency control, two clients that read version 7 both write back, and the second write silently erases the first. ETags fix this without holding locks between requests.

```http
GET /v1/documents/42
→ 200 OK
  ETag: "v7"

PATCH /v1/documents/42
If-Match: "v7"
Content-Type: application/merge-patch+json
{"title": "Q3 plan"}
→ 200 OK
  ETag: "v8"

PATCH /v1/documents/42          (second client, still holding v7)
If-Match: "v7"
→ 412 Precondition Failed       (application/problem+json; client re-reads and retries)

PATCH /v1/documents/42          (no If-Match, on a resource that requires it)
→ 428 Precondition Required
```

Implementation rules:
- **Make the check and the write one atomic statement.** Reading the version, comparing it in application code, and then writing is a race.
  ```sql
  UPDATE documents
     SET title = :title, version = version + 1, updated_at = now()
   WHERE id = :id AND version = :expected_version;
  -- 0 rows: check existence to choose 404 (gone) vs 412 (stale version)
  ```
- **Derive the ETag** from a version column or a hash of the representation. `If-Match` uses strong comparison, so issue strong ETags (no `W/` prefix) on resources clients will update.
- **For create-only semantics**, `PUT` with `If-None-Match: *` creates the resource if it's absent and returns 412 if it already exists.
- **Clients that can't set headers** can send a `version` field in the body. Apply the same atomic check and keep the HTTP semantics (412) the same.
- **Require `If-Match` (428 when missing)** on resources where lost updates are expensive: shared documents, configuration, money-adjacent records. Introducing that requirement on an existing endpoint is breaking. See breaking-change-checklist.md.

## 5. Caching

- **Per-user data**: `Cache-Control: private, max-age=N` or `no-cache` (store but revalidate). **Sensitive data** (tokens, PII, financial): `Cache-Control: no-store`.
- **Shared, public data**: `Cache-Control: public, max-age=N` plus an `ETag`, so revalidation can return 304 with no body.
- **Set `Vary`** on any request header that changes the response (`Accept`, `Accept-Language`, `Accept-Encoding`). A shared cache must not reuse a response to an authenticated request unless the response explicitly allows it (RFC 9111). Don't depend on edge cases there; mark per-user responses `private`.
- **Field selection and expansion parameters** become part of the cache key. Keep their combinations bounded.

## 6. Long-running operations (202 + status resource)

Use this when the work can outlast a typical gateway or client timeout (a few seconds to tens of seconds). A held-open connection gets cut at some proxy hop, the client retries, and the work runs twice.

```http
POST /v1/exports
Idempotency-Key: "8b0d6c3e-5f9a-4b6e-9d0a-2f6c1e7a4b11"
Content-Type: application/json
{"report": "sales_summary", "period": "2026-09"}

→ 202 Accepted
  Location: /v1/operations/op_01JA8Z6
  Retry-After: 5
  {"id": "op_01JA8Z6", "status": "queued", "created_at": "2026-10-09T14:03:00Z"}

GET /v1/operations/op_01JA8Z6
→ 200 OK
  {"id": "op_01JA8Z6", "status": "running", "progress": {"completed": 40, "total": 100}}

GET /v1/operations/op_01JA8Z6
→ 200 OK
  {"id": "op_01JA8Z6", "status": "succeeded",
   "result": {"export": "/v1/exports/exp_7QK2"}, "completed_at": "2026-10-09T14:05:12Z"}
```

Rules:
- `status` is a closed lifecycle: `queued` → `running` → `succeeded` | `failed` | `canceled`. Terminal states never change.
- Reading a failed operation still returns **200**, because the read succeeded. The failure goes in an `error` member formatted as Problem Details.
- Send `Retry-After` as a polling hint. Clients should back off. Don't let them poll in a tight loop.
- Offer cancellation if it's meaningful (`POST /v1/operations/{id}:cancel`). Document that cancellation is best effort.
- Authorize the operation resource exactly like the thing it operates on. Operation IDs show up in logs and URLs, and an unprotected status endpoint leaks results.
- Document how long finished operations are retained. Put an `Idempotency-Key` on the POST so a retry returns the same operation instead of starting a duplicate job.
- Webhooks or callbacks for completion are a good addition. Keep polling as the fallback, because webhook delivery can fail.

## 7. Rate limiting

- **Always**: respond with 429 and `Retry-After` (seconds or an HTTP-date) plus a Problem Details body. For overload, use 503 with `Retry-After`. `Retry-After` is the one widely standardized signal, so clients should honor it and add exponential backoff with jitter.
- **Quota headers** (optional, pick one scheme and document it):
  - The IETF HTTPAPI working-group draft (`draft-ietf-httpapi-ratelimit-headers`; an Internet-Draft, not an RFC, as of 2026-10) defines two Structured Fields:
    ```http
    RateLimit-Policy: "default";q=100;w=60
    RateLimit: "default";r=42;t=18
    ```
    `q` is the quota, `w` the window in seconds, `r` the quota still available, and `t` the number of seconds in which the client may use no more than `r`. In practice, `t` is the time until the window resets. When a response carries both `Retry-After` and `RateLimit`, the draft says `Retry-After` should not point to a time earlier than the end of that window. Earlier revisions of the draft used separate `RateLimit-Limit`, `RateLimit-Remaining`, and `RateLimit-Reset` headers with different syntax. Don't mix the two forms, and expect the draft to change before it's finalized.
  - The de-facto `X-RateLimit-Limit` / `X-RateLimit-Remaining` / `X-RateLimit-Reset` are widely recognized, but the meaning of `Reset` varies between APIs (epoch seconds or seconds remaining). State which one yours uses.
- **Key the limit on the right identity**: credential or account, not only the client IP. Weight expensive operations (search, export, bulk) more heavily, and keep separate budgets for writes. This is OWASP API4:2023 territory (unrestricted resource consumption).

## 8. Header cheat sheet

| Header | Direction | Purpose |
|---|---|---|
| `Location` | response | New resource (201) or status resource (202) |
| `ETag` / `If-Match` / `If-None-Match` | both | Concurrency control (412, 428) and cache revalidation (304) |
| `Retry-After` | response | Back-off hint on 429, 503, and 202 polling |
| `Prefer` / `Preference-Applied` | request / response | RFC 7240: `return=minimal`, `return=representation`, `respond-async` |
| `Link` | response | RFC 8288 typed links: `rel="next"` for pagination, `rel="deprecation"`, `rel="sunset"` |
| `Deprecation` | response | RFC 9745. Format and rules: breaking-change-checklist.md section 7 |
| `Sunset` | response | RFC 8594. Format and rules: breaking-change-checklist.md section 7 |
| `Idempotency-Key` | request | Retry-safe POST and PATCH; canonical value is a quoted string (conventions.md section 6) |
| `Accept-Patch` | response | PATCH media types the resource accepts (RFC 5789) |
| `Accept-Query` | response | Query formats the resource accepts with QUERY (RFC 10008) |
| `WWW-Authenticate` | response | Required on 401 |
| `Allow` | response | Required on 405 |
| `Vary` | response | Request headers that change the response |
| `traceparent` | request | W3C Trace Context. Lets you correlate a client report with server traces. |
| `Content-Type: application/problem+json` | response | Every error body (RFC 9457) |

## 9. CORS for browser clients

Browser JavaScript can read only a handful of CORS-safelisted response headers. None of the headers this skill relies on is among them, so without CORS configuration the 201 `Location`, ETag concurrency, 429 back-off, and deprecation patterns silently fail for single-page apps, while working fine from curl and server-side clients.

- **Expose what clients must read:** `Access-Control-Expose-Headers: ETag, Location, Retry-After, RateLimit, RateLimit-Policy, Deprecation, Sunset, Link` (plus any others your clients use).
- **Allow the request headers you require:** `If-Match`, `If-None-Match`, `Idempotency-Key`, `Content-Type` (a JSON or patch media type is not safelisted), and `Authorization` go in `Access-Control-Allow-Headers`. Each of them makes the browser send a preflight, as do PUT, PATCH, DELETE, and QUERY.
- **Use an explicit origin allowlist.** Never reflect an arbitrary `Origin` back while sending `Access-Control-Allow-Credentials: true`; that lets any website make authenticated calls as the user. Don't allow the `null` origin.
- **Set `Vary: Origin`** whenever the response's CORS headers depend on the request origin, so caches don't serve one origin's answer to another.
- Cache preflights with `Access-Control-Max-Age` to save a round trip on every write.
