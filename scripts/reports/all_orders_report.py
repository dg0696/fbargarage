#!/usr/bin/env python3
"""Generate all-orders reports from SQLite."""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analyze_all_orders import (
    build_sku_detail_lines,
    build_summary_lines,
    default_paths,
    month_label,
    write_report,
)
from scripts.db.connection import DEFAULT_DB_PATH, db_session
from scripts.reports.db_queries import load_order_lines


def generate_all_orders_reports(
    year,
    month,
    sku_prefix="G",
    store_name="f-bargarage",
    db_path=None,
):
    ym = f"{year:04d}-{month:02d}"
    source_label = f"db://order_lines/{ym}"

    with db_session(db_path) as conn:
        month_df = load_order_lines(conn, year, month)

    if month_df.empty:
        print(f"No orders found for {ym} in database")
        return False

    label = month_label(year, month)
    store_title = f"{label} ALL-ORDERS REPORT ({store_name})"
    store_lines, _ = build_summary_lines(month_df, store_title, source_label)
    base_report, sku_base = default_paths(year, month, sku_prefix)
    write_report(f"{base_report}_report.txt", store_lines)
    write_report(f"{base_report}_summary.txt", store_lines[:9])

    if sku_prefix:
        sku_df = month_df[
            month_df["Custom Label"].notna()
            & month_df["Custom Label"].astype(str).str.startswith(sku_prefix, na=False)
        ]
        sku_title = f"SKU_{sku_prefix} REPORT (FROM ALL-ORDERS) - {label.title()}"
        sku_lines = build_sku_detail_lines(sku_df, sku_title, source_label)
        write_report(f"{sku_base}_report.txt", sku_lines)
        write_report(f"{sku_base}_summary.txt", sku_lines[:9])
        export_path = Path(f"{sku_base}_data.csv")
        export_path.parent.mkdir(parents=True, exist_ok=True)
        sku_df.to_csv(export_path, index=False)
        print(f"Wrote {export_path}")

    return True


def main():
    parser = argparse.ArgumentParser(description="Generate all-orders reports from DB")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--sku-prefix", default="G")
    parser.add_argument("--store-name", default="f-bargarage")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()

    ok = generate_all_orders_reports(
        args.year,
        args.month,
        sku_prefix=args.sku_prefix,
        store_name=args.store_name,
        db_path=args.db,
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
