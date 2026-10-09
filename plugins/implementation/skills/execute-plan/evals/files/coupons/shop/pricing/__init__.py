"""Order pricing. Pure functions over integer cents."""

from shop.cart import Cart


def subtotal_cents(cart: Cart) -> int:
    return sum(item.unit_price_cents * item.quantity for item in cart.items)
