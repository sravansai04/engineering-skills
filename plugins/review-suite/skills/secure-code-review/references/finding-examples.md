# Calibration Examples

Worked examples of the Step 6 decision (report, mark Likely, demote to hardening, or rule out) and the Step 7 rating. Each one shows the reasoning, which is the part worth copying.

## Contents

1. Ruled out: SQL built by string formatting from a constant (Python)
2. Likely: SSRF behind a hostname check (Go)
3. Confirmed: race condition on coupon redemption (Java/SQL)
4. Confirmed: stored XSS that executes for admins (TypeScript/React)
5. Confirmed: JWT algorithm taken from the token (Node)
6. Hardening: vulnerable dependency, unreachable function
7. Ruled out vs Confirmed: the same mass-assignment pattern in two places (Ruby)

---

## 1. Ruled out: SQL built by string formatting from a constant (Python)

```python
TABLES = {"daily": "metrics_daily", "hourly": "metrics_hourly"}

def load(granularity: str, since: date):
    table = TABLES[granularity]          # KeyError for anything else
    return db.execute(f"SELECT * FROM {table} WHERE ts >= %s", (since,))
```

- A scanner flags "SQL built with f-string". Tracing shows `table` can only be one of two hard-coded values, because the dict lookup *is* an allowlist. `since` is bound as a parameter.
- Condition 2 (attacker-controlled) fails for the interpolated part.
- **Report as:** Ruled out. "`metrics.py:12` f-string SQL: identifier comes from a fixed allowlist map; value is bound." Then check whether an unhandled `KeyError` turns into a 500 with a stack trace. That would be a separate, small A10 hardening note.

## 2. Likely: SSRF behind a hostname check (Go)

```go
func registerWebhook(w http.ResponseWriter, r *http.Request) {
    u, err := url.Parse(r.FormValue("url"))
    if err != nil || isInternalHost(u.Hostname()) { http.Error(w, "bad url", 400); return }
    // later, from a worker:
    resp, err := http.Post(u.String(), "application/json", body)
```

`isInternalHost` resolves the name once and checks the IPs against private ranges.

- **Reachable and controlled:** any account can register a webhook. Confirmed from the router.
- **Not neutralized?** The check resolves DNS at registration. The worker resolves again at delivery time, so a DNS-rebinding name passes the check and later points at `127.0.0.1` or the metadata service. `http.Post` uses the default client, which follows redirects, so a public URL that 302s to an internal one also works. Delivery responses are stored and shown in the "webhook log" UI, which makes the SSRF readable.
- **What's outside the code:** whether the workers have network egress filtering or a metadata endpoint that requires a session token.
- **Severity:** Likelihood Medium (any account can register a webhook, but the attack also needs an attacker-run redirecting or rebinding host, and egress that reaches internal ranges) × Impact High (readable responses from internal services; cloud credentials if the metadata endpoint answers plain GETs) → **High**.
- **Report as:** [high] Likely. Verify that worker egress to RFC 1918, loopback, and link-local ranges and to the cloud metadata endpoint is blocked at the network layer. If it is, downgrade to Medium, because services listening on the worker's own loopback interface stay reachable.
- **Fix:** validate the resolved IP inside a custom dialer (`net.Dialer.Control`) so the check covers the connection actually made. Disable redirects (`CheckRedirect` returning `http.ErrUseLastResponse`) or re-validate each hop. Set a timeout and a response-size cap. Store status codes, not bodies.

## 3. Confirmed: race condition on coupon redemption (Java/SQL)

```java
Coupon c = repo.findByCode(code);
if (c.isRedeemed()) throw new AlreadyRedeemed();
order.applyDiscount(c.getAmount());
c.setRedeemed(true);
repo.save(c);
```

- **Reachable:** checkout, any customer.
- **Controlled:** the attacker controls timing by sending parallel requests.
- **Not neutralized:** there's no row lock, no version column, and no conditional update. The default transaction isolation (read committed) doesn't stop two transactions from both reading `redeemed = false`.
- **Impact:** a single-use coupon gets applied N times, which is direct money loss.
- **Severity:** Likelihood Medium (any customer, needs concurrent requests, which is trivial to script) × Impact High (money) → **High**.
- **Fix:** an atomic claim. Run `UPDATE coupons SET redeemed = true WHERE code = :code AND redeemed = false` and proceed only if exactly one row changed. Alternatively, lock the row with `SELECT ... FOR UPDATE` inside the transaction.
- **Regression test:** fire 20 concurrent redemptions and assert exactly one succeeds.

## 4. Confirmed: stored XSS that executes for admins (TypeScript/React)

```tsx
// Admin support console
<div className="ticket-body" dangerouslySetInnerHTML={{ __html: ticket.bodyHtml }} />
```

`bodyHtml` is produced by a Markdown renderer on the server with raw HTML passthrough enabled. Customers write the ticket bodies.

- **Source to sink:** customer ticket text → Markdown with HTML allowed → stored → rendered as raw HTML in the admin console.
- **Not neutralized:** there's no sanitizer on either side. The app's CSP allows `'unsafe-inline'`.
- **Impact:** script runs in an admin's session. It can call admin APIs, such as changing user emails or issuing refunds.
- **Severity:** Likelihood High (any customer can open a ticket, and admins read tickets as routine work, which Step 7 counts as High rather than as luring a victim) × Impact High (admin session) → **Critical**.
- **Fix:** sanitize the rendered HTML with an allowlist sanitizer on the server, or disable raw HTML in the Markdown renderer. Defense in depth: a nonce-based CSP without `'unsafe-inline'`.

## 5. Confirmed: JWT algorithm taken from the token (Node)

```js
const header = JSON.parse(Buffer.from(token.split('.')[0], 'base64url'));
const key = header.alg.startsWith('HS') ? process.env.JWT_SECRET : publicKeyPem;
const claims = jwt.verify(token, key);   // no `algorithms` option
```

- The app's real tokens are RS256. An attacker takes the public key (published at the JWKS endpoint), signs a token with HS256 using the key bytes as the HMAC secret, and gets... nothing here, because this branch picks `JWT_SECRET` for HS tokens. Re-read before concluding. The confusion attack fails on this exact code.
- **But:** `JWT_SECRET` also signs the email-verification tokens. `POST /verify-email/request` takes a `userId` and an `email` from the caller, mints an HS256 token with `sub` set to that `userId`, and mails it to that address. An attacker requests one for a victim's `userId`, sends it to their own mailbox, and presents it as a session token. It passes `jwt.verify` here, because neither the algorithm, `aud`, nor `iss` is checked, and the session code reads `sub`.
- **Severity:** Likelihood High (any visitor, two ordinary requests, the victim's ID is all that's needed) × Impact High (signs in as any account) → **Critical**.
- **Report as:** [critical] Confirmed. Token-type confusion: an email-verification token is accepted as a session token, so anyone can sign in as any user. Pin `algorithms: ['RS256']` and check `aud`/`iss`. Use separate keys per token purpose. Separately, the request endpoint shouldn't mint a token for a `userId` the caller doesn't own.
- **The lesson:** validate the specific attack against the specific code. The textbook attack was blocked, and a different one worked.

## 6. Hardening: vulnerable dependency, unreachable function

The audit shows a high-severity advisory in an image library's TIFF decoder. The app uses the library only to resize PNG and JPEG avatars, and the upload handler rejects anything whose sniffed type isn't PNG or JPEG before decoding.

- **Report as:** Hardening. "Upgrade `imagelib` to the patched release. The vulnerable TIFF path isn't reachable today because uploads are restricted to PNG and JPEG by content sniffing (`upload.py:40`), but that restriction is the only barrier."
- If the type check trusted the file extension or the client's `Content-Type` instead of sniffing, the bug would be reachable, and this becomes a High finding.

## 7. Ruled out vs Confirmed: the same mass-assignment pattern in two places (Ruby)

```ruby
# app/controllers/profiles_controller.rb
def update
  current_user.update!(params.require(:user).permit(:name, :bio, :avatar))
end

# app/controllers/admin/users_controller.rb
before_action :require_admin!
def update
  User.find(params[:id]).update!(params.require(:user).permit!)
end
```

- **Profiles:** explicit permit list with no privileged attributes. Ruled out.
- **Admin:** `permit!` allows every attribute, but only admins reach it, and admins can already set any attribute through the UI. No privilege is gained, so this is hardening ("use an explicit permit list so a future sensitive column isn't silently writable").
- **It would become a finding if** a lower "support" role could also reach this controller (check `require_admin!`), or if the model has attributes even admins shouldn't set, such as `organization_id` or another user's `password_digest`.
