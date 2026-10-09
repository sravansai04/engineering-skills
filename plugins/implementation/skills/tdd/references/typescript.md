# TDD in TypeScript and JavaScript (Jest or Vitest)

The single-test command is in SKILL.md. Jest and Vitest share almost the same API. The main differences:

- **Mock namespace:** Vitest uses `vi`, Jest uses `jest`.
- **Imports:** Vitest needs `import { describe, it, expect, vi } from "vitest"` unless `globals: true` is set in its config.

Use whichever runner the project already has. Check `devDependencies` and the `test` script in `package.json`.

## Worked cycle: a fixed-window rate limiter with an injected clock

**Test list:**

- first request is allowed
- requests over the limit within a window are rejected
- the limit resets when the window passes
- a request just before the window ends is still rejected
- each key has its own budget

The clock is a constructor argument from the very first test. Wall-clock time is the most common source of flaky tests, and designing the seam in up front costs nothing.

**Cycle 1, red.**

```ts
// rate-limiter.test.ts
import { describe, it, expect } from "vitest";
import { RateLimiter } from "./rate-limiter";

describe("RateLimiter", () => {
  it("allows the first request for a key", () => {
    const limiter = new RateLimiter({ limit: 2, windowMs: 1000, now: () => 0 });

    expect(limiter.tryAcquire("user-1")).toBe(true);
  });
});
```

The first run can't resolve `./rate-limiter`. That's "not yet" red. Add a stub whose `tryAcquire` returns `false`, and you get the right red: `expected false to be true`.

**Cycle 1, green.** Fake it with `return true`.

**Cycle 2, red.** This test kills the fake:

```ts
it("rejects requests over the limit within one window", () => {
  const limiter = new RateLimiter({ limit: 2, windowMs: 1000, now: () => 0 });
  limiter.tryAcquire("user-1");
  limiter.tryAcquire("user-1");

  expect(limiter.tryAcquire("user-1")).toBe(false);
});
```

Observed red: `expected true to be false`.

**Cycle 2, green.** Count calls and compare with the limit:

```ts
private count = 0;

tryAcquire(key: string): boolean {
  this.count += 1;
  return this.count <= this.opts.limit;
}
```

**Cycle 3, red.** Time is advanced by mutating a variable the fake clock reads. No timers, no sleeping.

```ts
it("allows requests again once the window has passed", () => {
  let t = 0;
  const limiter = new RateLimiter({ limit: 1, windowMs: 1000, now: () => t });
  limiter.tryAcquire("user-1");

  t = 1000;

  expect(limiter.tryAcquire("user-1")).toBe(true);
});
```

Observed red: `expected false to be true`. The count keeps climbing because nothing ever resets it.

**Cycle 3, green.** The simplest code that passes keeps a window start and resets the count whenever the clock has moved at all (`if (now !== this.start)`). That's wrong, and the next test says so.

**Cycle 4, red.** The boundary just inside the window:

```ts
it("still rejects in the last millisecond of the window", () => {
  let t = 0;
  const limiter = new RateLimiter({ limit: 1, windowMs: 1000, now: () => t });
  limiter.tryAcquire("user-1");

  t = 999;

  expect(limiter.tryAcquire("user-1")).toBe(false);
});
```

Observed red: `expected true to be false`.

**Cycle 4, green.** Reset only when `now - this.start >= this.opts.windowMs`. Cycles 3 and 4 together pin the window length from both sides. The t = 1000 test fails if `>=` becomes `>`. The t = 999 test fails if the window length is ignored, for example if `windowMs` is replaced by `1`, a mutant the first three tests can't catch.

**Cycle 5, red.** Separate keys get separate budgets:

```ts
it("tracks each key separately", () => {
  const limiter = new RateLimiter({ limit: 1, windowMs: 1000, now: () => 0 });
  limiter.tryAcquire("user-1");

  expect(limiter.tryAcquire("user-2")).toBe(true);
});
```

Observed red: `expected false to be true`, because `user-2` shares `user-1`'s single count.

**Cycle 5, green.** Keep one window per key in a `Map`. If a `Map` had been introduced earlier, this test passes on arrival. Then prove it by temporarily replacing `key` with a constant in both the `get` and the `set`, and watching it go red.

**Refactor.** The implementation once all five tests pass and the code has been tidied:

```ts
// rate-limiter.ts
type Window = { start: number; count: number };

export class RateLimiter {
  private readonly windows = new Map<string, Window>();

  constructor(
    private readonly opts: { limit: number; windowMs: number; now: () => number },
  ) {}

  tryAcquire(key: string): boolean {
    const now = this.opts.now();
    const current = this.windows.get(key);
    if (!current || now - current.start >= this.opts.windowMs) {
      this.windows.set(key, { start: now, count: 1 });
      return true;
    }
    if (current.count >= this.opts.limit) return false;
    current.count += 1;
    return true;
  }
}
```

## Table-driven cases

```ts
it.each([
  { input: "Hello World", expected: "hello-world" },
  { input: "  trim me  ", expected: "trim-me" },
])("slugifies $input", ({ input, expected }) => {
  expect(slugify(input)).toBe(expected);
});
```

The `$input` placeholder in the name makes each case show up as its own specification in the output.

## Async pitfalls: tests that pass without checking anything

- **Always `await` or `return` the promise you assert on.** For rejections, write `await expect(save(bad)).rejects.toThrow("invalid email")`. Without the `await`, the test can finish before the assertion runs.
- **Assertions inside callbacks** (event handlers, `.then`) may never execute. Add `expect.assertions(n)` or `expect.hasAssertions()` so a skipped assertion fails the test.

## Cleanup between tests

Leaked mock state causes order-dependent failures, and the obvious fix only covers half of it:

- **`restoreAllMocks` does not clear call history.** In both Jest and Vitest it only puts back originals replaced with `spyOn` (and, in Jest, `replaceProperty`). A module-level `vi.fn()` or `jest.fn()` keeps accumulating calls across tests, so `toHaveBeenCalledTimes(1)` starts depending on test order.
- **Set both `clearMocks: true` and `restoreMocks: true`** in the runner config. Vitest 5 turns `clearMocks` on by default; Jest and older Vitest versions don't, so check the installed version.
- **Undo stubbed env vars and globals.** In Vitest, set `unstubEnvs: true` and `unstubGlobals: true`, or call `vi.unstubAllEnvs()` and `vi.unstubAllGlobals()` in `afterEach`.
- **Return to real timers** with `vi.useRealTimers()` or `jest.useRealTimers()` in `afterEach` after using fake ones.
- **Better still, create mocks inside the test or in `beforeEach`** rather than at module scope. A mock that only one test can see has no history to leak.

## Fake timers and system time

Use fake timers for code that reads `Date.now()` or schedules work with `setTimeout`/`setInterval` and can't take an injected clock:

```ts
import { afterEach, beforeEach, expect, it, vi } from "vitest";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2024-01-31T23:59:00Z"));
});
afterEach(() => {
  vi.useRealTimers();
});

it("fires the debounced save once after typing stops", () => {
  const save = vi.fn();
  const onType = debounce(save, 300);

  onType("a");
  onType("ab");
  vi.advanceTimersByTime(300);

  expect(save).toHaveBeenCalledTimes(1);
  expect(save).toHaveBeenCalledWith("ab");
});
```

Jest's equivalents are `jest.useFakeTimers()`, `jest.setSystemTime(...)`, `jest.advanceTimersByTime(ms)`, and `jest.useRealTimers()`. When the timer callback awaits promises, use the async variant (`vi.advanceTimersByTimeAsync(ms)`) so microtasks run in between.

The `save` mock here checks an outgoing command (the save is the behavior), which is a legitimate use of a mock.

## Network

Unit tests should fake your own API-client interface. To test the client itself, intercept HTTP at the network layer with Mock Service Worker (`msw`). Check the installed major version first (`npm ls msw`), because 3.0 moved the imports and renamed the unhandled-request option:

| | msw 2.x | msw 3.x |
|---|---|---|
| `http`, `HttpResponse` | `from "msw"` | `from "msw/http"` |
| Unhandled-request option | `onUnhandledRequest` | `onUnhandledFrame` |
| Custom callback | `(request, print)`, then `print.error()` | `({ frame, defaults })`, then `defaults.error()` |

msw 3 ignores the old option name at runtime and falls back to `"warn"`, which lets unmatched requests reach the real network. TypeScript reports the stale name; plain JavaScript does not.

Setting the option to `"error"` is not enough on its own. It blocks the unmatched request and makes it fail with a network error, but it does not fail the test. A client that maps failures to a domain error turns that network error into the same `RatesUnavailable` the outage test expects, so a wrong URL or a handler that doesn't match passes for the wrong reason. Record unhandled requests and fail in `afterEach`, and assert on something only the intended path produces. With msw 3:

```ts
import { afterAll, afterEach, beforeAll, expect, it } from "vitest";
import { http, HttpResponse } from "msw/http";
import { setupServer } from "msw/node";

const server = setupServer(
  http.get("https://api.example.com/rates", () => HttpResponse.json({ usd: 1 })),
);
const unhandled: unknown[] = [];

beforeAll(() =>
  server.listen({
    onUnhandledFrame({ frame, defaults }) {
      unhandled.push(frame);
      defaults.error(); // still block the real request
    },
  }),
);
afterEach(() => {
  server.resetHandlers();
  expect(unhandled.splice(0)).toEqual([]); // splice empties the list even when this fails
});
afterAll(() => server.close());

it("surfaces a provider outage as RatesUnavailable", async () => {
  server.use(
    http.get("https://api.example.com/rates", () => new HttpResponse(null, { status: 503 })),
  );

  const error = await fetchRates().catch((e: unknown) => e);

  expect(error).toBeInstanceOf(RatesUnavailable);
  expect(error).toMatchObject({ status: 503 });
});
```

With msw 2, import `http` and `HttpResponse` from `"msw"` and swap the listener:

```ts
const unhandled: string[] = [];

server.listen({
  onUnhandledRequest(request, print) {
    unhandled.push(`${request.method} ${request.url}`);
    print.error();
  },
});
```

A failing `afterEach` fails the test that just ran, so a stray request is pinned on the test that made it. The `status: 503` assertion means a network error, which carries no status, can't satisfy the outage test. For Jest, drop the `vitest` import line.

## Module mocks

`vi.mock("./payments")` and `jest.mock("./payments")` are hoisted above imports and replace the whole module for the file. This is convenient, but it's the easiest way to mock what you don't own and to couple tests to import structure. Prefer passing the dependency in, through a constructor or function argument. Keep module mocks for true boundaries that the code under test can't receive any other way.

## Ordering and randomness

- **Shuffle test order** to expose hidden dependencies between tests:
  - Jest: `--randomize`. Rerun a failing order with `--seed=N`.
  - Vitest: `--sequence.shuffle.tests`. Pin the order with `--sequence.seed`.
- **Inject randomness.** Accept a `random: () => number` parameter. Spying on `Math.random` is a last resort.
- **Pin the timezone** for date formatting tests in the test environment. Set `TZ=UTC` in the test script or the runner's global setup, so results don't depend on the developer's machine.

## UI components

Test what the user perceives. With Testing Library, query by role, label, or visible text (`getByRole("button", { name: "Save" })`), not by CSS class, test id, or component internals. Assert on what appears or what callback fires, not on component state.

## Snapshots

The rules are in SKILL.md under "Snapshot abuse". In these runners, two specifics apply:

- **`toMatchInlineSnapshot()` writes the expected value into the test file,** where reviewers see it.
- **`-u` updates snapshots in both Jest and Vitest** by accepting whatever the code now produces. Read the diff first.
