# Test doubles: choosing, designing, and keeping them honest

SKILL.md gives the preference order (real object, fake, stub, mock) and the rule to double only at boundaries you own. This file covers the vocabulary, how to choose, how to build a good fake, and how to stop fakes drifting from reality.

## Vocabulary

Gerard Meszaros's terms are the common ones. Many libraries call everything a "mock", so name the role you need rather than the tool.

| Double | What it does | Typical use |
|---|---|---|
| Dummy | Fills a parameter and is never used | A required argument irrelevant to this test |
| Stub | Returns canned answers to queries | "The exchange-rate service returns 1.1" |
| Spy | Records calls for later assertions | "Which messages were published?" |
| Mock | Pre-programmed with expected calls; fails on unexpected or missing ones | Verifying a required outgoing command |
| Fake | A working, simplified implementation | In-memory repository, in-memory queue, fixed clock |

## Deciding what to do with a dependency

Work through these questions in order and stop at the first that applies:

1. **Is it fast, deterministic, and free of side effects outside the process?** Examples: a value object, a pure function, a domain service. Use the real thing. Doubling it only makes the test fragile.
2. **Is it a resource you control and can run locally?** Examples: your database, filesystem, your own queue. Unit-test the logic against a fake. Test the real adapter in an integration test against the real engine, using a container or a temp instance.
3. **Is it an external system or a nondeterministic source?** Examples: a payment provider, email, a third-party API, the clock, randomness. Put a small interface (a port) in your code, write a fake for unit tests, and cover the adapter that implements the port with an integration or contract test.
4. **Is the behavior under test an outgoing command whose only evidence is the call itself?** Examples: an email sent, an event published, a charge made, or nothing charged when validation fails. Assert on it with a spy, or with a fake that records calls. Use a mock only if the project's style prefers mocks.
5. **Is it a query whose answer you just need?** Stub it, and assert on what the code under test did with the answer, not on the fact that it asked.

## Designing the port

- **Name it in your domain's language and give it the narrowest surface the caller needs.** For example, `PaymentGateway.charge(amount, card_token) -> ChargeResult`, not a mirror of the vendor SDK's 40 methods. A narrow port is easy to fake well. It also limits the blast radius when the vendor changes.
- **Return your own types.** A port that leaks vendor response objects forces every test to build vendor objects.
- **Keep the adapter thin and dumb.** Its job is translation, so its integration test can be small.

## Building a good fake

- **Behave like the real thing for everything tests rely on.** An in-memory repository should enforce the same uniqueness rule the database does, return copies rather than shared references, and raise the same not-found error. A fake that is more permissive than reality lets bugs through.
- **Add inspection helpers for assertions,** such as `sent_messages` or `last_charge`. Add failure injection for the unhappy paths: `fail_next_charge(with=CardDeclined)`, `simulate_timeout()`.
- **Make it deterministic:** fixed clocks, seeded ids, ordered storage.
- **Keep it in shared test support code,** so every test uses the same fake instead of a dozen slightly different ones.

## Keeping fakes honest: contract tests

A fake is only useful while it matches the real implementation. Write one suite of behavioral tests against the port and run it against both implementations:

- the fake, on every run
- the real adapter, in the integration tier, which may be tagged slow or need a service running

```python
import os
import pytest

@pytest.fixture(params=["fake", "real"])
def repo(request):
    if request.param == "fake":
        yield InMemoryOrderRepository()
        return
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        if os.environ.get("CI"):
            pytest.fail("TEST_DATABASE_URL is not set; the real contract must run in CI")
        pytest.skip("TEST_DATABASE_URL not set; real repository contract skipped locally")
    conn = connect(url)
    try:
        yield SqlOrderRepository(conn)  # the repository uses this connection and never commits
    finally:
        conn.rollback()  # each test leaves the database as it found it
        conn.close()

def test_saving_twice_with_same_id_raises_duplicate(repo):
    repo.save(Order(id="o-1"))
    with pytest.raises(DuplicateOrder):
        repo.save(Order(id="o-1"))
```

Two details make the real arm trustworthy:

- **Each test is isolated.** The rollback in teardown means the second run doesn't find `o-1` left over from the first and fail in the arrange step. Rollback-per-test only works when the adapter runs inside a transaction it was handed. If the adapter opens, commits, or pools its own connections, give each test unique data instead (`Order(id=f"o-{uuid.uuid4().hex}")`) or a fresh schema per test or per run.
- **The real arm fails rather than skips in CI.** A skip that fires on every CI run because nobody set the variable is invisible, and it leaves the fake unchecked forever. Most hosted CI services set `CI=true`. Where yours doesn't, use a variable or flag of your own, such as a `--run-integration` option that the CI job always passes.

The same shape works elsewhere:

- **Jest or Vitest:** a function that takes a factory and declares a `describe` block, called once per implementation.
- **Go:** a `func testRepositoryContract(t *testing.T, newRepo func(t *testing.T) Repository)` helper called from two `Test` functions, with cleanup registered through `t.Cleanup`.

When the real adapter fails a contract test that the fake passes, decide which side is wrong:

- **The real system's behavior is the source of truth** (database semantics, the provider's documented behavior). Correct the contract test to match reality. Watch the fake fail the corrected test, then fix the fake.
- **The adapter has a bug.** Fix the adapter.

Either way, rerun the unit tests that use the fake. Some may have been passing on the false assumption, and those unit tests built on a lying fake are the false confidence this practice exists to prevent.

For services owned by other teams, consumer-driven contract testing tools (for example, Pact) do the same job across repository boundaries.

## Databases specifically

- **Run integration tests against the same engine and major version as production.** An in-memory substitute with different semantics hides bugs. Common differences are type coercion, constraint enforcement, transaction isolation, and SQL dialect. Container-based helpers (for example, Testcontainers, which exists for most major languages) make this cheap.
- **Isolate tests from each other.** Either wrap each test in a transaction that rolls back (when the code under test accepts the connection it runs on), or give each test unique data. Wiping shared tables between tests breaks parallel runs.
- **Keep business rules out of the database layer where you can,** so most rule tests stay in the fast unit tier against a fake repository.

## Mocking pitfalls

- **Untyped mocks that accept any call.** They keep passing after the real signature changes. Use spec- or type-checked doubles: Python `create_autospec`, typed interfaces in TypeScript, compile-checked interfaces in Go.
- **Patching the wrong name.** Patch where the code under test looks the name up, not where it's defined. Better still, pass the dependency in.
- **Global patches that leak.** A patched module, timer, or `Date` that isn't restored makes tests order-dependent. Restore in teardown, or use the runner's auto-restore setting.
- **Mocking value objects or data structures.** Build real ones. If they're hard to build, add a test data builder.
- **Partial mocks of the system under test.** Stubbing one method of the class you're testing means you're testing a different class. Split the responsibilities instead.
- **Verifying queries.** "Asserts `get_price` was called with `sku-1`" breaks on harmless refactors, such as caching or batching, and proves nothing about the result. Assert on the result.
- **Mock chains.** A mock returning a mock returning a mock signals the code reaches through collaborators. Redesign so the unit receives what it needs directly.

## Smell checklist when reviewing your own tests

- [ ] Arrange is longer than the code under test
- [ ] The test would fail after a behavior-preserving refactor
- [ ] It asserts call counts, call order, or arguments on something that isn't a boundary
- [ ] A mock returns another mock
- [ ] A third-party class is mocked directly instead of an adapter you own
- [ ] The fake has no contract test against the real implementation
- [ ] The test stays green with the production integration deliberately broken

Any ticked box is worth a second look before moving on.
