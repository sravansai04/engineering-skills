import unittest

from app.pagination import paginate


class PaginateTest(unittest.TestCase):
    def test_first_page(self):
        self.assertEqual(paginate(list(range(50)), 1, 20), list(range(20)))

    def test_rejects_page_zero(self):
        with self.assertRaises(ValueError):
            paginate([1, 2, 3], 0, 20)
