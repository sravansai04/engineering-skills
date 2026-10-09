from payments.retry_policy import RetryPolicy


def backoff_delays(policy: RetryPolicy) -> list:
    """Delays to wait before each retry (one fewer than max_attempts)."""
    return [policy.base_delay_s * policy.multiplier**n for n in range(policy.max_attempts - 1)]
