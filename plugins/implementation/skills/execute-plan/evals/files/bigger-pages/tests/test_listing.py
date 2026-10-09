import unittest

from api.listing import list_items


class ListingTest(unittest.TestCase):
    def test_second_page(self):
        result = list_items(list(range(30)), page=2, page_size=10)
        self.assertEqual(result["items"], list(range(10, 20)))


if __name__ == "__main__":
    unittest.main()
