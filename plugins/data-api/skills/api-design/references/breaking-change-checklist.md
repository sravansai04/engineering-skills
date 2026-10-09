# Breaking-Change Review Checklist

Use this file for every change to an API that already has clients, and when you're choosing a versioning strategy or planning a deprecation. Schema differs (oasdiff, buf, graphql-inspector) catch structural breaks. Most of the rows below marked "silent" are behavioral, and only a human reviewer will catch them.

## Contents

1. The variance rule
2. The tolerant-reader contract (state it once in your docs)
3. Checklist tables: endpoints, requests, responses, errors, behavior, events
4. Review procedure
5. Shipping a necessary break: expand, migrate, contract
6. Versioning strategies
7. Deprecation and sunset

---

## 1. The variance rule

- **Inputs** (path, query, headers, and bodies that clients send) may become **more permissive**, never stricter.
- **Outputs** (response bodies, headers, status codes, events) may gain new fields, and their value ranges, lengths, and formats may get **narrower**, never wider. Never remove a promised field, and never change what a value means. Widening an output (a longer string, a bigger number, a new enum value or format variant) breaks clients that store or validate against the old bound.
- **Behavior**: the same request has to keep meaning the same thing. Anything a reasonable client could observe and depend on is effectively part of the contract, whether or not it's documented. That includes ordering, defaults, timing class (sync or async), side effects, and which errors happen.

## 2. The tolerant-reader contract

Additive changes are safe only if clients were told to expect them. Publish these rules in the API's documentation from the start:
- Ignore unknown response fields.
- Handle unknown enum values, using a documented fallback.
- Handle unknown Problem Details `type` values by falling back to the HTTP status class.
- Don't depend on field order, on JSON formatting, or on the format of opaque IDs and cursors.
- Follow `Location` and pagination links rather than constructing URLs.

Watch generated clients. Some code generators and strict validators reject unknown properties (for example, schemas with `additionalProperties: false` enforced on the client side) or throw on unknown enum values. If your official SDKs do this, then additive changes break your own SDK users. Fix the generator configuration before you rely on additivity.

## 3. Checklist tables

Legend: **Yes** = breaking. **No** = safe given the tolerant-reader contract. **Silent** = breaking in a way a schema differ either can't see or doesn't fail on by default. For example, oasdiff only sees defaults declared in the spec, and reports a changed default at INFO level, below `--fail-on ERR`. Section 4 shows how to promote such checks.

### Endpoints and transport

| Change | Breaking? | Safe alternative |
|---|---|---|
| Add a new operation or resource | No | |
| Remove or rename an operation, path, or path parameter | Yes | Keep the old route, deprecate it, and add the new one beside it |
| Change an operation's HTTP method | Yes | Add the new method and keep the old one through deprecation |
| Change the host, base path, or version prefix | Yes | Serve both through the deprecation window |
| Require a new header (`If-Match`, `Idempotency-Key`, a custom header) | Yes | Accept it as optional first, then require it in the next major version or for new credentials only |
| Require a new auth scope or permission, or switch auth scheme | Yes | Grandfather existing tokens and communicate a migration date |
| Drop support for a request or response media type | Yes | |
| Switch an endpoint from sync (200/201) to async (202) | Yes | New endpoint, or opt-in with `Prefer: respond-async` |

### Request (inputs)

| Change | Breaking? | Notes |
|---|---|---|
| Add an optional parameter or field whose default preserves old behavior | No | The default must reproduce exactly what clients got before |
| Add a required parameter or field | Yes | Make it optional with a safe default |
| Make an optional field required | Yes | |
| Remove or rename an accepted field | Yes | If the server now rejects it, clients fail loudly. If it's silently ignored, clients believe they set something they didn't (silent). |
| Change a field's type or format (integer to string, date to date-time, ID format) | Yes | Add a new field |
| Tighten validation (shorter max length, narrower pattern, smaller range, fewer accepted enum values, stricter Unicode or whitespace handling) | Yes (silent) | Check production traffic and stored data first. Existing clients and existing records may already violate the new rule. |
| Loosen validation | Usually no | Downstream consumers of the stored data, such as reports, exports, and other services, may break |
| Change the default of an optional parameter (page size, sort, a boolean flag, a status filter) | Yes (silent) | Declare every default in the spec so a differ can see it, and promote the default-change checks (section 4). Defaults that exist only in code stay invisible to tools. |
| Change case sensitivity, trimming, or normalization of inputs | Yes (silent) | |
| Lower the maximum page size, body size, or batch size | Yes | |

### Response (outputs)

| Change | Breaking? | Notes |
|---|---|---|
| Add a read-only field | No | Yes for strict clients if the tolerant-reader contract wasn't published |
| Add a writable field to a resource that clients update with PUT | Yes (silent) | Old typed clients GET, deserialize into a model that drops the unknown field, then PUT, and replace semantics reset the new field to its default or null. Prefer PATCH for updates, make the field ignored by PUT and settable through a dedicated operation, or ship it in a new version. |
| Relax a response constraint (larger `maxLength`, `maximum`, or `maxItems`, int32 to int64, a new string format variant) | Yes (often silent) | Clients store values in sized columns or validate responses against the old bound. Recent oasdiff versions flag some of these as errors, but not all. |
| Remove or rename a field | Yes | Add the new name, keep the old one, deprecate it |
| Change a field's type, format, units, precision, or scale | Yes | For example, cents to dollars, a seconds-to-milliseconds timestamp, a number to a string |
| Make a non-null field nullable, or make a guaranteed field optional | Yes | Clients dereference it without checking |
| Make a nullable field non-null | No | |
| Add an enum value | Treat as yes unless the enum was documented as open | Announce it ahead of time, even when it's documented as open |
| Change what an existing value means (for example, `closed` now also covers `archived`) | Yes (silent) | The worst kind. Add a new value instead. |
| Change default ordering, page size, or which items a default filter includes | Yes (silent) | |
| Change the pagination style or cursor semantics | Yes | |
| Wrap or unwrap the response envelope | Yes | |
| Change ID format or length | Yes | Clients validate IDs, store them in sized columns, and parse them despite being told not to |
| Remove or change a response header that clients read (`Location`, `ETag`, rate-limit headers) | Yes | |

### Status codes and errors

| Change | Breaking? | Notes |
|---|---|---|
| Change a success code (200 to 201, 201 to 200, 200 to 204) | Yes | Clients check for an exact code more often than you'd expect |
| A request that used to succeed now fails (new validation or a new precondition) | Yes | This is tightening (see Request) |
| Add a problem type for a new condition on a new field or feature | No | |
| Change the `type` URI, status, or extension members of an existing problem type | Yes | Clients branch on `type` |
| Change an error's status class (4xx to 5xx or back) | Yes | It changes retry behavior in client libraries |
| Return 410 after an announced sunset | Expected | That's the end of the deprecation process, not a surprise |

### Behavior and side effects

| Change | Breaking? | Notes |
|---|---|---|
| New side effect on an existing call (sends an email, charges, emits webhooks, notifies a third party) | Yes (silent) | Make it opt-in |
| Change idempotency or retry semantics | Yes (silent) | |
| Weaken consistency (read-your-writes lost after moving reads to a replica or cache) | Yes (silent) | |
| Tighter rate limits or quotas | Effectively yes | Announce, and give per-client notice when someone will start hitting the new limit |
| Change authorization so callers see more or fewer objects | Yes | Fewer breaks their workflows. More may be a security bug. Review both directions. |
| Latency regression beyond a published SLO | Contract-adjacent | Clients size their timeouts against it |

### Events and webhooks

| Change | Breaking? | Notes |
|---|---|---|
| Add an event type | No if subscriptions are per type; announce it if consumers can subscribe to "all" | |
| Remove an event type, or remove or rename payload fields | Yes | Same rules as responses |
| Change the signature scheme, secret format, or signed content | Yes | Send old and new signatures in parallel during the migration (webhooks.md) |
| Change delivery guarantees, such as retry duration or ordering assumptions | Yes (silent) | |

For protobuf/gRPC and GraphQL-specific compatibility rules (field numbers, `reserved`, nullability in SDL), see graphql-grpc.md.

## 4. Review procedure

1. **Get the base and head contracts** (SKILL.md step 2B). In a code-first project, regenerate the spec on both commits. Reading handler code alone misses serializer and validation changes.
2. **Run the linter and the structural differ** and record the output verbatim in the report. Use the project's own commands first. If it defines none, these are fallbacks. Each one downloads a tool (`npx` fetches packages; oasdiff and buf are standalone binaries), so ask before running any that isn't already a project dependency.

   | Contract | Lint | Breaking-change diff |
   |---|---|---|
   | OpenAPI | `npx @redocly/cli lint openapi.yaml` (defaults to its `recommended` ruleset). Spectral also works but needs a `.spectral.yaml` containing `extends: spectral:oas` in the working directory. | `oasdiff breaking --fail-on ERR "$BASE_SPEC" openapi.yaml` (base spec first; exits 1 on ERR-level breaks) |
   | Protobuf | `buf lint` | `buf breaking --against '.git#branch=main'` (needs a local `main` branch, so fetch it first in shallow CI clones) |
   | GraphQL | the project's schema linter | `npx @graphql-inspector/cli diff old.graphql new.graphql` (accepts `git:origin/main:schema.graphql` as a source) |

   Treat ERR-level results as breaking until proven otherwise. Read WARN-level results and decide on each one. oasdiff classifies changed defaults as INFO, so `--fail-on ERR` ignores them. To make CI catch them, promote those checks with a severity file and pass it with `--severity-levels severity.txt`:
   ```text
   request-parameter-default-value-changed err
   request-property-default-value-changed err
   request-body-default-value-changed err
   ```
   Run `oasdiff checks` to see every check ID and its default level for your installed version.
3. **Walk the tables above** for every changed operation, with particular attention to the rows marked silent. Look at the code paths too: defaults, validators, serializers, authorization filters, and sort clauses.
4. **Find the consumers.** Search this repository (frontends, SDKs, other services) for the field, path, or enum value: `git grep -n 'field_name'`. If request logs, API analytics, or gateway metrics exist, check actual usage of the affected field or parameter for each client. "Nobody uses it" needs evidence.
5. **Decide**:
   - Additive → ship it.
   - Breaking, and every consumer is internal, known, and deploys on your schedule → expand, migrate, contract (section 5), with named owners and dates.
   - Breaking, with external or slow-upgrading consumers (mobile apps, partners, public clients) → redesign it as additive, or ship it in a new version (section 6) with a deprecation plan (section 7).

## 5. Shipping a necessary break: expand, migrate, contract

1. **Expand.** Add the new field, endpoint, or behavior alongside the old one, with both working. Old and new representations must stay consistent: write both, or derive one from the other.
2. **Migrate.** Update consumers. Mark the old element `deprecated: true` in the spec, send `Deprecation` and `Sunset` headers on responses that use it, publish a changelog entry and a migration guide, and track usage of the old element per client.
3. **Contract.** After the sunset date, and once usage is zero or explicitly accepted, remove the old element. A removed endpoint returns 410 with a Problem Details body linking to the migration guide.

Optional: run scheduled brownouts (brief, announced periods where the deprecated element returns errors) before final removal, to flush out consumers who missed the announcements.

## 6. Versioning strategies

| Strategy | Example | Strengths | Costs |
|---|---|---|---|
| Major version in the URI | `/v1/orders` | Visible in logs and links, simple routing and caching, easy to try in a browser | Coarse-grained. Tempts big-bang rewrites. |
| Version header or media-type parameter | `Accept: application/vnd.example+json; version=2`, or a custom version header | Clean URLs, versions can evolve per resource | Invisible in links and logs, harder to test by hand, caches need `Vary` |
| Date-pinned versions | Custom header such as `Api-Version: 2026-10-01`, with each account pinned to the version it first used | Fine-grained, and clients upgrade when they choose | Needs a request and response transformation layer for every change, which is a real operating cost |
| Query parameter | `?api-version=2` | Easy to add | Easy to forget, and it pollutes cache keys |

Guidance:
- Pick one strategy per API and apply it to every endpoint. Never version endpoints independently.
- Evolve additively inside a major version. A new major version should be rare, and it's a product event with a migration guide, not a refactoring tool.
- Publish a support policy, such as a minimum window between a successor's release and the old version's sunset, and keep the number of live versions small. Every live version is code you have to secure and test.
- Internal APIs whose consumers all deploy with you can often skip versions and use expand, migrate, contract instead.
- Record the chosen strategy as an ADR (with `workflow:adr-writer`, if it's installed).

## 7. Deprecation and sunset

```http
Deprecation: @1767225600
Sunset: Thu, 01 Jul 2027 00:00:00 GMT
Link: <https://developer.example.com/deprecations/orders-v1>; rel="deprecation"; type="text/html"
```

- **`Deprecation` (RFC 9745, March 2025)** is a Structured Field Date: `@` followed by Unix seconds. The example above is 2026-01-01T00:00:00Z. The date can be in the past (already deprecated) or the future (will be deprecated). `Deprecation: true` is wrong. That boolean form came from an earlier draft.
- **`Sunset` (RFC 8594)** is an HTTP-date giving when the resource is expected to stop responding. RFC 9745 requires that it be no earlier than the `Deprecation` date. RFC 8594 also defines `rel="sunset"` for links.
- **`Link` with `rel="deprecation"`** points to human-readable migration documentation.
- Deprecation headers are informational. A deprecated endpoint keeps behaving exactly as before until it's removed.
- Mark the element deprecated in the contract as well: OpenAPI `deprecated: true` on operations, parameters, and schema properties, protobuf `[deprecated = true]`, GraphQL `@deprecated(reason: "...")`.
- Communicate through every channel clients read (changelog, email to registered developers, dashboards showing each client's deprecated usage), and contact the remaining callers directly before the sunset date.
