import unittest

from payments.client import PaymentError
from payments.retry import retry
from payments.retry_policy import RetryPolicy


class RetryTest(unittest.TestCase):
    def test_succeeds_after_one_retryable_failure(self):
        calls, slept = [], []

        def fn():
            calls.append(1)
            if len(calls) == 1:
                raise PaymentError("timeout", retryable=True)
            return "ok"

        self.assertEqual(retry(fn, RetryPolicy(), slept.append), "ok")
        self.assertEqual(slept, [0.2])

    def test_non_retryable_error_is_raised_immediately(self):
        def fn():
            raise PaymentError("declined")

        with self.assertRaises(PaymentError):
            retry(fn, RetryPolicy(), lambda s: None)

    def test_gives_up_after_max_attempts(self):
        def fn():
            raise PaymentError("timeout", retryable=True)

        with self.assertRaises(PaymentError):
            retry(fn, RetryPolicy(max_attempts=2), lambda s: None)
