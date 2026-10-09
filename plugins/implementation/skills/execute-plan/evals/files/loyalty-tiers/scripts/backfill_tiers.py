"""Recompute every customer's loyalty tier and write it back to the database.

Usage: DATABASE_URL=postgres://... python3 scripts/backfill_tiers.py
"""

import os
import sys


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    print(f"connecting to {url} ...", file=sys.stderr)
    print("error: no database driver is installed in this checkout", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
