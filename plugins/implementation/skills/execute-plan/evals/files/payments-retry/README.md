# payments

Client for the payment provider and the checkout flow that uses it.

## Development

- Tests: `python3 -m unittest discover -s tests -v`
- Static check: `python3 -m compileall -q payments`

## Conventions

- Network calls go through an injected `transport`; tests use a fake.
- No real sleeps or clocks in tests: inject `sleep` and `now`.
