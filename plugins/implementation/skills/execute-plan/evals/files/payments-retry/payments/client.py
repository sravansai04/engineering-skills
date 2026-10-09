"""Thin client for the payment provider. Network calls go through `transport`."""


class PaymentError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class PaymentClient:
    def __init__(self, transport):
        self._transport = transport

    def charge(self, order_id: str, amount_cents: int) -> dict:
        return self._transport.post(
            "/charges", {"order_id": order_id, "amount_cents": amount_cents}
        )

    def refund(self, charge_id: str) -> dict:
        return self._transport.post("/refunds", {"charge_id": charge_id})
