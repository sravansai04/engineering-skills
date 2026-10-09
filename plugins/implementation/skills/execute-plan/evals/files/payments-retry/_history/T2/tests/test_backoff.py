import unittest

from payments.backoff import backoff_delays
from payments.retry_policy import RetryPolicy


class BackoffTest(unittest.TestCase):
    def test_default_delays(self):
        self.assertEqual(backoff_delays(RetryPolicy()), [0.2, 0.4])

    def test_single_attempt_has_no_delays(self):
        self.assertEqual(backoff_delays(RetryPolicy(max_attempts=1)), [])
