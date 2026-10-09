from payments.backoff import backoff_delays
from payments.retry_policy import RetryPolicy
from payments.retryable import is_retryable


def retry(fn, policy: RetryPolicy, sleep):
    """Call fn(); on a retryable error wait and try again, up to policy.max_attempts calls."""
    delays = backoff_delays(policy)
    for attempt in range(policy.max_attempts):
        try:
            return fn()
        except Exception as error:
            if not is_retryable(error) or attempt == policy.max_attempts - 1:
                raise
            sleep(delays[attempt])
