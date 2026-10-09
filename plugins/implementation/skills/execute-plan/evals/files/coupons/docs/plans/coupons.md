# Plan: percentage coupons

Spec: a customer can apply one percentage coupon at checkout. Each item's discount is capped
at the coupon's per-item maximum. Non-discountable items are never discounted.

## Acceptance criteria

- A 10% coupon with a 500-cent per-item cap discounts each eligible line by the smaller of
  10% of the line and 500 cents.
- Expired coupons are rejected with `CouponExpired`.
- Orders store the discount total, and the order summary and email receipt show it.

## Tasks

T1. Add a `Coupon` dataclass in `shop/coupons.py` with `code`, `percent` (int, 0-100),
    `max_per_item_cents` and `expires_on` (date). Verify: `python3 -m unittest tests.test_coupons`
    passes with a construction test.

T2. Add `apply_discount(cart, coupon)` to `shop/pricing.py`. It applies the coupon's percent
    to each discountable line and caps each line's discount at `max_per_item_cents`.
    Verify: `python3 -m unittest tests.test_pricing` passes with new cases for cap, no cap,
    and non-discountable items.

T3. Reject expired coupons: `apply_discount` raises `CouponExpired` when `expires_on` is
    before today. Verify: a test for an expired coupon.

T4. Migration `migrations/0042_add_discount_total.sql`: add a nullable
    `discount_total_cents` column to `orders`. Verify: `python3 scripts/check_migrations.py`.

T5. Show the discount on the order summary (`shop/summary.py`, `render_summary(order)`).
    Verify: a test that the summary includes a "Discount" line when the total is non-zero
    and omits it when it is zero.

T6. Add the discount line to the email receipt (`shop/receipt.py`). Verify: a receipt test.

T7. Document coupons in README.md.
