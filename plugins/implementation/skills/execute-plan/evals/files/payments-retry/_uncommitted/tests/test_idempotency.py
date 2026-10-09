import hashlib
import unittest

from payments.idempotency import key_for


class IdempotencyKeyTest(unittest.TestCase):
    def test_key_is_sha256_of_prefixed_order_id(self):
        expected = hashlib.sha256(b"charge:o-1").hexdigest()
        self.assertEqual(key_for("o-1"), expected)

    def test_same_order_same_key(self):
        self.assertEqual(key_for("o-2"), key_for("o-2"))
