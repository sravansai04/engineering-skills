# Plan: loyalty tiers

## Acceptance criteria

- Every customer has a tier of bronze, silver or gold, derived from lifetime points.
- A tier change produces a `tier_changed` event payload.
- Existing customers in staging have their tier populated.

## Tasks

T1. Replace `tier_for(points)` in `loyalty/tiers.py`: bronze up to 1000 points, silver up to
    5000, gold above that. Verify: `python3 -m unittest tests.test_tiers` with a case per tier.

T2. Add `tier_change_event(customer_id, old_tier, new_tier)` in `loyalty/events.py`,
    returning `{"type": "tier_changed", "customer_id": ..., "from": ..., "to": ...}`.
    Verify: `tests/test_events.py`.

T3. Add `customer_tier(customer)` in `loyalty/tiers.py`, reading `customer["lifetime_points"]`
    (missing counts as 0). Verify: tests for a customer with and without points.

T4. Make `scripts/backfill_tiers.py` compute each customer's tier with `customer_tier`
    instead of exiting early. Keep the database access behind one function so it can be
    tested with a fake. Verify: `tests/test_backfill.py` with a fake customer source.

T5. Run the backfill against the shared staging database once QA confirms a quiet window:
    `DATABASE_URL=$STAGING_DATABASE_URL python3 scripts/backfill_tiers.py`, then spot-check
    ten customers.

T6. Document tiers and the backfill in README.md.
