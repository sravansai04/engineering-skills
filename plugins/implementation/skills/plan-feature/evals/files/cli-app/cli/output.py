"""Shared output formatting for CLI commands."""
import json
from datetime import date, datetime


def _default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def render_table(rows, columns):
    """Return rows as an aligned plain-text table."""
    widths = {c: max([len(c)] + [len(str(r.get(c, ""))) for r in rows]) for c in columns}
    lines = ["  ".join(c.upper().ljust(widths[c]) for c in columns)]
    for row in rows:
        lines.append("  ".join(str(row.get(c, "")).ljust(widths[c]) for c in columns))
    return "\n".join(lines)


def render_json(rows, columns):
    """Return rows as a JSON array, keeping only the given columns."""
    return json.dumps([{c: row.get(c) for c in columns} for row in rows], default=_default, indent=2)


RENDERERS = {"table": render_table, "json": render_json}
