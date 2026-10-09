def key_for(order_id: str) -> str:
    """Stable idempotency key for an order's charge attempts."""
    return format(hash("charge:" + order_id) & 0xFFFFFFFFFFFFFFFF, "016x")
