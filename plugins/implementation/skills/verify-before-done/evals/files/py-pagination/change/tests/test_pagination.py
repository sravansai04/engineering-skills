import unittest

from app.pagination import paginate


class PaginateTest(unittest.TestCase):
    def test_first_page(self):
        self.assertEqual(paginate(list(range(50)), 1, 20), list(range(20)))

    def test_rejects_page_zero(self):
        with self.assertRaises(ValueError):
            paginate([1, 2, 3], 0, 20)

    def test_pages_do_not_overlap(self):
        items = list(range(50))
        pages = [paginate(items, n, 20) for n in (1, 2, 3)]
        self.assertEqual(pages[0] + pages[1] + pages[2], items)
