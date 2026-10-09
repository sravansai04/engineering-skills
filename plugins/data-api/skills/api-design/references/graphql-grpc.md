# GraphQL and gRPC

Read this when the contract is GraphQL SDL or protobuf. Many of the principles in SKILL.md carry over unchanged: model resources rather than storage, authorize every object, paginate every list, treat money and time carefully, and evolve additively. This file covers what is different.

Specification status last verified 2026-10. GraphQL spec editions and the GraphQL-over-HTTP draft change; check graphql.org and spec.graphql.org before citing them.

## Contents

1. GraphQL: schema design
2. GraphQL: errors and HTTP
3. GraphQL: security and performance
4. GraphQL: evolution
5. gRPC and protobuf: design
6. gRPC: errors, deadlines, retries
7. Protobuf: compatibility rules

---

## 1. GraphQL: schema design

- **Design the schema around client use cases, not around tables.** Expose domain types and relationships, and don't mirror the database.
- **Nullability is a compatibility decision.** In output types, a non-null field that fails to resolve nulls out its parent, and the null keeps propagating up to the nearest nullable field. Make a field non-null only when it's truly guaranteed. Later changing an output field from non-null to nullable breaks clients. Changing it from nullable to non-null is safe.
- **Mutations take a single `input` argument and return a payload type**: `createInvoice(input: CreateInvoiceInput!): CreateInvoicePayload!`. Both can gain fields later without breaking anyone.
- **Put expected business errors in the schema, not the top-level `errors` array.** Model them as a union result (`union CreateInvoiceResult = Invoice | ValidationError | CreditLimitExceeded`) or as a `userErrors: [UserError!]!` field on the payload. Top-level `errors` is for exceptional failures: parse and validation errors, authorization failures, and bugs.
- **Mutually exclusive inputs**: use OneOf input objects (`@oneOf`, part of the GraphQL specification since its September 2025 edition) where your server library supports them. Exactly one field must be set.
- **Pagination**: use cursor connections (`first` / `after`, `edges { node cursor }`, `pageInfo { hasNextPage endCursor }`). Cap `first` on the server.
- **IDs**: use globally unique, opaque `ID`s so clients can cache and refetch by ID.
- **Custom scalars** for `DateTime`, `Date`, `Decimal` or `Money`, and `URL` make the format explicit. Document each one's serialization (RFC 3339, decimal string) as you would for REST.

## 2. GraphQL: errors and HTTP

- How status codes are used for GraphQL over HTTP is still settling. The GraphQL-over-HTTP specification is a working draft, and its rules have changed between revisions. That includes the `application/graphql-response+json` media type, and how request errors and partial results are reported. Follow whatever behavior your server library implements for the media types it negotiates. Don't hand-roll status logic. Make sure clients send `Accept: application/graphql-response+json, application/json`.
- Put a machine-readable code in `errors[].extensions` (for example, `extensions.code`), and treat those codes as part of the contract, like Problem Details `type` URIs.
- Never return stack traces or resolver internals in `errors[].message` in production.

## 3. GraphQL: security and performance

- **Authorize in the business layer that every resolver goes through, not in the gateway.** Every field that loads an object by ID, including nested fields reached through relationships, needs the same object-level check as a REST `/{id}` route. A query can reach an object through many paths. An authorization check on one of them is no check at all.
- **Bound query cost.** Set a maximum depth, a maximum page size for every connection, and a complexity or cost budget per operation. Rate-limit by *cost*, not request count: a single request can batch hundreds of operations through aliases.
- **Trusted documents (persisted queries)** for first-party clients let the server reject arbitrary queries in production. Make a deliberate decision about introspection on public endpoints. It isn't a security boundary, but it does make reconnaissance easier.
- **N+1 queries**: batch loads per request with a DataLoader-style batching layer. For a deeper pass, use `review-suite:performance-review` if it's installed.

## 4. GraphQL: evolution

GraphQL APIs usually evolve continuously instead of shipping numbered versions.
- Add fields, types, and optional arguments freely.
- Deprecate with `@deprecated(reason: "Use totalAmount")`. The September 2025 spec edition allows it on arguments and input fields as well as on fields and enum values, but check your server library's support. Remove a deprecated element only after field-usage telemetry shows no remaining callers. Collecting per-field usage metrics is what makes this possible.
- Breaking: removing a field or type, changing a field's type, adding a required argument or required input field, making an argument or input field non-null, making an output field nullable, and removing an enum value. Adding an enum value is "dangerous": clients that switch over every case can break.
- Diff in CI: `npx @graphql-inspector/cli diff 'git:origin/main:schema.graphql' schema.graphql` classifies changes as breaking, dangerous, or safe.

## 5. gRPC and protobuf: design

Google's public API Improvement Proposals (AIPs, at google.aip.dev) are a widely used, detailed style guide for resource-oriented gRPC APIs. The most useful ones:

| Topic | AIP | Gist |
|---|---|---|
| Resource-oriented design, resource names | 121, 122 | Model resources with hierarchical names (`publishers/123/books/456`) |
| Standard methods | 131–135 | `Get`, `List`, `Create`, `Update`, `Delete` with conventional request and response shapes |
| Long-running operations | 151 | Return a `google.longrunning.Operation` for slow work |
| Request identification | 155 | Client-supplied `request_id` (a UUID) for idempotent retries |
| Pagination | 158 | `page_size`, `page_token`, `next_page_token`. Tokens are opaque. |
| Filtering | 160 | A documented `filter` string grammar |
| Partial update | 134, 161 | `Update` takes a `google.protobuf.FieldMask` naming the fields to change, which is the gRPC counterpart of PATCH |
| Errors | 193 | `google.rpc.Status` with structured details (`ErrorInfo`, `BadRequest`) |
| Backwards compatibility | 180 | What counts as a breaking change |

Additional rules:
- **Field presence.** In proto3, scalar fields without `optional` can't distinguish "unset" from the zero value (`0`, `""`, `false`). Use `optional` (or wrapper types) where unset must be distinguishable, and use field masks for updates.
- **Enums.** The first value is `{ENUM_NAME}_UNSPECIFIED = 0`. Prefix every value with the enum name, because proto3 enum values share their enclosing scope. Receivers must handle unknown values, which proto3 preserves as their numeric value.
- **Money and time.** Use well-known or common types: `google.protobuf.Timestamp` and `google.protobuf.Duration` for time, and `google.type.Money` or a decimal string for currency. Never use `double` for money.
- **Streaming** is for genuinely incremental data (feeds, large result sets, bidirectional sessions). Design for resumption with a token, because long-lived streams get cut.

## 6. gRPC: errors, deadlines, retries

Use the canonical status codes precisely. Client retry behavior depends on them.

| Code | Use for | Rough HTTP analog |
|---|---|---|
| `INVALID_ARGUMENT` | Bad input regardless of system state | 400 |
| `FAILED_PRECONDITION` | System isn't in the required state (for example, a non-empty directory); don't retry until the state changes | 400 |
| `OUT_OF_RANGE` | Valid type, but past the valid range (for example, reading past the end) | 400 |
| `UNAUTHENTICATED` | No valid credentials | 401 |
| `PERMISSION_DENIED` | Identity known, not allowed | 403 |
| `NOT_FOUND` | Missing, or hidden from the caller | 404 |
| `ALREADY_EXISTS` | Create conflicts with an existing resource | 409 |
| `ABORTED` | Concurrency conflict, such as an optimistic-lock or transaction abort; retry the whole read-modify-write | 409 |
| `RESOURCE_EXHAUSTED` | Quota or rate limit | 429 |
| `UNAVAILABLE` | Transient; retry with backoff only if the call is idempotent or carries a `request_id` (AIP-155), because the server may have processed it before the connection dropped | 503 |
| `DEADLINE_EXCEEDED` | Deadline passed (the operation may still have completed) | 504 |
| `UNIMPLEMENTED` | Method not supported | 501 |
| `INTERNAL` | Invariant broken or a bug | 500 |

- **Every call has a deadline.** Clients set one, and servers propagate the remaining budget to their own downstream calls. A call without a deadline can hang forever and pin resources.
- **Retry only idempotent calls**, or calls made idempotent with a `request_id` (AIP-155). Configure retries through the client's retry policy, with backoff, rather than with ad hoc loops.
- **Use structured error details** (`BadRequest.field_violations`, `ErrorInfo.reason` plus `domain`) so clients can act without parsing messages. Treat the reason strings as part of the contract.

## 7. Protobuf: compatibility rules

The wire format identifies fields by **number**, while JSON transcoding and generated code identify them by **name**. Both are part of the contract.
- **Never reuse or renumber a field.** When you remove a field, `reserved` both its number and its name so nobody reuses them by accident:
  ```proto
  message Invoice {
    reserved 4;
    reserved "legacy_total";
    string id = 1;
    google.type.Money total = 5;
  }
  ```
- **Renaming a field** is wire-compatible but breaks JSON mapping, generated code, and field masks. Treat it as breaking.
- **Changing a field's type** is breaking, apart from a few wire-compatible integer pairs, and even those can silently truncate. Treat every type change as breaking.
- Moving an existing field into or out of a `oneof`, changing `repeated` versus singular, or changing a package, service, or method name are all breaking.
- **Adding** fields, messages, methods, or enum values is wire-safe. Receivers still need to tolerate unknown enum values.
- **CI check**: `buf breaking --against '.git#branch=main'` compares against the base branch. Shallow CI clones need the base branch fetched first, or use a remote reference such as `https://github.com/ORG/REPO.git#branch=main`. Lint with `buf lint`.
