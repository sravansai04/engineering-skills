import unittest

from shop.search import normalize_query


class NormalizeQueryTest(unittest.TestCase):
    def test_lowercases_and_trims(self):
        self.assertEqual(normalize_query("  Red Shoes "), "red shoes")

    def test_collapses_internal_whitespace(self):
        self.assertEqual(normalize_query("red   shoes"), "red shoes")


if __name__ == "__main__":
    unittest.main()
