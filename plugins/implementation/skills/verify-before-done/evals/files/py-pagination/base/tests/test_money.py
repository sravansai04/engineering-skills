import unittest

from app.money import format_cents


class FormatCentsTest(unittest.TestCase):
    def test_whole_and_fraction(self):
        self.assertEqual(format_cents(1999), "$19.99")

    def test_pads_single_digit_cents(self):
        self.assertEqual(format_cents(1905), "$19.05")
