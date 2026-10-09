# Plan: retry transient payment failures

## Acceptance criteria

- A charge that fails with a retryable `PaymentError` is retried with exponential backoff,
  up to 3 attempts in total. Declined cards are never retried.
- Retries of one order's charge reuse a single idempotency key, so the provider never
  charges twice.
- Each retry is logged with the order id and the attempt number.

## Tasks

T1. Add a `RetryPolicy` dataclass in `payments/retry_policy.py` (`max_attempts=3`,
    `base_delay_s=0.2`, `multiplier=2.0`). Verify: `python3 -m unittest tests.test_retry_policy`.

T2. Add `backoff_delays(policy)` in `payments/backoff.py`, returning the delay before each
    retry. Verify: `python3 -m unittest tests.test_backoff`.

T3. Add `is_retryable(error)` in `payments/retryable.py`: true only for a `PaymentError`
    with `retryable=True`. Verify: `python3 -m unittest tests.test_retryable`.

T4. Add `retry(fn, policy, sleep)` in `payments/retry.py`, which retries retryable errors
    using the backoff delays and re-raises after `max_attempts`. Verify:
    `python3 -m unittest tests.test_retry`.

T5. Add `key_for(order_id)` in `payments/idempotency.py`: the SHA-256 hex digest of
    `"charge:" + order_id`. Verify: `python3 -m unittest tests.test_idempotency`.

T6. In `payments/checkout.py`, wrap the charge in `PaymentClient.retry_with_backoff(policy)`
    so retryable failures are retried, and pass `key_for(order_id)` as the idempotency key.
    Verify: `tests/test_checkout.py` has a case where the first charge raises a retryable
    `PaymentError` and the second succeeds, both with the same key.

T7. Log each retry attempt (order id, attempt number) at INFO.

T8. Document the retry behaviour in README.md.

## Execution notes

### Progress
| Task | Status | Note |
|---|---|---|
| T1 | todo | |
| T2 | todo | |
| T3 | todo | |
| T4 | todo | |
| T5 | todo | |
| T6 | todo | |
| T7 | todo | |
| T8 | todo | |
