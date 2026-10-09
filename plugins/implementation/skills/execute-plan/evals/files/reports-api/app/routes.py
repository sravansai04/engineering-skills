"""Route table: path -> handler. Every endpoint registers here."""

from app.handlers import health

ROUTES = {
    "/health": health.handle,
}


def dispatch(path: str, params: dict) -> dict:
    handler = ROUTES.get(path)
    if handler is None:
        return {"status": 404, "body": {"error": "not_found"}}
    return handler(params)
