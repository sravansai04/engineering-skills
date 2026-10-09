"""Money helpers. All amounts are integer cents."""

from fractions import Fraction


def round_half_even(amount: Fraction) -> int:
    """Round a fractional cent amount to whole cents, ties to even (banker's rounding)."""
    return round(amount)
