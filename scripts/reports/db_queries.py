"""Load report data from SQLite as pandas DataFrames."""

import pandas as pd

TRANSACTION_COLUMN_MAP = {
    "transaction_date": "Transaction creation date",
    "type": "Type",
    "order_number": "Order number",
    "legacy_order_id": "Legacy order ID",
    "buyer_username": "Buyer username",
    "buyer_name": "Buyer name",
    "ship_to_city": "Ship to city",
    "ship_to_state": "Ship to province/region/state",
    "ship_to_zip": "Ship to zip",
    "ship_to_country": "Ship to country",
    "net_amount": "Net amount",
    "payout_currency": "Payout currency",
    "payout_date": "Payout date",
    "payout_id": "Payout ID",
    "payout_method": "Payout method",
    "payout_status": "Payout status",
    "reason_for_hold": "Reason for hold",
    "item_id": "Item ID",
    "transaction_id": "Transaction ID",
    "item_title": "Item title",
    "custom_label": "Custom label",
    "quantity": "Quantity",
    "item_subtotal": "Item subtotal",
    "shipping_and_handling": "Shipping and handling",
    "seller_collected_tax": "Seller collected tax",
    "ebay_collected_tax": "eBay collected tax",
    "final_value_fee_fixed": "Final Value Fee - fixed",
    "final_value_fee_variable": "Final Value Fee - variable",
    "regulatory_operating_fee": "Regulatory operating fee",
    "inad_fee": 'Very high "item not as described" fee',
    "below_standard_fee": "Below standard performance fee",
    "international_fee": "International fee",
    "charity_donation": "Charity donation",
    "deposit_processing_fee": "Deposit processing fee",
    "promoted_listing_fee": "Promoted Listing Standard fee",
    "gross_transaction_amount": "Gross transaction amount",
    "transaction_currency": "Transaction currency",
    "exchange_rate": "Exchange rate",
    "reference_id": "Reference ID",
    "description": "Description",
}


def load_transactions(conn, year, month=None, sku_prefix=None, order_type="Order"):
    sql = """
        SELECT * FROM transactions
        WHERE type = ?
          AND strftime('%Y', transaction_date) = ?
    """
    params = [order_type, f"{year:04d}"]
    if month is not None:
        sql += " AND strftime('%m', transaction_date) = ?"
        params.append(f"{month:02d}")
    if sku_prefix:
        sql += " AND custom_label LIKE ?"
        params.append(f"{sku_prefix}%")
    sql += " ORDER BY transaction_date"
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(row) for row in rows])
    df = df.rename(columns=TRANSACTION_COLUMN_MAP)
    return df


def load_order_lines(conn, year, month):
    sql = """
        SELECT * FROM order_lines
        WHERE sale_date_parsed IS NOT NULL
          AND strftime('%Y', sale_date_parsed) = ?
          AND strftime('%m', sale_date_parsed) = ?
        ORDER BY sale_date_parsed
    """
    rows = conn.execute(sql, (f"{year:04d}", f"{month:02d}")).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(row) for row in rows])
    df = df.rename(
        columns={
            "order_number": "Order Number",
            "buyer_username": "Buyer Username",
            "buyer_name": "Buyer Name",
            "item_number": "Item Number",
            "item_title": "Item Title",
            "custom_label": "Custom Label",
            "sold_via_promoted_listings": "Sold Via Promoted Listings",
            "quantity": "Quantity",
            "sold_for": "Sold For",
            "shipping_and_handling": "Shipping And Handling",
            "total_price": "Total Price",
            "sale_date": "Sale Date",
            "sale_date_parsed": "Sale Date Parsed",
            "transaction_id": "Transaction ID",
        }
    )
    df["Sold For Num"] = pd.to_numeric(df["Sold For"], errors="coerce").fillna(0)
    df["Shipping And Handling Num"] = pd.to_numeric(df["Shipping And Handling"], errors="coerce").fillna(0)
    df["Total Price Num"] = pd.to_numeric(df["Total Price"], errors="coerce").fillna(0)
    df["Quantity Num"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0)
    df["Sale Date Parsed"] = pd.to_datetime(df["Sale Date Parsed"], errors="coerce")
    return df
