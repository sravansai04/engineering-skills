# loyalty

Loyalty points and tiers.

## Development

- Tests: `python3 -m unittest discover -s tests -v`
- Static check: `python3 -m compileall -q loyalty scripts`

## Environments

The staging database (`STAGING_DATABASE_URL`) is shared by QA and the sales demo. Writes to
it are scheduled with the QA team in advance.
