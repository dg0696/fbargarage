"""Import an eBay active-listings CSV into MySQL.

Usage:
    python scripts/import_listings_csv.py
    python scripts/import_listings_csv.py --file financials/f-bargarage/eBay-all-active-listings-report-2026-03-22-12306956625.csv
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from store_app.store import upsert_listing  # noqa: E402

FINANCIALS = ROOT / "financials" / "f-bargarage"
DATE_FORMATS = (
    "%b-%d-%y %H:%M:%S %Z",
    "%b-%d-%Y %H:%M:%S %Z",
    "%b-%d-%y %H:%M:%S",
)


def newest_listings_csv() -> Path:
    matches = sorted(FINANCIALS.glob("eBay-all-active-listings-report-*.csv"))
    matches = [path for path in matches if " (1)" not in path.name]
    if not matches:
        raise SystemExit(f"No active-listings CSV in {FINANCIALS}")
    return matches[-1]


def parse_date(value: object) -> str | None:
    text = str(value or "").strip()
    if not text or text == "--":
        return None
    for suffix in (" PDT", " PST"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    for fmt in ("%b-%d-%y %H:%M:%S", "%b-%d-%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Import eBay active-listings CSV into MySQL.")
    parser.add_argument("--file", type=Path, default=None)
    args = parser.parse_args()
    path = args.file or newest_listings_csv()
    if not path.is_file():
        raise SystemExit(f"File not found: {path}")

    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {"Item number", "Title"}
    missing = required - set(frame.columns)
    if missing:
        raise SystemExit(f"{path.name} missing columns: {', '.join(sorted(missing))}")

    count = 0
    for row in frame.to_dict(orient="records"):
        item_id = str(row.get("Item number") or "").strip()
        title = str(row.get("Title") or "").strip()
        if not item_id or not title:
            continue
        upsert_listing(
            ebay_item_id=item_id,
            title=title,
            sku=str(row.get("Custom label (SKU)") or "").strip(),
            price=row.get("Current price") or row.get("Start price") or None,
            qty=row.get("Available quantity") or 0,
            status="active",
            ebay_category=str(row.get("eBay category 1 name") or "").strip(),
            watchers=row.get("Watchers") or None,
            start_date=parse_date(row.get("Start date")),
            end_date=parse_date(row.get("End date")),
        )
        count += 1
    print(f"Imported {count} listings from {path.name}")


if __name__ == "__main__":
    main()
