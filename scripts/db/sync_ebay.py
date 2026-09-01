#!/usr/bin/env python3
"""Sync eBay seller data from REST APIs into SQLite."""

import argparse
import calendar
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.db.connection import DEFAULT_DB_PATH, db_session, init_schema
from scripts.db.import_csv import finish_import_run, start_import_run, upsert_row
from scripts.lib.ebay_client import EbayClient
from scripts.lib.parsers import clean_str, parse_date_iso, parse_money


def month_bounds(year, month):
    last_day = calendar.monthrange(year, month)[1]
    start = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    start_filter = start.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    end_filter = end.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return start_filter, end_filter


def transaction_dedup_key(values):
    parts = [
        values.get("transaction_date") or "",
        values.get("type") or "",
        values.get("order_number") or "",
        values.get("transaction_id") or "",
        values.get("item_id") or "",
        values.get("description") or "",
        str(values.get("net_amount") or ""),
        str(values.get("gross_transaction_amount") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def map_finances_transaction(tx, run_id):
    order_id = clean_str((tx.get("orderId") or tx.get("order_id")))
    booking_entry = tx.get("bookingEntry", "")
    tx_type = booking_entry or clean_str(tx.get("transactionType")) or "Unknown"
    amount = tx.get("amount", {})
    net_amount = parse_money(amount.get("value"))
    order_line = (tx.get("orderLineItems") or [{}])[0] if tx.get("orderLineItems") else {}
    fees = tx.get("totalFeeAmount", {})
    values = {
        "source_run_id": run_id,
        "transaction_date": parse_date_iso(tx.get("transactionDate")),
        "type": tx_type,
        "order_number": order_id or "--",
        "legacy_order_id": order_id,
        "buyer_username": clean_str(tx.get("buyer", {}).get("username")),
        "buyer_name": None,
        "ship_to_city": None,
        "ship_to_state": None,
        "ship_to_zip": None,
        "ship_to_country": None,
        "net_amount": net_amount,
        "payout_currency": clean_str(amount.get("currency")),
        "payout_date": parse_date_iso(tx.get("payoutDate")),
        "payout_id": clean_str(tx.get("payoutId")),
        "payout_method": None,
        "payout_status": None,
        "reason_for_hold": None,
        "item_id": clean_str(order_line.get("lineItemId") or tx.get("itemId")),
        "transaction_id": clean_str(tx.get("transactionId")) or "",
        "item_title": clean_str(order_line.get("title")),
        "custom_label": clean_str(order_line.get("sku") or order_line.get("legacyItemId")),
        "quantity": parse_money(order_line.get("quantity")),
        "item_subtotal": parse_money(order_line.get("lineItemAmount", {}).get("value")),
        "shipping_and_handling": None,
        "seller_collected_tax": None,
        "ebay_collected_tax": None,
        "final_value_fee_fixed": None,
        "final_value_fee_variable": parse_money(fees.get("value")),
        "regulatory_operating_fee": None,
        "inad_fee": None,
        "below_standard_fee": None,
        "international_fee": None,
        "charity_donation": None,
        "deposit_processing_fee": None,
        "promoted_listing_fee": None,
        "gross_transaction_amount": parse_money(tx.get("totalAmount", {}).get("value")),
        "transaction_currency": clean_str(amount.get("currency")),
        "exchange_rate": None,
        "reference_id": clean_str(tx.get("referenceId")),
        "description": clean_str(tx.get("transactionMemo")),
        "raw_json": json.dumps(tx),
    }
    values["dedup_key"] = transaction_dedup_key(values)
    return values


def map_fulfillment_line(order, line, run_id):
    pricing = line.get("lineItemCost", {})
    delivery = line.get("deliveryCost", {})
    total = line.get("total", {})
    sale_date = parse_date_iso(order.get("creationDate"))
    values = {
        "source_run_id": run_id,
        "sales_record_number": None,
        "order_number": clean_str(order.get("orderId")) or "",
        "buyer_username": clean_str(order.get("buyer", {}).get("username")),
        "buyer_name": clean_str(order.get("buyer", {}).get("fullName")),
        "item_number": clean_str(line.get("legacyItemId") or line.get("lineItemId")) or "",
        "item_title": clean_str(line.get("title")),
        "custom_label": clean_str(line.get("sku")),
        "sold_via_promoted_listings": None,
        "quantity": parse_money(line.get("quantity")),
        "sold_for": parse_money(pricing.get("value")),
        "shipping_and_handling": parse_money(delivery.get("shippingCost", {}).get("value")),
        "total_price": parse_money(total.get("value")),
        "sale_date": clean_str(order.get("creationDate")),
        "sale_date_parsed": sale_date,
        "transaction_id": clean_str(line.get("lineItemId")) or "",
        "raw_json": json.dumps({"order": order, "line": line}),
    }
    return values


def upsert_transaction(conn, values):
    columns = list(values.keys())
    upsert_row(conn, "transactions", columns, list(values.values()), ["dedup_key"])


def upsert_order_line(conn, values):
    columns = list(values.keys())
    upsert_row(
        conn,
        "order_lines",
        columns,
        list(values.values()),
        ["order_number", "item_number", "transaction_id"],
    )


def sync_transactions(client, conn, year, month):
    start_filter, end_filter = month_bounds(year, month)
    run_id = start_import_run(conn, "api", "transactions", None)
    conn.execute(
        "UPDATE import_runs SET api_endpoint = ? WHERE id = ?",
        (f"/sell/finances/v1/transaction?{start_filter}..{end_filter}", run_id),
    )
    inserted = skipped = 0
    try:
        items = client.paginate_get(
            "/sell/finances/v1/transaction",
            {
                "filter": f"transactionDate:[{start_filter}..{end_filter}]",
                "limit": 200,
            },
            results_key="transactions",
        )
        for tx in items:
            values = map_finances_transaction(tx, run_id)
            before = conn.total_changes
            upsert_transaction(conn, values)
            if conn.total_changes > before:
                inserted += 1
            else:
                skipped += 1
        finish_import_run(conn, run_id, inserted, 0, skipped)
        conn.execute(
            """
            INSERT INTO sync_state (data_type, last_sync_at, last_sync_cursor)
            VALUES ('transactions', datetime('now'), ?)
            ON CONFLICT(data_type) DO UPDATE SET
                last_sync_at = excluded.last_sync_at,
                last_sync_cursor = excluded.last_sync_cursor
            """,
            (f"{year:04d}-{month:02d}",),
        )
        return inserted, skipped
    except Exception as exc:
        finish_import_run(conn, run_id, inserted, 0, skipped, status="failed", error_message=str(exc))
        raise


def sync_orders(client, conn, year, month):
    start_filter, end_filter = month_bounds(year, month)
    run_id = start_import_run(conn, "api", "order_lines", None)
    conn.execute(
        "UPDATE import_runs SET api_endpoint = ? WHERE id = ?",
        (f"/sell/fulfillment/v1/order?{start_filter}..{end_filter}", run_id),
    )
    inserted = skipped = 0
    try:
        orders = client.paginate_get(
            "/sell/fulfillment/v1/order",
            {
                "filter": f"creationdate:[{start_filter}..{end_filter}]",
                "limit": 50,
            },
            results_key="orders",
        )
        for order in orders:
            for line in order.get("lineItems", []):
                values = map_fulfillment_line(order, line, run_id)
                before = conn.total_changes
                upsert_order_line(conn, values)
                if conn.total_changes > before:
                    inserted += 1
                else:
                    skipped += 1
        finish_import_run(conn, run_id, inserted, 0, skipped)
        conn.execute(
            """
            INSERT INTO sync_state (data_type, last_sync_at, last_sync_cursor)
            VALUES ('order_lines', datetime('now'), ?)
            ON CONFLICT(data_type) DO UPDATE SET
                last_sync_at = excluded.last_sync_at,
                last_sync_cursor = excluded.last_sync_cursor
            """,
            (f"{year:04d}-{month:02d}",),
        )
        return inserted, skipped
    except Exception as exc:
        finish_import_run(conn, run_id, inserted, 0, skipped, status="failed", error_message=str(exc))
        raise


def parse_month(value):
    year, month = value.split("-")
    return int(year), int(month)


def main():
    parser = argparse.ArgumentParser(description="Sync eBay seller data into SQLite")
    parser.add_argument("--month", help="Sync month as YYYY-MM")
    parser.add_argument("--since", help="Sync from date YYYY-MM-DD through today")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()

    init_schema(args.db)
    client = EbayClient()

    if args.month:
        year, month = parse_month(args.month)
        months = [(year, month)]
    elif args.since:
        start = datetime.strptime(args.since, "%Y-%m-%d")
        now = datetime.now()
        months = []
        cursor = datetime(start.year, start.month, 1)
        while (cursor.year, cursor.month) <= (now.year, now.month):
            months.append((cursor.year, cursor.month))
            if cursor.month == 12:
                cursor = datetime(cursor.year + 1, 1, 1)
            else:
                cursor = datetime(cursor.year, cursor.month + 1, 1)
    else:
        parser.error("Specify --month YYYY-MM or --since YYYY-MM-DD")

    with db_session(args.db) as conn:
        for year, month in months:
            print(f"Syncing {year:04d}-{month:02d}...")
            try:
                tx_inserted, tx_skipped = sync_transactions(client, conn, year, month)
                order_inserted, order_skipped = sync_orders(client, conn, year, month)
                print(
                    f"  transactions: inserted={tx_inserted} skipped={tx_skipped}; "
                    f"order_lines: inserted={order_inserted} skipped={order_skipped}"
                )
            except Exception as exc:
                print(f"  ERROR: {exc}", file=sys.stderr)
                sys.exit(1)

    print("Sync complete.")


if __name__ == "__main__":
    main()
