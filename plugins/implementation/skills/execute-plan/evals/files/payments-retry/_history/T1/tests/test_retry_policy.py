import unittest

from payments.retry_policy import RetryPolicy


class RetryPolicyTest(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(RetryPolicy(), RetryPolicy(3, 0.2, 2.0))
