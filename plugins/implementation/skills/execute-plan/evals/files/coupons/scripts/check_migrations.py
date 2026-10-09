"""Apply every migration, in file-name order, to a throwaway in-memory SQLite database."""

import pathlib
import sqlite3
import sys


def main() -> int:
    files = sorted(pathlib.Path("migrations").glob("*.sql"))
    db = sqlite3.connect(":memory:")
    for path in files:
        db.executescript(path.read_text())
        print(f"applied {path.name}")
    print(f"{len(files)} migrations OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
