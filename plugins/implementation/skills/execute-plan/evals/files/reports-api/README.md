# reports-api

Read-only reporting endpoints over in-memory sample data.

## Development

- Tests: `python3 -m unittest discover -s tests -v`
- Static check: `python3 -m compileall -q app`

## Conventions

- One module per endpoint under `app/handlers/`, exposing `handle(params) -> dict`.
- Every endpoint is registered in the route table in `app/routes.py`.
- Responses are `{"status": <int>, "body": <dict>}`.
