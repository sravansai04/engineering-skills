# shop

Checkout and pricing for the web store.

## Development

- Tests: `python3 -m unittest discover -s tests -v`
- Static check: `python3 -m compileall -q shop scripts`
- Migrations: `python3 scripts/check_migrations.py` (applies every migration, in order, to
  an in-memory SQLite database)

## Conventions

- Money is integer cents. Round fractional cents with `shop.money.round_half_even`.
- Pricing functions take today's date as a parameter and never read the database or the system time.
- Migrations are numbered `NNNN_description.sql` and never renumbered once merged.
