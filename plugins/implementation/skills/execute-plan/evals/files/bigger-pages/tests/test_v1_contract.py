"""Partner contract for /v1, as published in docs/api/v1.md. Partners depend on it."""

import unittest

from api.listing import list_items


class V1ContractTest(unittest.TestCase):
    def test_default_page_size_is_20(self):
        result = list_items(list(range(100)))
        self.assertEqual(len(result["items"]), 20)

    def test_page_size_override(self):
        result = list_items(list(range(100)), page_size=5)
        self.assertEqual(len(result["items"]), 5)


if __name__ == "__main__":
    unittest.main()
