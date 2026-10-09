from datetime import datetime

from pydantic import BaseModel


class CreateOrder(BaseModel):
    customer_id: str
    sku: str
    quantity: int
    requested_at: datetime
    note: str | None = None
