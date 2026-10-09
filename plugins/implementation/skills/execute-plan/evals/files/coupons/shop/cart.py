from dataclasses import dataclass, field


@dataclass(frozen=True)
class Item:
    sku: str
    unit_price_cents: int
    quantity: int = 1
    discountable: bool = True


@dataclass
class Cart:
    items: list = field(default_factory=list)
