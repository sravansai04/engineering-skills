# Representation Conventions

These are defaults for the shape of requests and responses. If the API already has a consistent convention for one of these topics, keep it, and raise any harmful convention as a finding instead of diverging in a single endpoint.

Standards status last verified 2026-10. Check datatracker.ietf.org before citing an Internet-Draft's status.

## Contents

1. Naming and structure
2. Errors: RFC 9457 Problem Details
3. Pagination
4. Filtering, sorting, field selection, expansion
5. Partial updates (PATCH)
6. Idempotency keys
7. Data types: instants, dates, durations, money, IDs, enums, nulls
8. Bulk and batch operations

---

## 1. Naming and structure

- **Use one casing for field names across the whole API.** Match the dominant client ecosystem: `snake_case` and `camelCase` are both fine, but mixing them isn't. Path segments are usually lowercase with hyphens (`/payment-methods`).
- **Name collections with plural nouns, and give items stable IDs:** `/customers/{customer_id}/addresses/{address_id}`. Nest only where the child can't exist without the parent. Keep top-level access (`/addresses/{id}`) for resources that might be re-parented later.
- **Put units and kinds in field names.** Use `size_bytes`, `timeout_seconds`, `created_at` for instants, `birth_date` for date-only values, and `line_count` for counts. A bare `timeout: 30` gets misread.
- **Name booleans positively** (`enabled`, not `disabled`), and use them only for facts that are truly two-valued and will stay that way.
- **Avoid abbreviations and internal jargon.** Your org chart isn't the client's vocabulary.
- **Make every response body a JSON object.** Wrap collections as `{"data": [...], ...}` so pagination and metadata can be added without breaking clients.
- **Never serialize a persistence model directly.** Map it to an explicit response type so new columns, internal flags, and secrets can't leak (OWASP API3:2023, broken object property level authorization).

## 2. Errors: RFC 9457 Problem Details

RFC 9457 (which obsoletes RFC 7807) defines `application/problem+json`. It has five standard members, and you can add extension members.

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/validation-failed",
  "title": "Request validation failed",
  "status": 422,
  "detail": "2 fields are invalid.",
  "instance": "/v1/orders",
  "errors": [
    {"pointer": "#/items/0/quantity", "detail": "must be at least 1"},
    {"pointer": "#/shipping/postal_code", "detail": "is not a valid postal code for country US"}
  ],
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

| Member | Rule |
|---|---|
| `type` | A URI that identifies the problem class. Clients branch on it, so it's part of the contract: renaming it is a breaking change. Ideally it resolves to documentation. If it's omitted, it defaults to `about:blank`, meaning "nothing beyond the status code". |
| `title` | A short summary of the problem type. Keep it the same for every occurrence of that type, except for localization. |
| `status` | Advisory copy of the HTTP status. It must match the real status line. |
| `detail` | Human-readable text about this occurrence. The RFC tells clients not to parse it. Anything a program needs belongs in an extension member. |
| `instance` | A URI identifying this occurrence. Optional. |
| extensions | Machine-readable data specific to the type (`errors[]`, `retry_after`, `balance`, `limit`). Clients must ignore extensions they don't recognize, which lets problem types evolve. |

Practices:
- **Keep a catalog of problem types.** Document each `type` with its status code, what it means, what the client should do, and its extension members. Adding a type for a new condition is fine. Returning a new type, or a different status, for a request that used to succeed is a breaking change.
- **Report every validation failure in one response**, each with a JSON Pointer to the offending field. The `errors` array with `pointer` and `detail` follows the pattern RFC 9457 itself uses in its examples. Use one status and one `validation-failed` type for every field-level failure, whether the rule lives in the schema (`minimum`) or in business logic (a postal code that doesn't match the country), as the example above does. Splitting them across 400 and 422 means a request that fails both kinds can't report everything at once (see http-semantics.md section 3).
- **Leak nothing internal.** Exception messages, SQL, stack traces, internal hostnames, and upstream vendor errors stay out. Log them server-side under a `trace_id` and return that ID.
- **Use the same error shape everywhere**, including the 401, 404 for unknown routes, 405, 413, 415, 429, and 5xx responses that frameworks and gateways produce. Clients should still check `Content-Type` before parsing an error, because an intermediary such as a load balancer may return HTML.
- **Localize deliberately.** If `title` or `detail` is localized, select the language via `Accept-Language`. Clients should never depend on that text.

## 3. Pagination

**Default to cursor (keyset) pagination.** Offset pagination (`?page=40&size=50`) makes the database read and discard every row before the requested page, so deep pages get slower. It also skips or duplicates rows when items are inserted or deleted between requests. Use offset only for small, bounded, slowly changing sets, or when "jump to page N" is a real product requirement.

Request and response:
```http
GET /v1/orders?status=open&limit=50&cursor=eyJ2IjoxLCJxIjoiN2MxZTRiMmEiLCJrIjpbIjIwMjYtMTAtMDlUMTU6MDA6MDAuNDgyMTEzWiIsIm9yZF8xMiJdfQ
→ 200 OK
{
  "data": [ {"id": "ord_11", "created_at": "2026-10-09T14:40:00.871Z"}, "...", {"id": "ord_9", "created_at": "2026-10-09T14:03:00.123Z"} ],
  "next_cursor": "eyJ2IjoxLCJxIjoiN2MxZTRiMmEiLCJrIjpbIjIwMjYtMTAtMDlUMTQ6MDM6MDAuMTIzNDU2WiIsIm9yZF85Il19"
}
```
The cursor here is base64url-encoded JSON, `{"v":1,"q":"7c1e4b2a","k":["2026-10-09T14:03:00.123456Z","ord_9"]}`: a format version, a hash of the normalized filter and sort it was issued for, and the sort keys of the last row returned. The response shows milliseconds, the API's documented precision, but the cursor carries the stored microsecond value (see the precision rule below).
An absent or `null` `next_cursor` means there are no more pages. A `Link: <...>; rel="next"` header (RFC 8288) can carry the same information for HTTP-native clients.

Rules:
- **Default and maximum page size.** Document both. Over the maximum, clamp or reject (400), and document which you do. Changing either later is a breaking change.
- **The ordering must be total.** Every sort ends with a unique tie-breaker, usually the primary key. Sorting on `created_at` alone splits ties unpredictably across pages.
- **Cursors are opaque.** Encode the sort-key values of the last returned row, plus a format version. Tell clients not to parse cursors, because otherwise they'll come to depend on the format. If tampering could matter (for example, the cursor encodes an account scope or a filter), sign or encrypt it. In any case, validate it on the way in.
- **Bind cursors to their query.** Put a hash of the normalized filter and sort in the cursor (`q` above). A cursor replayed with a different filter or sort would return silently wrong results, so reject it with 400 and an `invalid-cursor` problem type. Page size isn't part of the binding; clients may change `limit` between pages.
- **Keep sort keys at full storage precision.** If the database stores microseconds and the cursor carries a truncated value, `(created_at, id) < (:c, :id)` skips every row that falls between the truncated and the real value, and those rows never appear on any page. Encode the raw stored value as a string, or encode only the unique ID and look up the row's sort keys server-side. Never round-trip a sort key through a lower-precision type such as a JavaScript `Date`.
- **Sort keys must be NOT NULL.** A row-value comparison involving NULL evaluates to NULL, so rows with a NULL sort column drop out of every page. If a sortable column is nullable, give it an explicit `NULLS FIRST` or `NULLS LAST` and expand the predicate to handle the NULL band, or sort on a non-null derived value.
- **Make totals opt-in** (`?include=total_count`). Exact counts on large tables are expensive, and most UIs don't need them.
- **Fetch `limit + 1` rows** to know whether another page exists without running a second query.

Keyset query shape (for index and plan review, use `data-api:query-review` if it's installed):
```sql
-- next page, newest first; the cursor carries (created_at, id) of the last row returned
SELECT id, created_at, total
FROM orders
WHERE account_id = :account_id
  AND (created_at, id) < (:cursor_created_at, :cursor_id)
ORDER BY created_at DESC, id DESC
LIMIT 51;  -- limit + 1
-- needs an index on (account_id, created_at DESC, id DESC)
```
Row-value comparison works in PostgreSQL, MySQL, and SQLite. Where an engine lacks it, or doesn't use an index for it, expand it to `created_at < :c OR (created_at = :c AND id < :id)`.

## 4. Filtering, sorting, field selection, expansion

- **Filters.** Equality uses plain parameters (`?status=open`). Pick one convention for multiple values, either repeated (`?status=open&status=pending`) or comma-separated (`?status=open,pending`), and use it everywhere. Express ranges with explicit names (`created_after`, `created_before`) or bracket operators (`created_at[gte]=`), again one convention per API.
- **Allowlist every filterable field.** Each filter is a query pattern the database has to serve efficiently at full scale, so it needs an index or a known acceptable cost.
- **Avoid inventing a query language** inside a string parameter. If you truly need one, publish its grammar, parse it into an AST, map fields through the allowlist, and never splice it into SQL. When criteria outgrow the URL, use `QUERY` (RFC 10008) or `POST /{collection}/search` (see http-semantics.md section 1).
- **Sorting.** Use `?sort=-created_at,name`, where a leading `-` means descending. Allowlist the sortable fields, have the server append the ID tie-breaker, and document the default order, which is part of the contract.
- **Field selection.** `?fields=id,name,total` trims payloads for mobile clients. Keep the full representation as the default so existing clients aren't affected.
- **Expansion.** `?expand=customer,lines` inlines related resources. Bound the depth (one or two levels) and how many expansions a request can ask for. Each expanded object needs its own authorization check and response allowlist. An expansion that skips the object-level check is a classic data leak.

## 5. Partial updates (PATCH)

Declare the patch format with the request `Content-Type`, and advertise the formats you support with `Accept-Patch`. Reject anything else with 415.

**JSON Merge Patch (RFC 7396, `application/merge-patch+json`).** The client sends only the fields that change. This is the right default for simple field updates.
```http
PATCH /v1/customers/cus_123
Content-Type: application/merge-patch+json
If-Match: "v7"

{"email": "new@example.com", "phone": null, "address": {"city": "Austin"}}
```
This sets `email`, removes `phone`, and changes `address.city` while leaving the other address fields alone. Limits: `null` always means "remove", so a field can't be set to JSON `null` as a value, and arrays are replaced wholesale, so a client can't edit one element.

**JSON Patch (RFC 6902, `application/json-patch+json`).** An ordered list of operations (`add`, `remove`, `replace`, `move`, `copy`, `test`), applied atomically: if any operation fails, none are applied. Use it when clients need to edit array elements or want an inline precondition.
```json
[
  {"op": "test", "path": "/status", "value": "draft"},
  {"op": "replace", "path": "/lines/2/quantity", "value": 3},
  {"op": "remove", "path": "/lines/0"}
]
```
Operations run in order, so array indexes shift after a `remove`. Put index-sensitive operations first, or address elements by a stable key in a merge-patch design instead.

**Implementation traps:**
- **Absent versus null.** Merge Patch needs three states for each field: absent (leave it alone), `null` (clear it), and a value (set it). Most typed deserializers collapse absent and null into one:
  - TypeScript and JavaScript: check `Object.hasOwn(body, "phone")` before reading `body.phone`.
  - Python with Pydantic v2: read `model.model_fields_set`, or use `model_dump(exclude_unset=True)`.
  - Go: a `*string` is `nil` both when the field is absent and when it's `null`. Decode into `map[string]json.RawMessage`, or use a wrapper type that records whether the field was present.
  - Java with Jackson: `Optional<T>` alone can't express three states. Use a tri-state wrapper such as `JsonNullable<T>` (from the jackson-databind-nullable module), or read the body as a `JsonNode`.
- **Read-only and server-managed fields.** A PATCH that tries to change `id`, `owner_id`, `role`, `balance`, or timestamps should get a 400 or 422 that names the field. Silently ignoring it hides client bugs, and binding it is a mass-assignment vulnerability.
- **Validate the result, not just the patch.** Apply the patch to the current state, validate the merged resource against the full schema and business rules, and only then write it, atomically with the `If-Match` check.
- **Return the updated representation** (200) by default, or 204 when the client sends `Prefer: return=minimal`.

gRPC and AIP-style APIs express the same idea with a field mask. See graphql-grpc.md.

## 6. Idempotency keys

Network failures leave clients unsure whether a POST succeeded, so they retry. Without a key, every retry is a new charge, order, or message. The `Idempotency-Key` request header comes from an IETF HTTPAPI working-group draft (`draft-ietf-httpapi-idempotency-key-header`), which expired without becoming an RFC (an Internet-Draft, not an RFC, as of 2026-10). It's still a widely deployed de-facto convention, especially in payment APIs. The status codes below follow that draft.

**Header format.** The draft defines the value as a Structured Field String, so the canonical form is quoted: `Idempotency-Key: "8e03978e-40d5-43e8-bc93-6894a57f9324"`. Many deployed clients send the bare value. Servers should accept both (strip one pair of surrounding double quotes before lookup), and the docs should show the quoted form.

**Client contract**
- Generate a high-entropy key (a UUID is fine) for each *logical operation*, not for each HTTP attempt. Persist it along with the pending operation so that a retry after a crash or app restart reuses the same key.
- Retry with the same key and the same body. Honor `Retry-After`.

**Server algorithm**
1. Scope the key to the caller: (account or credential, key), plus the operation if you like. Never look keys up globally. A global key space lets one client receive another client's stored response.
2. Compute a fingerprint of the request: method, path, and a hash of the canonicalized body.
3. **Claim the key.** Insert `(scope, key, fingerprint, state = in_progress, locked_until = now() + lease)` and rely on a **unique constraint** to settle races. "Check whether it exists, then act" lets two concurrent retries both proceed. Make the lease comfortably longer than the slowest legitimate attempt.
   - If the work has an external side effect (a payment provider, an email service), commit this insert in its own short transaction *before* the external call. Never hold a database transaction open across a call to a remote service. A slow provider then pins connections and locks, and a crash loses the record that says the call may have happened.
   - If the work is purely local database writes, the claim, the business write, and the stored response can share one transaction. A crash rolls all of it back, and a concurrent retry waits on the unique index, then finds the committed record.
4. **If the insert conflicts**, load the existing record:
   - Different fingerprint → **422** (the key was reused for a different request).
   - Completed → replay the stored status code and body exactly.
   - `in_progress` and the lease is still live → **409** with `Retry-After`. The client retries later.
   - `in_progress` and the lease has expired → the first attempt died mid-flight. Without a takeover rule, every retry gets 409 until the key expires and the client never learns the outcome. Take the record over atomically:
     ```sql
     UPDATE idempotency_keys
        SET locked_until = now() + interval '5 minutes', attempt = attempt + 1
      WHERE scope = :scope AND key = :key
        AND state = 'in_progress' AND locked_until < now()
     RETURNING attempt;
     -- 1 row: you own the retry. 0 rows: another request took it first, so answer 409.
     ```
     Then re-execute with the **same** derived downstream key (step 5), so the provider deduplicates a side effect that may already have happened instead of repeating it.
5. **Do the work.** Pass a derived idempotency key (for example, a hash of scope, key, and step name) to every external call, so each downstream call is idempotent too. For multi-step operations, persist a recovery point after each step that finishes (`charge_created`, `receipt_sent`), so a takeover resumes from the last finished step instead of starting over. Finish in a fresh short transaction: write the business result, store the final status code and body, and set `state = completed`, conditioned on `attempt` still matching yours so a slow original attempt can't overwrite a takeover.
6. If the attempt fails *before* any side effect was committed, delete or reset the record so the client can retry. Deterministic outcomes, such as a validation 4xx or a completed success, can be stored and replayed.
7. If the operation requires a key and the request has none → **400**.

**Retention**: document how long keys are kept. Commonly this is 24 hours to several days, and it must exceed the longest client retry window. After a key expires, a retry is treated as a new request. Say so in the docs.

**Alternatives** that make the operation naturally idempotent:
- Client-chosen IDs: `PUT /v1/transfers/{client_generated_id}`.
- A unique business reference (`external_reference`) with a unique constraint. A duplicate returns 409 with a link to the existing resource.

## 7. Data types

**Instants (a point on the global timeline)**
- Use RFC 3339 strings (a profile of ISO 8601) that always include an offset: `2026-10-09T14:03:00Z`. Return UTC. Accept any offset on input and normalize it. Reject offset-less timestamps, because they're ambiguous.
- Pick a precision and document it. JavaScript `Date` keeps milliseconds, so finer precision is silently truncated in browsers.
- Don't send Unix epoch numbers in new JSON APIs unless the ecosystem demands them. They're unreadable in logs, and seconds-versus-milliseconds bugs are common.

**Dates and local times (not instants)**
- Birthdays, due dates, and business days are `YYYY-MM-DD` with no time and no zone. Converting them to midnight UTC shifts them by a day for half the world.
- Future events in local time (a 9 am meeting in Chicago next March) should be stored as a local date-time plus an IANA zone name (`America/Chicago`). A precomputed UTC instant goes wrong when daylight-saving rules change. RFC 9557 extends RFC 3339 with a bracketed zone suffix for this (`2027-03-15T09:00:00-05:00[America/Chicago]`), but check that your clients' parsers accept it.

**Durations**: use ISO 8601 durations (`PT15M`) or integers with the unit in the field name (`timeout_seconds`). Pick one style per API.

**Money**
- Never use binary floating point. `0.1 + 0.2 != 0.3`, and rounding errors add up across invoices.
- Use either a decimal string, `{"amount": "1234.50", "currency": "USD"}`, or integer minor units, `{"amount_minor": 123450, "currency": "USD"}`. Always include the ISO 4217 currency code.
- The number of minor units depends on the currency: JPY has 0 decimal places, USD 2, and KWD and BHD 3. Use the ISO 4217 table and never assume 2.
- Specify the rounding rule (for example, half-even at line level) and where rounding happens. Return computed totals from the server instead of letting each client recompute them.
- The same advice applies to other exact decimals: tax rates, FX rates, quantities with fractions.

**IDs**
- Make IDs opaque strings. Clients must not parse or do arithmetic on them. Type prefixes (`ord_`, `cus_`) help debugging and catch mixed-up IDs.
- Send integers beyond 2^53 − 1 as strings. I-JSON (RFC 7493) recommends keeping numbers within IEEE 754 double precision, and JavaScript clients lose precision above it.
- Sequential IDs reveal volume and invite enumeration. Random IDs make enumeration harder but are **not** authorization. The object-level check is still required.

**Enums**
- Use strings (`"status": "pending_review"`), never integers, which are meaningless in logs and break when the list is reordered.
- Document every enum as open: "new values may be added; treat unknown values as X." Without that note, adding a value breaks clients that switch over all cases.
- Prefer an enum over a boolean whenever a third state is plausible.

**Null, absent, empty**
- Pick one meaning for "no value" (usually absent or `null`) and document it. Don't use `""`, `0`, or `-1` as sentinels.
- An empty collection is `[]`, never `null`.

## 8. Bulk and batch operations

- **Choose atomic or per-item semantics up front, and document the choice.**
  - Atomic: all items succeed, or none are applied and a single error lists the failing items.
  - Per-item: return 200 with one result per input item, in input order: `{"results": [{"index": 0, "status": 201, "id": "..."}, {"index": 1, "status": 422, "error": {...problem...}}]}`. Some APIs use 207 Multi-Status. It comes from WebDAV, so if you use it, define the JSON body explicitly.
- **Cap the batch size** (and document the cap). Beyond it, accept the work asynchronously with 202 and a status resource. A synchronous request that writes thousands of rows ties up connections and times out.
- **Authorize every item individually.** A bulk endpoint that checks only the first item, or only the collection, is an object-level authorization hole.
- **One idempotency key covers the whole batch request.**
