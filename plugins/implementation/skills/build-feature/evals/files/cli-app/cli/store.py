"""Task storage: a JSON file named by TASKTRACK_FILE."""
import json
import os
from datetime import date
from pathlib import Path


def _path():
    return Path(os.environ.get("TASKTRACK_FILE", Path.home() / ".tasktrack.json"))


def load_tasks():
    path = _path()
    if not path.exists():
        return []
    rows = json.loads(path.read_text())
    for row in rows:
        if row.get("due"):
            row["due"] = date.fromisoformat(row["due"])
    return rows
