from payments.client import PaymentClient


def pay_for_order(client: PaymentClient, order_id: str, amount_cents: int) -> dict:
    return client.charge(order_id, amount_cents)
