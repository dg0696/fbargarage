#!/usr/bin/env python3
"""Import eBay financial CSV exports into SQLite."""

import argparse
import hashlib
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.db.connection import DEFAULT_DB_PATH, db_session, init_schema
from scripts.lib.parsers import (
    clean_str,
    find_header_row,
    invoice_month_from_filename,
    parse_date_iso,
    parse_money,
    parse_quantity,
    row_to_json,
)

DEFAULT_FINANCIALS = REPO_ROOT / "financials" / "f-bargarage"
IMPORT_DIRS = [DEFAULT_FINANCIALS, REPO_ROOT / "reports"]


def detect_file_type(path):
    name = path.name.lower()
    if name.startswith("transaction_report_"):
        return "transactions"
    if name.startswith("ebay-all-orders-report-"):
        return "order_lines"
    if name.startswith("order_earnings"):
        return "order_earnings"
    if name.startswith("2745279534_") and name.endswith(".csv"):
        return "tax_invoice_lines"
    if "promoted-listing" in name:
        return "promoted_listing_fees"
    return None


def load_csv(path, markers, skip_fallback=(4, 5, 6, 7, 11, 12)):
    header_row = find_header_row(path, markers)
    if header_row is None:
        for skip in skip_fallback:
            try:
                sample = pd.read_csv(path, skiprows=skip, nrows=1, encoding="utf-8-sig")
                if any(marker.replace(",", "") in ",".join(sample.columns) for marker in markers):
                    header_row = skip
                    break
            except Exception:
                continue
    if header_row is None:
        raise ValueError(f"Could not find header row in {path}")
    df = pd.read_csv(path, skiprows=header_row, encoding="utf-8-sig", low_memory=False)
    df.columns = df.columns.str.strip()
    return df


def start_import_run(conn, source, data_type, file_path):
    cur = conn.execute(
        """
        INSERT INTO import_runs (source, file_path, data_type, status)
        VALUES (?, ?, ?, 'running')
        """,
        (source, str(file_path), data_type),
    )
    return cur.lastrowid


def finish_import_run(conn, run_id, inserted, updated, skipped, status="completed", error_message=None):
    conn.execute(
        """
        UPDATE import_runs
        SET finished_at = datetime('now'),
            rows_inserted = ?,
            rows_updated = ?,
            rows_skipped = ?,
            status = ?,
            error_message = ?
        WHERE id = ?
        """,
        (inserted, updated, skipped, status, error_message, run_id),
    )


def upsert_row(conn, table, columns, values, conflict_columns):
    placeholders = ", ".join("?" for _ in columns)
    col_names = ", ".join(columns)
    update_cols = [c for c in columns if c not in conflict_columns]
    if update_cols:
        update_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
        sql = f"""
            INSERT INTO {table} ({col_names}) VALUES ({placeholders})
            ON CONFLICT({', '.join(conflict_columns)}) DO UPDATE SET {update_clause}
        """
    else:
        sql = f"""
            INSERT INTO {table} ({col_names}) VALUES ({placeholders})
            ON CONFLICT({', '.join(conflict_columns)}) DO NOTHING
        """
    before = conn.total_changes
    conn.execute(sql, values)
    delta = conn.total_changes - before
    return "inserted" if delta else "skipped"


def transaction_dedup_key(row, tx_id, tx_type, order_num):
    parts = [
        parse_date_iso(row.get("Transaction creation date")) or "",
        tx_type,
        order_num,
        tx_id,
        clean_str(row.get("Item ID")) or "",
        clean_str(row.get("Description")) or "",
        str(parse_money(row.get("Net amount")) or ""),
        str(parse_money(row.get("Gross transaction amount")) or ""),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def import_transactions(conn, path):
    df = load_csv(path, ["Transaction creation date", "Custom label"])
    run_id = start_import_run(conn, "csv", "transactions", path)
    inserted = updated = skipped = 0

    for _, row in df.iterrows():
        tx_id = clean_str(row.get("Transaction ID")) or ""
        tx_type = clean_str(row.get("Type")) or "Unknown"
        order_num = clean_str(row.get("Order number")) or "--"
        dedup_key = transaction_dedup_key(row, tx_id, tx_type, order_num)
        columns = [
            "source_run_id", "transaction_date", "type", "order_number", "legacy_order_id",
            "buyer_username", "buyer_name", "ship_to_city", "ship_to_state", "ship_to_zip",
            "ship_to_country", "net_amount", "payout_currency", "payout_date", "payout_id",
            "payout_method", "payout_status", "reason_for_hold", "item_id", "transaction_id",
            "item_title", "custom_label", "quantity", "item_subtotal", "shipping_and_handling",
            "seller_collected_tax", "ebay_collected_tax", "final_value_fee_fixed",
            "final_value_fee_variable", "regulatory_operating_fee", "inad_fee",
            "below_standard_fee", "international_fee", "charity_donation",
            "deposit_processing_fee", "promoted_listing_fee", "gross_transaction_amount",
            "transaction_currency", "exchange_rate", "reference_id", "description", "raw_json",
            "dedup_key",
        ]
        values = [
            run_id,
            parse_date_iso(row.get("Transaction creation date")),
            tx_type,
            order_num,
            clean_str(row.get("Legacy order ID")),
            clean_str(row.get("Buyer username")),
            clean_str(row.get("Buyer name")),
            clean_str(row.get("Ship to city")),
            clean_str(row.get("Ship to province/region/state")),
            clean_str(row.get("Ship to zip")),
            clean_str(row.get("Ship to country")),
            parse_money(row.get("Net amount")),
            clean_str(row.get("Payout currency")),
            parse_date_iso(row.get("Payout date")),
            clean_str(row.get("Payout ID")),
            clean_str(row.get("Payout method")),
            clean_str(row.get("Payout status")),
            clean_str(row.get("Reason for hold")),
            clean_str(row.get("Item ID")),
            tx_id,
            clean_str(row.get("Item title")),
            clean_str(row.get("Custom label")),
            parse_quantity(row.get("Quantity")),
            parse_money(row.get("Item subtotal")),
            parse_money(row.get("Shipping and handling")),
            parse_money(row.get("Seller collected tax")),
            parse_money(row.get("eBay collected tax")),
            parse_money(row.get("Final Value Fee - fixed")),
            parse_money(row.get("Final Value Fee - variable")),
            parse_money(row.get("Regulatory operating fee")),
            parse_money(row.get('Very high "item not as described" fee')),
            parse_money(row.get("Below standard performance fee")),
            parse_money(row.get("International fee")),
            parse_money(row.get("Charity donation")),
            parse_money(row.get("Deposit processing fee")),
            parse_money(row.get("Promoted Listing Standard fee")),
            parse_money(row.get("Gross transaction amount")),
            clean_str(row.get("Transaction currency")),
            clean_str(row.get("Exchange rate")),
            clean_str(row.get("Reference ID")),
            clean_str(row.get("Description")),
            row_to_json(row),
            dedup_key,
        ]
        result = upsert_row(conn, "transactions", columns, values, ["dedup_key"])
        if result == "inserted":
            inserted += 1
        else:
            skipped += 1

    finish_import_run(conn, run_id, inserted, updated, skipped)
    return {"inserted": inserted, "skipped": skipped, "type": "transactions"}


def import_order_lines(conn, path):
    df = load_csv(path, ["Order Number", "Custom Label"], skip_fallback=(2, 3, 4))
    df = df[df["Order Number"].notna()]
    df = df[df["Order Number"].astype(str).str.strip() != ""]
    run_id = start_import_run(conn, "csv", "order_lines", path)
    inserted = skipped = 0

    for _, row in df.iterrows():
        order_num = clean_str(row.get("Order Number")) or ""
        item_num = clean_str(row.get("Item Number")) or ""
        tx_id = clean_str(row.get("Transaction ID")) or ""
        sale_parsed = parse_date_iso(row.get("Sale Date"))
        columns = [
            "source_run_id", "sales_record_number", "order_number", "buyer_username",
            "buyer_name", "item_number", "item_title", "custom_label",
            "sold_via_promoted_listings", "quantity", "sold_for",
            "shipping_and_handling", "total_price", "sale_date", "sale_date_parsed",
            "transaction_id", "raw_json",
        ]
        values = [
            run_id,
            clean_str(row.get("Sales Record Number")),
            order_num,
            clean_str(row.get("Buyer Username")),
            clean_str(row.get("Buyer Name")),
            item_num,
            clean_str(row.get("Item Title")),
            clean_str(row.get("Custom Label")),
            clean_str(row.get("Sold Via Promoted Listings")),
            parse_quantity(row.get("Quantity")),
            parse_money(row.get("Sold For")),
            parse_money(row.get("Shipping And Handling")),
            parse_money(row.get("Total Price")),
            clean_str(row.get("Sale Date")),
            sale_parsed,
            tx_id,
            row_to_json(row),
        ]
        result = upsert_row(
            conn, "order_lines", columns, values,
            ["order_number", "item_number", "transaction_id"],
        )
        if result == "inserted":
            inserted += 1
        else:
            skipped += 1

    finish_import_run(conn, run_id, inserted, 0, skipped)
    return {"inserted": inserted, "skipped": skipped, "type": "order_lines"}


def import_order_earnings(conn, path):
    df = load_csv(path, ["Order creation date", "Order number"])
    run_id = start_import_run(conn, "csv", "order_earnings", path)
    inserted = skipped = 0

    for _, row in df.iterrows():
        order_num = clean_str(row.get("Order number")) or ""
        item_id = clean_str(row.get("Item ID")) or ""
        columns = [
            "source_run_id", "order_creation_date", "order_number", "item_id", "item_title",
            "buyer_name", "ship_to_city", "ship_to_state", "ship_to_zip", "ship_to_country",
            "transaction_currency", "ebay_collected_tax", "item_price", "quantity",
            "item_subtotal", "shipping_and_handling", "seller_collected_tax", "discount",
            "payout_currency", "gross_amount", "final_value_fee_fixed",
            "final_value_fee_variable", "below_standard_fee", "inad_fee", "international_fee",
            "deposit_processing_fee", "regulatory_operating_fee", "promoted_listing_fee",
            "charity_donation", "shipping_labels", "payment_dispute_fee", "expenses",
            "refunds", "order_earnings", "your_cost", "net_order_earnings", "raw_json",
        ]
        values = [
            run_id,
            parse_date_iso(row.get("Order creation date")),
            order_num,
            item_id,
            clean_str(row.get("Item title")),
            clean_str(row.get("Buyer name")),
            clean_str(row.get("Ship to city")),
            clean_str(row.get("Ship to province/region/state")),
            clean_str(row.get("Ship to zip")),
            clean_str(row.get("Ship to country")),
            clean_str(row.get("Transaction currency")),
            parse_money(row.get("eBay collected tax")),
            parse_money(row.get("Item price")),
            parse_quantity(row.get("Quantity")),
            parse_money(row.get("Item subtotal")),
            parse_money(row.get("Shipping and handling")),
            parse_money(row.get("Seller collected tax")),
            parse_money(row.get("Discount")),
            clean_str(row.get("Payout currency")),
            parse_money(row.get("Gross amount")),
            parse_money(row.get("Final Value Fee - fixed")),
            parse_money(row.get("Final Value Fee - variable")),
            parse_money(row.get("Below standard performance fee")),
            parse_money(row.get('Very high "item not as described" fee')),
            parse_money(row.get("International fee")),
            parse_money(row.get("Deposit processing fee")),
            parse_money(row.get("Regulatory operating fee")),
            parse_money(row.get("Promoted Listing Standard fee")),
            parse_money(row.get("Charity donation")),
            parse_money(row.get("Shipping labels")),
            parse_money(row.get("Payment Dispute Fee")),
            parse_money(row.get("Expenses")),
            parse_money(row.get("Refunds")),
            parse_money(row.get("Order earnings")),
            parse_money(row.get("Your cost")),
            parse_money(row.get("Net order earnings")),
            row_to_json(row),
        ]
        result = upsert_row(conn, "order_earnings", columns, values, ["order_number", "item_id"])
        if result == "inserted":
            inserted += 1
        else:
            skipped += 1

    finish_import_run(conn, run_id, inserted, 0, skipped)
    return {"inserted": inserted, "skipped": skipped, "type": "order_earnings"}


def import_tax_invoice_lines(conn, path):
    invoice_month = invoice_month_from_filename(path)
    if not invoice_month:
        raise ValueError(f"Could not determine invoice month from {path.name}")
    df = load_csv(path, ["Date,Description", "Fee type"], skip_fallback=(5, 6))
    run_id = start_import_run(conn, "csv", "tax_invoice_lines", path)
    inserted = skipped = 0

    for _, row in df.iterrows():
        fee_type = clean_str(row.get("Fee type")) or ""
        order_num = clean_str(row.get("Order number")) or ""
        item_num = clean_str(row.get("Item number")) or ""
        line_date = clean_str(row.get("Date"))
        memo = clean_str(row.get("Memo")) or ""
        columns = [
            "source_run_id", "invoice_month", "line_date", "description", "memo",
            "order_number", "item_number", "fee_group", "fee_type", "currency",
            "net_amount", "tax_pct", "tax_amount", "total_amount", "charged_by_entity",
            "raw_json",
        ]
        values = [
            run_id,
            invoice_month,
            line_date,
            clean_str(row.get("Description")),
            memo,
            order_num,
            item_num,
            clean_str(row.get("Fee group")),
            fee_type,
            clean_str(row.get("Currency")),
            parse_money(row.get("Net amount")),
            clean_str(row.get("Tax (%)")),
            parse_money(row.get("Tax amount")),
            parse_money(row.get("Total amount")),
            clean_str(row.get("Charged by Entity")),
            row_to_json(row),
        ]
        result = upsert_row(
            conn, "tax_invoice_lines", columns, values,
            ["invoice_month", "line_date", "order_number", "item_number", "fee_type", "memo"],
        )
        if result == "inserted":
            inserted += 1
        else:
            skipped += 1

    finish_import_run(conn, run_id, inserted, 0, skipped)
    return {"inserted": inserted, "skipped": skipped, "type": "tax_invoice_lines"}


def import_promoted_listing_fees(conn, path):
    df = load_csv(path, ["Start date", "Item ID"], skip_fallback=(2, 3))
    run_id = start_import_run(conn, "csv", "promoted_listing_fees", path)
    inserted = skipped = 0

    for _, row in df.iterrows():
        listing_id = clean_str(row.get("Item ID")) or ""
        report_start = parse_date_iso(row.get("Start date")) or ""
        report_end = parse_date_iso(row.get("End date")) or ""
        campaign_id = clean_str(row.get("Campaign ID")) or ""
        columns = [
            "source_run_id", "report_start", "report_end", "campaign_name", "campaign_id",
            "listing_id", "title", "listing_format", "price", "quantity_available",
            "promoted_impressions", "promoted_clicks", "promoted_sold_qty",
            "organic_sold_qty", "total_sold_qty", "promoted_sales", "ad_fees",
            "return_on_ad_spend", "raw_json",
        ]
        values = [
            run_id,
            report_start,
            report_end,
            clean_str(row.get("Campaign name")),
            campaign_id,
            listing_id,
            clean_str(row.get("Title")),
            clean_str(row.get("Listing format")),
            parse_money(row.get("Price (Current or Last Price)")),
            parse_quantity(row.get("Quantity available")),
            parse_quantity(row.get("Promoted Listings Impressions (via eBay Placements)")),
            parse_quantity(row.get("Total Promoted Listings Clicks")),
            parse_quantity(row.get("Total Promoted Listings Sold quantity")),
            parse_quantity(row.get("Organic Sold Quantity")),
            parse_quantity(row.get("Total Quantity Sold")),
            parse_money(row.get("Total Promoted Listings Sales (in billing currency)")),
            parse_money(row.get("Ad fees (in billing currency)")),
            parse_money(row.get("Return on Ad spend (Sales/Ad fees)")),
            row_to_json(row),
        ]
        result = upsert_row(
            conn, "promoted_listing_fees", columns, values,
            ["listing_id", "report_start", "report_end", "campaign_id"],
        )
        if result == "inserted":
            inserted += 1
        else:
            skipped += 1

    finish_import_run(conn, run_id, inserted, 0, skipped)
    return {"inserted": inserted, "skipped": skipped, "type": "promoted_listing_fees"}


IMPORTERS = {
    "transactions": import_transactions,
    "order_lines": import_order_lines,
    "order_earnings": import_order_earnings,
    "tax_invoice_lines": import_tax_invoice_lines,
    "promoted_listing_fees": import_promoted_listing_fees,
}


def import_file(conn, path):
    file_type = detect_file_type(path)
    if not file_type:
        return None
    return IMPORTERS[file_type](conn, path)


def collect_files(directories, file_type=None):
    files = []
    seen = set()
    for directory in directories:
        directory = Path(directory)
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.csv")):
            if " (1)" in path.name:
                continue
            detected = detect_file_type(path)
            if detected is None:
                continue
            if file_type and detected != file_type:
                continue
            key = (detected, path.name)
            if key in seen:
                continue
            seen.add(key)
            files.append(path)
    return files


def main():
    parser = argparse.ArgumentParser(description="Import eBay CSV files into SQLite")
    parser.add_argument("--all", action="store_true", help="Import all CSVs in financials/f-bargarage")
    parser.add_argument("--file", help="Import a single CSV file")
    parser.add_argument("--type", choices=list(IMPORTERS.keys()), help="Filter by data type when using --all")
    parser.add_argument("--dir", action="append", help="Financials directory (repeatable)")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Database path")
    args = parser.parse_args()

    init_schema(args.db)

    if args.file:
        paths = [Path(args.file)]
    elif args.all:
        directories = [Path(d) for d in args.dir] if args.dir else IMPORT_DIRS
        paths = collect_files(directories, args.type)
    else:
        parser.error("Specify --all or --file")

    summaries = []
    with db_session(args.db) as conn:
        for path in paths:
            print(f"Importing {path.name}...")
            try:
                summary = import_file(conn, path)
                if summary:
                    summaries.append(summary)
                    print(f"  {summary['type']}: inserted={summary['inserted']} skipped={summary['skipped']}")
                else:
                    print("  Skipped (unknown file type)")
            except Exception as exc:
                print(f"  ERROR: {exc}", file=sys.stderr)

    print("\nImport complete.")
    for table in IMPORTERS:
        with db_session(args.db) as conn:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: {count} rows")


if __name__ == "__main__":
    main()
