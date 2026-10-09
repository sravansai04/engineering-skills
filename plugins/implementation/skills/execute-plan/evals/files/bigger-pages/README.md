# items-api

## Development

- Tests: `python3 -m unittest discover -s tests -v`
- Static check: `python3 -m compileall -q api`

## Versioning

The `/v1` API is published to partners (docs/api/v1.md). `tests/test_v1_contract.py` pins
its documented behaviour. A change to documented v1 behaviour ships as a new version, or
after the partner notice period.
