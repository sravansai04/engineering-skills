import unittest

from loyalty.tiers import tier_for


class TierTest(unittest.TestCase):
    def test_new_customer_has_a_tier(self):
        self.assertIsInstance(tier_for(0), str)


if __name__ == "__main__":
    unittest.main()
