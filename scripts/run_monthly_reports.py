#!/usr/bin/env python3
"""Run monthly financial reports from CSV exports or SQLite."""

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analyze_all_orders import enrich_orders, filter_month, load_all_orders
from scripts.db.connection import DEFAULT_DB_PATH
from scripts.reports.all_orders_report import generate_all_orders_reports
from scripts.reports.sku_transaction_report import generate_sku_transaction_report


def find_transaction_report(financials_dir, year, month):
    ym = f"{year:04d}{month:02d}"
    for directory in (financials_dir, Path("reports")):
        matches = sorted(directory.glob(f"Transaction_report_{ym}*.csv"))
        if matches:
            return matches[0]
    return None


def find_all_orders_report(financials_dir, year, month):
    pattern = f"ebay-all-orders-report-{year:04d}-{month:02d}-*.csv"
    matches = sorted(financials_dir.glob(pattern))
    preferred = [path for path in matches if " (1)" not in path.name]
    for path in preferred or matches:
        df = enrich_orders(load_all_orders(path))
        if len(filter_month(df, year, month)) > 0:
            return path

    candidates = sorted(
        (path for path in financials_dir.glob("ebay-all-orders-report-*.csv") if " (1)" not in path.name),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        df = enrich_orders(load_all_orders(path))
        if len(filter_month(df, year, month)) > 0:
            return path
    return None


def run_csv_reports(financials_dir, year, month, sku_prefix):
    ym = f"{year:04d}-{month:02d}"
    missing = []

    tx_file = find_transaction_report(financials_dir, year, month)
    if tx_file:
        subprocess.run(
            [
                sys.executable,
                "scripts/analyze_sku_financials.py",
                "--sku-prefix",
                sku_prefix,
                "--year",
                str(year),
                "--input-file",
                str(tx_file),
                "--output-file",
                f"reports/sku_{sku_prefix}_{ym}_report.txt",
                "--export-csv",
                f"reports/sku_{sku_prefix}_{ym}_data.csv",
            ],
            check=True,
        )
    else:
        missing.append(f"Transaction_report for {ym}")

    orders_file = find_all_orders_report(financials_dir, year, month)
    if orders_file:
        subprocess.run(
            [
                sys.executable,
                "scripts/analyze_all_orders.py",
                "--input-file",
                str(orders_file),
                "--year",
                str(year),
                "--month",
                str(month),
                "--sku-prefix",
                sku_prefix,
            ],
            check=True,
        )
    else:
        missing.append(f"ebay-all-orders-report for {ym}")

    return missing


def run_db_reports(year, month, sku_prefix, db_path):
    ym = f"{year:04d}-{month:02d}"
    missing = []

    generate_sku_transaction_report(
        year,
        month,
        sku_prefix=sku_prefix,
        output_file=f"reports/sku_{sku_prefix}_{ym}_report.txt",
        export_csv=f"reports/sku_{sku_prefix}_{ym}_data.csv",
        db_path=db_path,
    )

    ok = generate_all_orders_reports(
        year,
        month,
        sku_prefix=sku_prefix,
        db_path=db_path,
    )
    if not ok:
        missing.append(f"order_lines in db for {ym}")

    return missing


def main():
    parser = argparse.ArgumentParser(description="Run monthly report generation")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--sku-prefix", default="G")
    parser.add_argument("--from-db", action="store_true", help="Generate reports from SQLite")
    parser.add_argument("--from-csv", action="store_true", help="Generate reports from CSV files")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()

    use_db = args.from_db or not args.from_csv
    financials_dir = Path("financials/f-bargarage")

    if use_db:
        missing = run_db_reports(args.year, args.month, args.sku_prefix, args.db)
    else:
        missing = run_csv_reports(financials_dir, args.year, args.month, args.sku_prefix)

    if missing:
        print(f"Missing data for {args.year:04d}-{args.month:02d}:")
        for item in missing:
            print(f"  - {item}")
        sys.exit(1)


if __name__ == "__main__":
    main()
