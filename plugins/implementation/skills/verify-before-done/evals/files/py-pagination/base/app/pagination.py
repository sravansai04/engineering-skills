def paginate(items, page, per_page):
    """Return the items on a 1-based page of size per_page."""
    if page < 1 or per_page < 1:
        raise ValueError("page and per_page must be positive")
    start = (page - 1) * (per_page - 1)
    return items[start:start + per_page]
