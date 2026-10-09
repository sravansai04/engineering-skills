# Plan: report endpoints

## Acceptance criteria

- `/reports/sales`, `/reports/refunds` and `/reports/inventory` return paginated rows from
  `app/data.py`, 25 per page by default, with `page` and `total` in the body.
- An out-of-range page returns an empty `items` list, not an error.

## Tasks

T1. Add `paginate(rows, page, page_size=25)` in `app/pagination.py`, returning
    `{"items": [...], "page": page, "total": len(rows)}`. Verify: `tests/test_pagination.py`
    covers the first page, a middle page and an out-of-range page.

T2. Add `/reports/sales` in `app/handlers/sales.py` (paginated `SALES`, `page` taken from
    params, default 1) and register it in `app/routes.py`. Verify: `tests/test_sales.py`
    through `dispatch`.

T3. Add `/reports/refunds` in `app/handlers/refunds.py` the same way and register it in
    `app/routes.py`. Verify: `tests/test_refunds.py` through `dispatch`.

T4. Add `/reports/inventory` in `app/handlers/inventory.py` the same way and register it in
    `app/routes.py`. Verify: `tests/test_inventory.py` through `dispatch`.

T5. Document the three endpoints in README.md.
