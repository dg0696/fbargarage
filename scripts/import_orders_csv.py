"""Import an eBay all-orders CSV into MySQL (no buyer fields).

Usage:
    python scripts/import_orders_csv.py
    python scripts/import_orders_csv.py --file financials/f-bargarage/ebay-all-orders-report-2026-08-31-11331308008.csv
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

from store_app.store import upsert_order  # noqa: E402

FINANCIALS = ROOT / "financials" / "f-bargarage"


def newest_orders_csv() -> Path:
    matches = sorted(FINANCIALS.glob("ebay-all-orders-report-*.csv"))
    matches = [path for path in matches if " (1)" not in path.name]
    if not matches:
        raise SystemExit(f"No all-orders CSV in {FINANCIALS}")
    return matches[-1]


def parse_money(value: object):
    text = str(value or "").replace("$", "").replace(",", "").strip()
    if not text or text == "--":
        return None
    return text


def parse_date(value: object):
    text = str(value or "").strip()
    if not text or text == "--":
        return None
    for fmt in ("%b-%d-%y", "%b-%d-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Import eBay all-orders CSV into MySQL.")
    parser.add_argument("--file", type=Path, default=None)
    args = parser.parse_args()
    path = args.file or newest_orders_csv()
    if not path.is_file():
        raise SystemExit(f"File not found: {path}")

    header_row = 0
    preview = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()[:12]
    for idx, line in enumerate(preview):
        if "Order Number" in line and "Item Title" in line:
            header_row = idx
            break
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, skiprows=header_row)
    frame.columns = frame.columns.str.strip().str.strip('"')
    if "Order Number" not in frame.columns:
        raise SystemExit(f"{path.name} is not an all-orders report: {list(frame.columns)[:8]}")

    count = 0
    skipped = 0
    for row in frame.to_dict(orient="records"):
        order_id = str(row.get("Order Number") or "").strip()
        title = str(row.get("Item Title") or "").strip()
        if not order_id or not title:
            skipped += 1
            continue
        upsert_order(
            order_id=order_id,
            sku=str(row.get("Custom Label") or "").strip(),
            ebay_item_id=str(row.get("Item Number") or "").strip(),
            sold_on=parse_date(row.get("Sale Date")),
            qty=row.get("Quantity") or 1,
            sold_for=parse_money(row.get("Sold For")),
        )
        count += 1
    print(f"Imported {count} order lines from {path.name} (skipped {skipped} blank rows)")


if __name__ == "__main__":
    main()
