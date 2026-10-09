# Webhooks

Read this when the API sends events to customer-supplied URLs, or when you're reviewing code that receives them. A webhook is a reverse API: you are the client and the receiver is the server, and every reliability problem from the normal direction shows up again here.

## Contents

1. Event design
2. Signing
3. Verifying (receiver side), with Python and TypeScript examples
4. Delivery and retries (sender side)
5. Receiver rules: dedup, ordering, fast ack
6. Delivering to customer URLs safely (SSRF)
7. Review checklist

---

## 1. Event design

```json
{
  "id": "evt_01JA9C2X4T",
  "type": "invoice.paid",
  "created_at": "2026-10-09T14:03:00Z",
  "api_version": "2026-10-01",
  "data": {"object": {"id": "inv_42", "status": "paid", "amount_due": "0.00", "currency": "USD"}}
}
```

- `id` is unique per event and **stays the same across retries**. It's the receiver's dedup key.
- `type` is namespaced and past tense (`resource.verb_past`), drawn from a documented catalog. Let customers subscribe per type.
- `created_at` is when the event happened, not when this delivery attempt was made.
- `api_version` identifies the payload schema. Payloads follow the same compatibility rules as responses (breaking-change-checklist.md).
- **Thin versus full payloads.** A thin event (`type` plus the resource `id`, with the receiver fetching current state through the API) avoids stale data, sidesteps ordering problems, keeps personal data off the wire, and re-applies authorization at fetch time. A full snapshot is more convenient but goes stale and may carry sensitive fields to an endpoint you don't control. Default to thin, or to a minimal snapshot, for sensitive domains.

## 2. Signing

Receivers need to know that a request came from you, wasn't modified, and isn't a replay.

- **Sign the raw body together with a delivery timestamp and the event ID.** The Standard Webhooks specification (an open, vendor-neutral spec) signs `{webhook-id}.{webhook-timestamp}.{body}` with HMAC-SHA256 and sends three headers: `webhook-id`, `webhook-timestamp` (Unix seconds), and `webhook-signature` (`v1,` plus a base64 signature). Adopting an existing scheme means receivers can use off-the-shelf libraries. HTTP Message Signatures (RFC 9421) is a standards-track alternative when you need asymmetric keys or want to sign selected headers.
- **Put the timestamp inside the signed content.** If it isn't signed, an attacker can replay a captured request with a fresh timestamp.
- **Use per-endpoint secrets** with high entropy (Standard Webhooks specifies 24 to 64 random bytes). Show the secret once, and let customers roll it.
- **Support rotation without downtime.** During a rotation, send signatures from both the old and new secrets (space-separated in `webhook-signature`), and expire the old secret after a grace period.
- **Asymmetric signing** (for example, ed25519) lets receivers verify with a public key, so a leaked receiver can't forge events. It's worth considering for high-value events.

## 3. Verifying (receiver side)

Verify **before** parsing, using the exact bytes received. Re-serializing parsed JSON changes whitespace and key order, and the signature check then fails, or worse, gets skipped. Compare in constant time, and reject timestamps outside a tolerance window. Five minutes is a common default, and the spec leaves the exact value to you.

Python (3.9+):
```python
import base64, hashlib, hmac, time

def verify_webhook(secret: str, headers, raw_body: bytes, tolerance_s: int = 300) -> bool:
    """Standard Webhooks-style HMAC-SHA256 check. `headers` must be case-insensitive."""
    msg_id = headers.get("webhook-id")
    ts = headers.get("webhook-timestamp")
    sig_header = headers.get("webhook-signature")
    # isdigit() alone accepts non-ASCII digits such as "²", which int() then rejects;
    # the length cap also keeps int() away from its huge-string limit.
    if not (msg_id and ts and sig_header and len(ts) <= 12 and ts.isascii() and ts.isdigit()):
        return False
    if abs(time.time() - int(ts)) > tolerance_s:  # replay window
        return False
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = f"{msg_id}.{ts}.".encode() + raw_body  # raw bytes, never re-serialized JSON
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest())
    for candidate in sig_header.split(" "):  # several signatures during secret rotation
        version, _, value = candidate.partition(",")
        if version == "v1" and hmac.compare_digest(value.encode(), expected):
            return True
    return False
```

TypeScript (Node.js):
```ts
import { createHmac, timingSafeEqual } from "node:crypto";

export function verifyWebhook(
  secret: string,
  headers: Record<string, string | undefined>, // lower-cased header names
  rawBody: Buffer,                             // the exact bytes received
  toleranceSec = 300,
): boolean {
  const id = headers["webhook-id"];
  const ts = headers["webhook-timestamp"];
  const sigHeader = headers["webhook-signature"];
  if (!id || !ts || !sigHeader || !/^\d+$/.test(ts)) return false;
  if (Math.abs(Date.now() / 1000 - Number(ts)) > toleranceSec) return false;

  const key = Buffer.from(secret.replace(/^whsec_/, ""), "base64");
  const expected = createHmac("sha256", key).update(`${id}.${ts}.`).update(rawBody).digest();

  return sigHeader.split(" ").some((candidate) => {
    const [version, value] = candidate.split(",", 2);
    if (version !== "v1" || !value) return false;
    const given = Buffer.from(value, "base64");
    return given.length === expected.length && timingSafeEqual(given, expected);
  });
}
```

Notes:
- The secret is used as **base64-decoded bytes**, not as the literal `whsec_...` string. Getting this wrong is the most common verification bug.
- In web frameworks, capture the raw body before any JSON middleware consumes it. Most frameworks have a raw-body option for exactly this.
- Prefer the official Standard Webhooks library for your language if the project allows the dependency. These snippets show what such a library does.

## 4. Delivery and retries (sender side)

- **At-least-once delivery.** Treat any 2xx as success. Anything else, including timeouts and connection errors, gets retried with exponential backoff and jitter over a documented schedule (commonly hours to a few days).
- **Short timeouts** (a few seconds) for each attempt. A slow receiver must not tie up your delivery workers.
- **Decouple delivery from the business transaction.** Write the event to an outbox table in the same transaction as the state change, and deliver it from a worker. Sending inside the request either drops events when the send fails, or sends events for transactions that later roll back.
- **Disable endpoints that fail consistently**, notify the owner, and provide a way to list and redeliver failed events (dashboard or API). Receivers will lose events during their own outages and need a way to backfill.
- **Treat redirects as failures rather than following them,** and ask the owner to update the URL. Following a redirect to an attacker-chosen location is an SSRF bypass (section 6).
- **Separate per-endpoint queues** so one dead receiver can't delay everyone else's deliveries.

## 5. Receiver rules: dedup, ordering, fast ack

Document these for your customers, and apply them when your own code consumes webhooks:
- **Deduplicate on the event `id`** using a unique constraint (`INSERT ... ON CONFLICT DO NOTHING`, or the equivalent). Retries and redeliveries are normal, not an error case.
- **Don't assume order.** Event B can arrive before event A. Compare a version or `created_at` against stored state, or simply re-fetch the resource's current state (the thin-event pattern), before acting.
- **Acknowledge fast.** Verify the signature, persist or enqueue the event, return 2xx, and process it asynchronously. Slow handlers cause timeouts, which cause retries, which cause duplicate work.
- **Return 2xx for event types you don't handle.** A 4xx makes the sender retry an event you'll never want.

## 6. Delivering to customer URLs safely (SSRF)

Sending HTTP requests to URLs that customers configure is textbook server-side request forgery (OWASP API7:2023).
- Require `https` and a public DNS name. Reject IP literals, `localhost`, and internal suffixes.
- **Check the resolved IP at connection time, not only at registration.** Block private, loopback, link-local (including cloud metadata addresses such as 169.254.169.254), and unique-local ranges, for both IPv4 and IPv6. Checking only at registration is defeated by DNS rebinding.
- Send from an egress proxy or network segment that has no route to internal services.
- Don't follow redirects, and don't show response bodies to the customer verbatim. Echoing a response body turns blind SSRF into data exfiltration.
- Cap response size and request duration.

## 7. Review checklist

- [ ] The event has a unique, retry-stable `id`, a namespaced `type`, `created_at`, and a schema version.
- [ ] The signature covers ID, timestamp, and raw body. Verification is constant-time, enforces a tolerance window, and supports multiple signatures for rotation.
- [ ] The outbox pattern (or an equivalent) ties emission to the committed state change.
- [ ] Retries use backoff and jitter on a documented schedule, failing endpoints get disabled with a notification, and redelivery exists.
- [ ] Receivers dedupe on event ID, tolerate reordering, ack quickly, and ignore unknown types with a 2xx.
- [ ] Outbound delivery is protected against SSRF: resolved-IP checks on every connection, no redirects, an egress proxy, and size and time caps.
- [ ] Payloads leave out data the subscriber isn't authorized to see. Authorization is evaluated at emit time or, for thin events, at fetch time.
