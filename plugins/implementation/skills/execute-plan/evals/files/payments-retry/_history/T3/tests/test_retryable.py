import unittest

from payments.client import PaymentError
from payments.retryable import is_retryable


class RetryableTest(unittest.TestCase):
    def test_retryable_payment_error(self):
        self.assertTrue(is_retryable(PaymentError("timeout", retryable=True)))

    def test_declined_card_is_not_retryable(self):
        self.assertFalse(is_retryable(PaymentError("declined")))

    def test_other_exceptions_are_not_retryable(self):
        self.assertFalse(is_retryable(ValueError("bad input")))
