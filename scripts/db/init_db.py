#!/usr/bin/env python3
"""Initialize or upgrade the eBay store SQLite database."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.db.connection import DEFAULT_DB_PATH, init_schema


def main():
    parser = argparse.ArgumentParser(description="Initialize eBay store SQLite database")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Database file path")
    args = parser.parse_args()

    init_schema(args.db)
    print(f"Database initialized: {args.db}")


if __name__ == "__main__":
    main()
