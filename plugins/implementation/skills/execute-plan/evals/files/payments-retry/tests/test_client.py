import unittest

from payments.client import PaymentClient


class FakeTransport:
    def __init__(self):
        self.calls = []

    def post(self, path, payload):
        self.calls.append((path, payload))
        return {"id": "ch_1", "status": "succeeded"}


class PaymentClientTest(unittest.TestCase):
    def test_charge_posts_order_and_amount(self):
        transport = FakeTransport()
        PaymentClient(transport).charge("o-1", 1250)
        self.assertEqual(transport.calls, [("/charges", {"order_id": "o-1", "amount_cents": 1250})])


if __name__ == "__main__":
    unittest.main()
