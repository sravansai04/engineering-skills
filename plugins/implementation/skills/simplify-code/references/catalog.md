# Simplification catalog: before/after with safety conditions

Each entry shows one small transformation, then the conditions under which it
is safe and the conditions under which it is not. The examples rotate across
languages; the reasoning carries over to any of them. Tier numbers refer to
the risk tiers in SKILL.md.

## Contents

1. Unused bindings and parameters
2. Unreachable and commented-out code
3. Duplication: reuse what exists
4. Single-implementation interfaces
5. Pass-through wrappers
6. Premature generalization and knobs that never vary
7. Deep nesting to guard clauses
8. Clever code to plain code
9. Redundant defensive checks
10. Error handling that swallows or repeats
11. Logging noise
12. Casts and type escapes
13. Fallbacks that hide bugs
14. Comments that restate the code
15. Naming that drifts from its neighbors

---

## Unused bindings and parameters

```python
# before
def close_period(ledger, period, notify=False):   # notify: no caller passes it
    result = audit.record("close", period)        # result never read
    import json                                   # never used
    return ledger.close(period)

# after
def close_period(ledger, period):
    audit.record("close", period)                 # the call stays: it has a side effect
    return ledger.close(period)
```

Safe when the function is private to the scope, or every caller is in the
scope and you update them in the same batch (tier 1).

Not safe when:
- The parameter is dictated by a shape: a callback signature, an interface
  method, a framework hook. Express decides a middleware is an error handler
  by its arity, so `(err, req, res, next)` must keep `next` even if unused;
  rename it with the local "intentionally unused" convention (`_next`, `_`)
  instead.
- The function is exported or public. Removing a parameter is a signature
  change (tier 3).
- The initializer has side effects. Drop the binding, keep the call.
- The binding is an import that runs code. In Python, Ruby, plain
  JavaScript, and TypeScript compiled with `verbatimModuleSyntax` or
  `preserveValueImports`, importing a module executes it, and the module may
  register ORM models, signal handlers, tasks, or plugins, or patch something
  (`import myapp.signals`, a polyfill). In an `__init__.py`, a module with
  `__all__`, or an index barrel, an import that looks unused is often a
  re-export. Keep such an import and mark it with the project's idiom: a bare
  side-effect import (`import "./polyfills";`, Go's `_ "image/png"`), or a
  suppression with a reason (`import myapp.signals  # noqa: F401  registers
  handlers`). Imports in Java, C#, Rust, and TypeScript with default import
  elision are compile-time only, so removing an unused one there is tier 0.

## Unreachable and commented-out code

```ts
// before
function rateFor(plan: Plan): number {
  if (plan.kind === "free") return 0;
  return plan.rate;
  // legacy proration, disabled 2023
  // return prorate(plan.rate, plan.start);
  console.log("unreachable");
}

// after
function rateFor(plan: Plan): number {
  if (plan.kind === "free") return 0;
  return plan.rate;
}
```

Commented-out code is noise; version control already remembers it. A branch
guarded by a constant can go too, if the constant has exactly one definition
in source and no build configuration, define or replace step, or build tag
overrides it.

Not safe when the "dead" branch is guarded by a runtime flag, environment
variable, or config value, or by a constant that differs between builds:
conditional-compilation symbols (`#if DEBUG`), Rust `cfg!(debug_assertions)`
and `#[cfg(feature = "...")]`, bundler-defined `process.env.NODE_ENV`,
`__DEV__`, or `import.meta.env.*`, Go build tags, per-platform generated
constants. That code is live in some build or deployment, even if not in the
one you looked at; removing it is tier 2 at least, and usually a product
decision.

## Duplication: reuse what exists

```ts
// before: new code in the diff
const slug = title.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-");

// after: the codebase already exports one
import { slugify } from "@/lib/text";
const slug = slugify(title);
```

Before swapping, compare behavior on the inputs that usually differ: empty
string, whitespace only, unicode and accents, leading or trailing separators,
repeated separators, null or undefined. Here the hand-rolled version turns
`"Hello, World!"` into `hello-world-` (trailing separator) and `"Café"` into
`caf-`; a shared helper probably trims and transliterates. If they differ, the
swap is tier 2: decide which behavior is intended and say so in the report.
(Often the duplicate was the bug, which is one more reason to look.)

Standard library traps worth knowing:

```python
# before: hand-rolled grouping
groups = {}
for order in orders:
    groups.setdefault(order.customer_id, []).append(order)

# tempting but WRONG unless orders is already sorted by customer_id:
# itertools.groupby only groups *consecutive* equal keys
groups = {k: list(g) for k, g in itertools.groupby(orders, key=lambda o: o.customer_id)}

# correct, and still simpler than the original
groups = defaultdict(list)
for order in orders:
    groups[order.customer_id].append(order)
```

Reuse only helpers the scope can already import: the same package, its
declared dependencies, or a shared library's public API. If the only
equivalent lives in another module's internals, under a test-support tree,
or in a heavy module the lightweight one does not otherwise depend on,
calling it adds a dependency edge or an import cycle nobody asked for. Keep
the duplicate and list it under "Noticed outside scope" as a candidate for
promotion to shared code. After a swap, run the project's import-cycle or
module-boundary check if it has one.

Not safe when the two blocks look alike but change for different reasons (a
tax rule and a shipping rule that happen to share a formula today). Merging
them couples unrelated decisions. Leave them and note why.

## Single-implementation interfaces

```java
// before
public interface ReceiptFormatter { String format(Receipt r); }
public final class DefaultReceiptFormatter implements ReceiptFormatter { ... }
// one implementer, one injection site, no test double anywhere

// after
public final class ReceiptFormatter { public String format(Receipt r) { ... } }
```

In Go the idiom is that consumers declare the small interfaces they need; a
producer-side interface with exactly one implementation and no consumer-side
use is usually ceremony.

Check before collapsing:
- Test doubles: search the test tree for the interface name and for mocking
  calls that target it.
- DI or container configuration that binds the interface by name or type.
- Module or package boundaries the project enforces (the interface may be the
  allowed import while the implementation is not).
- Published extension points that outside code implements. That makes it
  tier 3.

## Pass-through wrappers

```ts
// before: module-internal (not exported), new in this diff, one caller
class UserService {
  constructor(private repo: UserRepo) {}
  getUser(id: string) { return this.repo.findById(id); }
}

// after: the single caller uses repo.findById directly
```

Safe when the wrapper adds no behavior (no validation, mapping, caching,
authorization, logging, or transaction), has few callers inside the scope,
and is not exported.

Not safe when it is a deliberate facade at a layer boundary, when it is the
only thing a test double replaces, or when its name carries intent across
many call sites (`isEligibleForRefund(order)` reads better than the boolean
expression it wraps, even if it is one line).

## Premature generalization and knobs that never vary

```python
# before
def export_rows(rows, fmt="csv", delimiter=",", quotechar='"', encoding="utf-8", writer_cls=None):
    if fmt != "csv":
        raise NotImplementedError(fmt)
    writer_cls = writer_cls or csv.writer
    ...
# every caller: export_rows(rows)

# after
def export_rows(rows):
    ...  # csv.writer with the defaults inlined
```

Other shapes of the same thing: a strategy registry with one strategy; a
generic type parameter only ever instantiated with one type and adding no
safety; an options object where one key is ever set; a feature flag that is
on everywhere and never toggled.

Not safe when the knob is part of a public API, read from configuration or
environment that operators set, or set by tests to reach an edge case (then
the "knob" is a test seam; keep it or find a better seam).

## Deep nesting to guard clauses

```go
// before
func apply(c *Coupon, o *Order) error {
    if c != nil {
        if !c.Expired(now()) {
            if o.Total >= c.Minimum {
                o.Discount = c.Amount
                return nil
            } else {
                return ErrBelowMinimum
            }
        } else {
            return ErrExpired
        }
    }
    return ErrNoCoupon
}

// after
func apply(c *Coupon, o *Order) error {
    if c == nil {
        return ErrNoCoupon
    }
    if c.Expired(now()) {
        return ErrExpired
    }
    if o.Total < c.Minimum {
        return ErrBelowMinimum
    }
    o.Discount = c.Amount
    return nil
}
```

Check each inverted condition mechanically. `!(a && b)` is `!a || !b`, and
`>=` inverts to `<`, not `<=`. Also confirm the order of checks is unchanged
when the checks have side effects or when several could fail at once (the
error a caller sees depends on which check runs first).

Not safe when an early exit skips cleanup that the original reached:

```ts
lock.acquire();
if (!valid) return;        // lock never released
...
lock.release();
```

Use the language's structured cleanup (`try/finally`, `defer`, `with`,
`using`, RAII) if it is already present; otherwise leave the shape alone or
make the cleanup structured first as its own batch.

## Clever code to plain code

```js
// before
const byId = users.reduce((acc, u) => ({ ...acc, [u.id]: u }), {});
const label = n > 99 ? "99+" : n > 0 ? String(n) : n === 0 ? "" : "?";
const whole = ~~ratio;

// after
const byId = Object.fromEntries(users.map((u) => [u.id, u]));
let label;
if (n > 99) label = "99+";
else if (n > 0) label = String(n);
else if (n === 0) label = "";
else label = "?";
const whole = Math.trunc(ratio);
```

The spread-in-reduce version is also quadratic, so the plain one is faster.

Plain replacements must match semantics where it matters. `~~x` truncates
toward zero like `Math.trunc`, but it also wraps values outside the 32-bit
signed range and turns `NaN` and `Infinity` into `0`, so the two agree only
for finite magnitudes below 2^31. If inputs can fall outside that, the
"simplification" changes results; state the range assumption or leave it. Equally, `Math.floor` is not a substitute for either on negative
numbers.

Not safe when a comment, benchmark, or profile shows the clever form was a
deliberate optimization in a hot path.

## Redundant defensive checks

```ts
// before (strict null checks on; every caller passes a typed Cart)
function total(cart: Cart): Money {
  if (!cart) return Money.zero();
  if (!Array.isArray(cart.items)) throw new Error("items must be an array");
  return cart.items.reduce((sum, i) => sum.add(i.price), Money.zero());
}

// after
function total(cart: Cart): Money {
  return cart.items.reduce((sum, i) => sum.add(i.price), Money.zero());
}
```

This is tier 1: cite the fact that makes the check impossible (the type is
non-nullable under strict checks; the only caller constructs the value; the
value was validated at the boundary two frames up). Static types are only as
good as their enforcement: TypeScript types are erased and Python hints are
not checked at runtime, so the fact must include that the checker runs in CI
over every caller and that no `any`, untyped caller, or deserialized value
reaches the function. Otherwise the check is a real runtime guard.

Not safe when a lock acquisition, an `await` or `yield`, a transaction
boundary, or an I/O call sits between the original check and the repeat.
The second check then sees state that may have changed, and it is the one
that matters:

```python
# looks redundant, is not: another thread may have filled the entry
# while this one waited for the lock
if key not in cache:
    with lock:
        if key not in cache:
            cache[key] = compute(key)
```

The same holds for a re-read inside a transaction or after
`SELECT ... FOR UPDATE`, for re-checking shared state after an `await`, and
for defensive copies: returning a copy of an internal list, copying an
argument before storing it, snapshotting a collection before iterating while
it may change, copying before handing data to another thread or task.
Removing any of these is tier 2 at minimum. Justify it by reasoning about
the possible interleavings; the test suite will almost never catch a mistake
here.

Keep checks at trust boundaries: request bodies, parsed JSON, environment
variables, files, message queues, FFI, and public library entry points where
fail-fast argument validation is part of the contract (for example Java's
`Objects.requireNonNull` at a public method).

## Error handling that swallows or repeats

```python
# before
def load_settings(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        return {}

# after (tier 2: callers now see the error instead of an empty dict)
def load_settings(path):
    with open(path) as f:
        return json.load(f)
```

```csharp
// before
public Invoice Load(Guid id)
{
    try { return _repo.Load(id); }
    catch (Exception ex) { throw ex; }   // adds nothing and resets the stack trace
}

// after (tier 1: the same exception escapes, with a better trace)
public Invoice Load(Guid id) => _repo.Load(id);
```

Classify before changing:

| Shape | Tier | Notes |
|---|---|---|
| catch, rethrow the same error unchanged, and it is the only handler on that `try` (or every handler rethrows unchanged) | 1 | Pure noise. In C#, `throw ex;` also resets the stack trace; removing the catch or using `throw;` preserves it. |
| catch, rethrow unchanged, followed by a broader sibling handler | keep | Load-bearing: it exempts that type from the broader handler (see below). Restructure only as a tier 2 change. |
| catch, wrap with context, rethrow | keep | Usually useful. Simplify only if the codebase does not wrap. |
| catch, log, rethrow, at every layer | 2 | Produces duplicate log lines; log once where it is handled. |
| catch everything, log, return default or continue | 2 | Callers may rely on "never throws". Fine to tighten in code that is new in this diff. |
| catch at a process boundary (request handler, job loop, UI event) | keep | That is where catching everything belongs. |

A rethrow-only clause is not always noise. When the same `try` has a
broader handler after it, the clause decides which errors escape:

```python
try:
    return int(settings["port"])
except ValueError:
    raise                    # a malformed port must fail loudly...
except Exception:
    return DEFAULT_PORT      # ...while a missing key or a None falls back
```

Deleting the first clause sends `ValueError` into the broad handler,
which swallows it: a silent behavior change. The same shape exists in Java
and C# (`catch (IOException e) { throw e; }` before `catch (Exception e)`).
JavaScript has a single catch clause per `try`, so there a catch that only
rethrows is always removable, which is why ESLint's `no-useless-catch` is
safe to apply. Ruff's TRY203 fires only when every handler re-raises, for
the same reason.

In JavaScript, `return await p` inside a `try`/`catch`/`finally`, or in a
block holding `using` or `await using` declarations, is load-bearing:
without the `await`, a rejection skips the `catch`, or the resource is
disposed before the promise settles. Elsewhere it is not redundant either:
it keeps the function's frame in async stack traces, which is why ESLint
deprecated `no-return-await`. Drop it only where the project's lint
configuration asks for that; otherwise it is a taste edit, so leave it.

## Logging noise

```go
// before
func (s *Store) Save(ctx context.Context, o Order) error {
    log.Printf("Save called with order %v", o.ID)
    if err := s.db.Insert(ctx, o); err != nil {
        log.Printf("error inserting order: %v", err)
        return fmt.Errorf("insert order %s: %w", o.ID, err)
    }
    log.Printf("Save completed successfully")
    return nil
}

// after: the caller that handles the error decides whether to log it
func (s *Store) Save(ctx context.Context, o Order) error {
    if err := s.db.Insert(ctx, o); err != nil {
        return fmt.Errorf("insert order %s: %w", o.ID, err)
    }
    return nil
}
```

Before removing a log line, search for its message text in alert rules,
dashboards, runbooks, and log-based metrics (often in another repository or
an ops config directory). Audit logs are behavior, not noise. Removing logs is
tier 2 when anything consumes them.

## Casts and type escapes

```ts
// before
const id = (req.params as any).id as string;
const user = getCurrentUser()!;           // getCurrentUser(): User
const order = (await repo.find(id))!;     // find(): Promise<Order | undefined>
const count = Number(items.length);

// after
const { id } = req.params;                // typed by the router already
const user = getCurrentUser();            // the type is already non-nullable; tsc agrees
const order = (await repo.find(id))!;     // left alone: find() can return undefined;
                                          // listed under Possible bugs
const count = items.length;
```

Casts and non-null assertions are erased at runtime in TypeScript, so
removing one that the checker confirms was unnecessary (typescript-eslint's
`no-unnecessary-type-assertion` flags exactly these) is tier 0 or 1. The `!`
on `find()` is different: it asserts away a real "may be missing" case, and
replacing it with handling for `undefined` would add a branch, which is a
behavior change and a bug fix.

```rust
// before (qty: u32)
let total: u64 = items.iter().map(|i| i.qty as u64).sum::<u64>() as u64;
let label = format!("{}", name.to_string());

// after
let total: u64 = items.iter().map(|i| u64::from(i.qty)).sum();
let label = name.to_string();
```

`u64::from` only compiles for lossless conversions, so the compiler proves
this swap safe; an `as` cast would silently truncate or wrap if `qty` later
became a wider or signed type. The trailing `as u64` and the turbofish were
converting a `u64` to itself.

Python equivalents: `str(name)` on a `str`, `int(len(x))`, `cast(Foo, foo)`
on something already typed `Foo`, scattered `# type: ignore`. Java and C#:
casts to the static type the expression already has.

Fix the type at its source rather than at each use. A non-null assertion or
`as` cast that hides a real "may be missing" case is a latent bug; report it
under possible bugs rather than silently "fixing" it.

## Fallbacks that hide bugs

```ts
// before
// config is schema-validated at startup and timeoutMs is required;
// displayName is required and non-empty, validated on every write
const timeout = config.timeoutMs ?? 30000;
const name = user.displayName || "Unknown";

// after
const timeout = config.timeoutMs;
const name = user.displayName;
```

Safe when absence is impossible by construction and you can cite why. For an
`||` fallback, "present" is not enough: cite that the value is never empty
either, as the comment above does.

Not safe when absence is possible: then the fallback is behavior. Watch the
operator too: `||` also replaces `0`, `""`, and `false`, so `count || 10`
and `count ?? 10` differ for `count = 0`. Replacing one with the other is a
behavior change, even if it fixes a bug (report it as such).

## Comments that restate the code

```java
// before
/**
 * Gets the user.
 * @param id the id
 * @return the user
 */
public User getUser(String id) {
    // Look up the user in the repository
    return repo.find(id); // return the user
}

// after
public User getUser(String id) {
    return repo.find(id);
}
```

Keep comments that carry information the code cannot: why a non-obvious
choice was made, a constraint from outside the code (a vendor bug, a
regulation, a protocol quirk), a link to an issue, a warning about an
ordering dependency. Keep license headers, doc comments that generate public
documentation, and directives that tools parse (lint suppressions, type
checker pragmas, build tags, codegen markers).

Where a comment explains what a confusing block does, prefer making the code
say it (a well-named function or variable) and then delete the comment.

## Naming that drifts from its neighbors

If the surrounding code says `getInvoice`, `getCustomer`, `getPayment`, a new
`fetchInvoiceDataObject` should become `getInvoiceDetails` or similar. Match
the existing verb set, the noun the domain already uses (do not introduce
`client` where the code says `customer`), and the local casing and
abbreviation habits.

Rename only private, non-serialized names. Exported names, names a
serializer or ORM reads by reflection, and names in templates or config are
tier 3. Renaming for personal preference, where the existing name already
matches local convention, is a taste edit: skip it.
