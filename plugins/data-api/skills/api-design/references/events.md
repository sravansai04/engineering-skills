# Event and message contracts

Read this when a change publishes or consumes messages through a broker or queue (Kafka, RabbitMQ, Amazon SNS and SQS, Google Pub/Sub, NATS, and similar), or defines an event schema. Webhooks to customer URLs are in `webhooks.md`; this file covers events between services. An event schema is an API whose consumers you often can't list, and whose old messages may be replayed months later, so the compatibility bar is higher than for a request and response.

## Contents

1. The envelope
2. Thin or fat events
3. Compatibility rules
4. Schema registries and upgrade order
5. Keys, partitions, and ordering
6. Delivery: at least once, idempotent consumers
7. Retention and replay
8. AsyncAPI as the contract source
9. Review checklist

---

## 1. The envelope

Put the same metadata on every event, separate from the payload, so routing, dedup, and tracing never depend on parsing `data`:

```json
{
  "id": "0b6f2d1e-6f0a-4c2e-9f57-3d1f2a6c9b10",
  "type": "billing.invoice.paid",
  "source": "/billing/invoices",
  "specversion": "1.0",
  "dataschema": "https://schemas.example.com/billing/invoice-paid/2",
  "subject": "inv_42",
  "time": "2026-10-09T14:03:00Z",
  "datacontenttype": "application/json",
  "data": {"invoice_id": "inv_42", "amount_paid": "120.00", "currency": "USD", "version": 7}
}
```

- **`id`**: unique per event and identical on every redelivery. Consumers dedup on it.
- **`type`**: namespaced and past tense. It names a fact that happened, not a command.
- **Schema version**: carried in the envelope (`dataschema`, or a `schema_version` field), never inferred from the payload's shape.
- **`time`**: when the fact happened (RFC 3339, UTC), which can differ from when it was published. Say which one the field means.
- **Producer and subject**: who emitted it and which entity it is about, plus correlation and causation IDs if the platform traces across services.

The example uses the CloudEvents 1.0 attribute names (`id`, `source`, `specversion`, and `type` are required; the rest are optional). Follow the house envelope if one exists; otherwise CloudEvents is a reasonable default with SDKs and broker bindings.

## 2. Thin or fat events

- **Thin (notification):** IDs and the minimum to route, and consumers fetch current state. The payload rarely changes, so compatibility is easy, but every consumer calls back, and a fetched state may already be newer than the event.
- **Fat (event-carried state):** the relevant state at the time of the event. Consumers don't call back, but the payload is a wide contract, and it may carry personal data into every downstream store and log.

Pick one per event type on purpose and write the reason down. Include a per-entity `version` or sequence number either way, so a consumer can discard a stale event.

## 3. Compatibility rules

- **Add, never change.** New optional fields are safe. Renaming a field, changing its type or unit, or changing what it means breaks consumers, often silently.
- **Never reuse a name or number.** A removed field's name (JSON, Avro) or field number (protobuf, where you also `reserved` both) stays retired forever, because old messages and old consumers still use it.
- **Tolerant readers.** Consumers ignore unknown fields and unknown enum values. A consumer that validates with `additionalProperties: false`, or switches exhaustively over an enum, turns every additive change into an outage. Document enums as open.
- **Defaults make additions safe in Avro.** A field added without a default can't be read from old data. Removing a field that has no default breaks readers that still expect it.
- **Required is forever.** Making a field required later breaks producers that don't send it; making a required field optional breaks consumers that rely on it. Prefer optional with a documented default.
- **A real break gets a new type or topic.** Publish `invoice.paid.v2` (or to a new topic) alongside the old one, migrate consumers, measure, then stop the old one. Don't change a type in place.

## 4. Schema registries and upgrade order

A schema registry (Confluent Schema Registry, AWS Glue Schema Registry, Apicurio, and others) rejects a new schema version that breaks the subject's compatibility mode. Know the mode, because it decides who upgrades first:

| Mode | Guarantee | Deploy first |
|---|---|---|
| `BACKWARD` | Consumers on the new schema can read data written with the previous one | Consumers |
| `FORWARD` | Consumers on the previous schema can read data written with the new one | Producers |
| `FULL` | Both of the above | Either |
| `*_TRANSITIVE` | The same check against every earlier version, not only the latest | As above |
| `NONE` | No check | Treat every change as breaking |

Use a transitive mode when consumers may read old data (long retention, replays, compacted topics). Run the registry's compatibility check in CI before merge, for example Confluent's `POST /compatibility/subjects/{subject}/versions/latest`, rather than finding out at deploy time.

## 5. Keys, partitions, and ordering

- **Ordering holds only within a partition or group.** Kafka orders per partition, SQS FIFO per `MessageGroupId`, Pub/Sub per ordering key. Nothing is ordered across them.
- **Key by the entity whose events must stay in order**, usually the aggregate ID (order, account). Keying by something coarser creates hot partitions; keying by something finer loses the ordering you needed.
- **Changing the partition count remaps keys** under hash-based partitioning, so events for one entity can be processed out of order across the change. Plan it like a migration.
- **Consumers still guard against reordering.** Retries, redeliveries, and multiple producers reorder events anyway. Apply an event only if its `version` is newer than the stored one.

## 6. Delivery: at least once, idempotent consumers

- **Assume at-least-once delivery.** Make every consumer idempotent: dedup on the event `id` with a unique constraint, or make the effect itself idempotent (an upsert guarded by version). "Exactly once" features are scoped; Kafka transactions, for example, cover read-process-write within Kafka, not a side effect in your database or a third-party call.
- **Publish with the state change, not after it.** Writing to the database and then publishing is a dual write: a crash in between loses the event or publishes one for a rolled-back change. Use a transactional outbox (or change data capture) so the event commits with the data.
- **Bound retries and dead-letter the rest.** A poison message must not block its partition forever. Retry with backoff a fixed number of times, then move it to a dead-letter queue with an alert and a replay tool.

## 7. Retention and replay

- Consumers must read every schema version still inside retention, and every version a replay or a backfill might feed them.
- On compacted topics the latest value per key is kept indefinitely, so a "temporary" schema can live for years. A tombstone (null value) deletes a key; consumers must handle it.
- Personal data in events lasts as long as retention and every downstream copy. Keep it out of fat events unless the consumers truly need it, or plan how a deletion request reaches them.

## 8. AsyncAPI as the contract source

AsyncAPI (version 3.x) describes channels, the operations an application sends or receives, and message payloads, with schemas in JSON Schema, Avro, or protobuf. Treat it like OpenAPI: keep it next to the code, validate it in CI with the AsyncAPI CLI (`asyncapi validate`), review its diff on every contract change, and generate or check producer and consumer types from it. If the project has a schema registry, the registry's compatibility check is the gate and the AsyncAPI document is the description; make sure they reference the same schemas.

## 9. Review checklist

- [ ] Every event has an envelope with a stable `id`, a past-tense `type`, a schema version, an occurred-at time, and the producer.
- [ ] The change is additive, or it ships as a new type or topic with a consumer migration plan.
- [ ] The registry compatibility mode is known, the check runs in CI, and the deploy order matches the mode.
- [ ] The partition or ordering key is the entity that needs ordering, and consumers discard stale versions.
- [ ] Consumers are idempotent on the event `id`; publishing goes through an outbox, not a dual write.
- [ ] Retries are bounded and failures land in a dead-letter queue someone is alerted on.
- [ ] Old versions inside retention can still be read, and personal data in payloads is justified.
