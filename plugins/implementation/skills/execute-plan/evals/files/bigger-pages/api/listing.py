"""Pagination for GET /v1/items."""

DEFAULT_PAGE_SIZE = 20


def list_items(items: list, page: int = 1, page_size: int = None) -> dict:
    size = page_size or DEFAULT_PAGE_SIZE
    start = (page - 1) * size
    return {"items": items[start:start + size], "page": page, "page_size": size}
