"""Sample data standing in for the reporting database."""

SALES = [{"id": i, "amount_cents": 1000 + i} for i in range(1, 76)]
REFUNDS = [{"id": i, "sale_id": i * 3, "amount_cents": 500} for i in range(1, 21)]
INVENTORY = [{"sku": f"SKU-{i:03d}", "on_hand": i % 7} for i in range(1, 131)]
