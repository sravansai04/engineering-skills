"""In-process token store shared by every request thread."""


class TokenStore:
    def __init__(self):
        self._rows = {}

    def get(self, token):
        row = self._rows.get(token)
        return dict(row) if row is not None else None

    def put(self, token, row):
        self._rows[token] = dict(row)

    def mark_used(self, token):
        self._rows[token]["used"] = True
