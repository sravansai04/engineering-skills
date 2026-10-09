import unittest

from shop.cart import Cart, Item
from shop.pricing import subtotal_cents


class SubtotalTest(unittest.TestCase):
    def test_empty_cart(self):
        self.assertEqual(subtotal_cents(Cart()), 0)

    def test_sums_quantity_times_price(self):
        cart = Cart([Item("a", 250, 2), Item("b", 100)])
        self.assertEqual(subtotal_cents(cart), 600)


if __name__ == "__main__":
    unittest.main()
