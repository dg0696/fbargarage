#!/usr/bin/env python3
"""Generate SKU transaction reports from SQLite."""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analyze_sku_financials import calculate_financial_summary, generate_report
from scripts.db.connection import DEFAULT_DB_PATH, db_session
from scripts.reports.db_queries import load_transactions


def generate_sku_transaction_report(
    year,
    month,
    sku_prefix="G",
    output_file=None,
    export_csv=None,
    db_path=None,
):
    ym = f"{year:04d}-{month:02d}" if month else str(year)
    if output_file is None:
        suffix = ym if month else str(year)
        output_file = f"reports/sku_{sku_prefix}_{suffix}_report.txt"
    if export_csv is None:
        suffix = ym if month else str(year)
        export_csv = f"reports/sku_{sku_prefix}_{suffix}_data.csv"

    with db_session(db_path) as conn:
        df = load_transactions(conn, year, month=month, sku_prefix=sku_prefix)

    source_label = f"db://transactions/{ym if month else year}"

    if df.empty:
        print(f"No data found for SKUs starting with '{sku_prefix}' in {source_label}")
        return True

    summary = calculate_financial_summary(df)
    df.to_csv(export_csv, index=False)
    print(f"Detailed data exported to CSV: {export_csv}")
    generate_report(df, summary, sku_prefix, year, output_file)
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate SKU transaction report from DB")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, default=None)
    parser.add_argument("--sku-prefix", default="G")
    parser.add_argument("--output-file", default=None)
    parser.add_argument("--export-csv", default=None)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()

    ok = generate_sku_transaction_report(
        args.year,
        args.month,
        sku_prefix=args.sku_prefix,
        output_file=args.output_file,
        export_csv=args.export_csv,
        db_path=args.db,
    )
    sys.exit(0 if ok else 0)


if __name__ == "__main__":
    main()
