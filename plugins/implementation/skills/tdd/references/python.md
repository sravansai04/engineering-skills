# TDD in Python (pytest)

The single-test command is in SKILL.md. This file covers idioms, a worked cycle, and tools for deterministic tests.

## Collection gotchas: make sure the test actually runs

By default pytest collects:

- files named `test_*.py` or `*_test.py`
- functions named `test_*`
- classes named `Test*` that have no `__init__`

A project can change these through `python_files`, `python_classes`, `python_functions`, and `testpaths` in `pyproject.toml` (`[tool.pytest.ini_options]`), `pytest.ini`, `tox.ini`, or `setup.cfg`. If a new test "passes" on its first run, check the summary line. The pass count should have gone up by one.

An `async def` test needs an async plugin. Use whichever the project already has:

- `pytest-asyncio`: mark tests with `@pytest.mark.asyncio`, or set `asyncio_mode = "auto"`
- `anyio`: mark tests with `@pytest.mark.anyio`

Without a plugin, how the test behaves depends on the pytest version. Before pytest 8.4 the test was skipped with only a warning, so it could never go red. From 8.4 it fails.

Also, calling an async function without `await` returns a coroutine object, and `assert coroutine` is always true, so the test passes without checking anything.

## Worked cycle: `parse_duration("1h30m") -> 5400`

**Test list:**

- seconds
- minutes
- combined units
- unknown unit is rejected
- empty string is rejected

**Cycle 1, red.** Start with the first test:

```python
# tests/test_duration.py
from timeparse import parse_duration

def test_parses_seconds():
    assert parse_duration("45s") == 45
```

The first run fails with `ModuleNotFoundError: No module named 'timeparse'`. That's "not yet" red, not the right red. Add a stub:

```python
# timeparse.py
def parse_duration(text: str) -> int:
    return 0
```

Run again and you get `assert 0 == 45`. That's the right red: the assertion fails because the behavior is missing.

**Cycle 1, green.** Fake it with `return 45`. It passes.

**Cycle 2, red.** Add a second test. This is triangulation: the hardcoded `45` can't satisfy both tests.

```python
def test_parses_minutes():
    assert parse_duration("2m") == 120
```

Observed red: `assert 45 == 120`.

**Cycle 2, green.** Write the real logic for one number followed by one unit:

```python
_UNITS = {"s": 1, "m": 60, "h": 3600}

def parse_duration(text: str) -> int:
    return int(text[:-1]) * _UNITS[text[-1]]
```

**Cycle 3, red.** Combined units become one parametrized rule. Each case needs a readable `id`:

```python
import pytest

@pytest.mark.parametrize(
    ("text", "expected"),
    [("1h30m", 5400), ("1m5s", 65), ("1h1m1s", 3661)],
    ids=["hours and minutes", "minutes and seconds", "all three units"],
)
def test_sums_each_unit(text, expected):
    assert parse_duration(text) == expected
```

Observed red, one line per row:

```
ValueError: invalid literal for int() with base 10: '1h30'
ValueError: invalid literal for int() with base 10: '1m5'
ValueError: invalid literal for int() with base 10: '1h1m1'
```

These rows fail with an exception, not an assertion. The traceback ends in `parse_duration` (`int(text[:-1])`), not in the test or a fixture. The single-unit code is choking on input it was never built for, which is exactly the missing behavior, so this is an acceptable red (SKILL.md, red step 4).

Pick rows that each fail. A single-unit row such as `("2h", 7200)` would pass at once against the Cycle 2 code and prove nothing new. These three rows go in together because they are examples of one rule, fail for the same predicted reason, and are fixed by one change. When rows need different changes, add them one per cycle, as the Go reference does with its table.

**Cycle 3, green, then refactor.** A regex handles combined units. Rename for clarity while the tests are green:

```python
import re

_UNITS = {"s": 1, "m": 60, "h": 3600}
_PART = re.compile(r"(\d+)([hms])")

def parse_duration(text: str) -> int:
    return sum(int(n) * _UNITS[unit] for n, unit in _PART.findall(text))
```

**Cycle 4, red.** The error case:

```python
def test_rejects_unknown_unit():
    with pytest.raises(ValueError, match="unknown duration"):
        parse_duration("3x")
```

This fails with `DID NOT RAISE`, which is the right red. The current code silently returns 0.

**Cycle 4, green.** Make the pattern match the whole string:

```python
_WHOLE = re.compile(r"(?:\d+[hms])+")

def parse_duration(text: str) -> int:
    if not _WHOLE.fullmatch(text):
        raise ValueError(f"unknown duration: {text!r}")
    return sum(int(n) * _UNITS[unit] for n, unit in _PART.findall(text))
```

`fullmatch("")` is `None`, so the empty-string case on the list would pass the moment you write it. Per SKILL.md, prove it can fail before you trust it. Temporarily change the guard to `if text and not ...`, watch the test fail, then restore the guard.

## Idioms

- **Exceptions:** use `pytest.raises(ExcType, match="regex")`. `match` is a regex search against `str(exc)`, so escape special characters.
- **Floats:** compare with `pytest.approx(expected)`. For money, use `decimal.Decimal` and assert exactly.
- **Fixtures** (`@pytest.fixture`) hold shared arrange steps. Use function scope (the default) for anything mutable. Module- or session-scoped mutable fixtures leak state between tests and create order dependence.
- **Built-in fixtures:**
  - `tmp_path` gives a fresh directory per test.
  - `monkeypatch.setenv` / `monkeypatch.setattr` set values and undo them automatically.
  - `capsys` captures stdout and stderr. Use it for CLI output that is part of the contract.
  - `caplog` captures log records. Use it only when the log is the requirement, and assert on `record.levelname` or structured fields rather than whole message strings.
- **Property-based tests:** Hypothesis (`@given(st.text())`) finds edge cases your example list missed. Use it after the examples pass, to assert invariants such as "a parsed duration is never negative."
- **Snapshots:** if the project uses `syrupy`, keep snapshots small and read every diff before running `pytest --snapshot-update`.

## Fakes and mocks

Define the boundary as a `typing.Protocol` in your code, and write a fake for tests:

```python
from typing import Protocol

class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...

class FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject))

def test_sends_one_receipt_per_order():
    sender = FakeEmailSender()
    checkout = Checkout(email=sender)

    checkout.place_order(cart_with_one_item(), customer="ana@example.com")

    assert sender.sent == [("ana@example.com", "Your receipt")]
```

When you do need a mock:

- **Use `unittest.mock.create_autospec(SomeClass, instance=True)`** rather than a bare `Mock()`. An autospecced mock rejects calls that don't match the real signature. A bare `Mock` accepts anything, so it keeps passing after the real API changes.
- **`patch()` replaces a name where it is looked up, not where it is defined.** If `orders.py` does `from payments import charge`, patch `orders.charge`, not `payments.charge`. This trap is a good reason to prefer passing dependencies in.

## Deterministic tests

**Time.** Prefer passing `now` or a clock callable in:

```python
def is_expired(coupon, now: datetime) -> bool: ...
```

When the code reads the clock directly, use `time-machine` or `freezegun`:

```python
import datetime as dt
import time_machine

@time_machine.travel(dt.datetime(2024, 1, 31, 23, 59, tzinfo=dt.timezone.utc), tick=False)
def test_coupon_valid_until_end_of_day():
    ...
```

**Randomness.** Inject a `random.Random(seed)` instance instead of calling module-level `random`. The `pytest-randomly` plugin, if installed:

- reseeds `random` (and Faker, NumPy, factory_boy) for each test
- shuffles test order to expose hidden dependencies
- replays the previous order with `pytest --randomly-seed=last`
- can be disabled with `-p no:randomly`

**Network.** Use your own fake behind a Protocol for unit tests. For the HTTP adapter itself:

- use `responses` (for `requests`), `respx` (for `httpx`), or `pytest-httpserver` (a real local server)
- `pytest-socket` with `--disable-socket` makes any accidental real connection fail loudly

**Timezone and locale.** Use timezone-aware datetimes everywhere. Pin `TZ` in the test environment config rather than relying on the developer's machine.

## Bug fix example

```python
def test_total_ignores_items_removed_from_cart():
    # Regression for ticket 1234: removed items were still being charged.
    cart = Cart()
    cart.add("apple", price=Decimal("1.00"))
    cart.add("pear", price=Decimal("2.00"))
    cart.remove("apple")

    assert cart.total() == Decimal("2.00")
```

Run it first and confirm it fails with the reported symptom: `assert Decimal('3.00') == Decimal('2.00')`. Then fix the code.
