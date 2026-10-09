import unittest
from decimal import Decimal

from orders.export import export_rows, parse_amount, to_csv


class ExportRowsTest(unittest.TestCase):
    def test_only_paid_orders_are_exported(self):
        orders = [
            {"title": "Draft order", "status": "draft", "amount": "5.00"},
            {"title": "Blue Mug", "status": "paid", "amount": "12.50"},
            {"title": "Red Pen", "status": "refunded", "amount": "3.00"},
        ]
        self.assertEqual(export_rows(orders, "batch-1"), [["blue-mug", "12.50"]])

    def test_a_batch_is_exported_once(self):
        orders = [
            {"title": "Draft order", "status": "draft", "amount": "1.00"},
            {"title": "Lamp", "status": "paid", "amount": "40"},
        ]
        self.assertEqual(export_rows(orders, "batch-2"), [["lamp", "40"]])
        self.assertEqual(export_rows(orders, "batch-2"), [])

    def test_missing_amount_counts_as_zero(self):
        self.assertEqual(parse_amount({"title": "Gift card"}), Decimal("0"))


class ToCsvTest(unittest.TestCase):
    def test_rows_become_csv_lines(self):
        self.assertEqual(to_csv([["blue-mug", "12.50"]]), "blue-mug,12.50\r\n")


if __name__ == "__main__":
    unittest.main()
