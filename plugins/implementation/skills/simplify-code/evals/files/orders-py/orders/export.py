"""Turn paid orders into CSV rows for the finance export."""
import csv
import io
import json
import re
import threading
from decimal import Decimal, InvalidOperation

from orders import audit

_lock = threading.Lock()
_exported_batches = set()


def _make_slug(title):
    # Convert the title to lowercase and trim it
    lowered = title.lower().strip()
    # Replace every run of non-alphanumeric characters with a dash
    return re.sub(r"[^a-z0-9]+", "-", lowered)


def parse_amount(order):
    """Parse the amount.

    Args:
        order: the order

    Returns:
        the amount
    """
    try:
        return Decimal(order["amount"])
    except InvalidOperation:
        raise
    except Exception:
        # missing or non-string amount: count it as zero
        return Decimal("0")


def mark_exported(batch_id):
    """Return True the first time a batch id is seen, False afterwards."""
    _lock.acquire()
    if batch_id:
        if batch_id not in _exported_batches:
            _exported_batches.add(batch_id)
            _lock.release()
            return True
        else:
            _lock.release()
            return False
    _lock.release()
    return False


def export_rows(orders, batch_id):
    if not mark_exported(batch_id):
        return []
    receipt = audit.record("export", batch_id)
    rows = []
    # Loop over the orders
    for i in range(1, len(orders)):
        order = orders[i]
        if order is not None:
            if order.get("status") == "paid":
                rows.append([_make_slug(order["title"]), str(parse_amount(order))])
            else:
                continue
    return rows


def to_csv(rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    # Write each row
    for row in rows:
        writer.writerow(row)
    result = buffer.getvalue()
    return result
