#!/usr/bin/env python3
"""Generate all-orders summary reports from eBay all-orders CSV exports."""

import argparse
import re
from datetime import datetime
from pathlib import Path

import pandas as pd


MONTH_NAMES = {
    1: "JANUARY",
    2: "FEBRUARY",
    3: "MARCH",
    4: "APRIL",
    5: "MAY",
    6: "JUNE",
    7: "JULY",
    8: "AUGUST",
    9: "SEPTEMBER",
    10: "OCTOBER",
    11: "NOVEMBER",
    12: "DECEMBER",
}


def find_header_row(file_path, max_rows=5):
    with open(file_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= max_rows:
                break
            if "Order Number" in line and "Custom Label" in line:
                return i
    return 2


def parse_money(value):
    if pd.isna(value) or value == "" or value == "--":
        return 0.0
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_sale_date(value):
    if pd.isna(value) or value == "":
        return pd.NaT
    text = str(value).strip()
    for fmt in ("%b-%d-%y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return pd.to_datetime(text, format=fmt)
        except ValueError:
            continue
    return pd.to_datetime(text, errors="coerce")


def load_all_orders(file_path):
    header_row = find_header_row(file_path)
    df = pd.read_csv(file_path, skiprows=header_row, low_memory=False)
    df.columns = df.columns.str.strip()
    df = df[df["Order Number"].notna()].copy()
    df = df[df["Order Number"].astype(str).str.strip() != ""]
    return df


def enrich_orders(df):
    df = df.copy()
    df["Sold For Num"] = df["Sold For"].map(parse_money)
    df["Shipping And Handling Num"] = df["Shipping And Handling"].map(parse_money)
    df["Total Price Num"] = df["Total Price"].map(parse_money)
    df["Quantity Num"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0)
    df["Sale Date Parsed"] = df["Sale Date"].map(parse_sale_date)
    return df


def filter_month(df, year, month):
    filtered = df[df["Sale Date Parsed"].notna()].copy()
    filtered = filtered[
        (filtered["Sale Date Parsed"].dt.year == year)
        & (filtered["Sale Date Parsed"].dt.month == month)
    ]
    return filtered


def build_summary_lines(df, title, input_file, sku_prefix=None):
    if sku_prefix:
        working = df[
            df["Custom Label"].notna()
            & df["Custom Label"].astype(str).str.startswith(sku_prefix, na=False)
        ].copy()
    else:
        working = df.copy()

    lines = []
    lines.append(title)
    lines.append("=" * len(title))
    lines.append(f"Input: {input_file}")
    lines.append(f"Orders: {working['Order Number'].nunique()}")
    lines.append(f"Total Quantity: {int(working['Quantity Num'].sum())}")
    lines.append(f"Total Sold For: USD {working['Sold For Num'].sum():.2f}")
    lines.append(
        f"Total Shipping And Handling: USD {working['Shipping And Handling Num'].sum():.2f}"
    )
    lines.append(f"Total Price: USD {working['Total Price Num'].sum():.2f}")
    lines.append("")

    lines.append("BY SKU")
    lines.append("-" * 70)
    sku_summary = (
        working.groupby("Custom Label", dropna=False)
        .agg(
            Orders=("Order Number", "nunique"),
            Quantity=("Quantity Num", "sum"),
            Sold_For=("Sold For Num", "sum"),
            Shipping=("Shipping And Handling Num", "sum"),
            Total_Price=("Total Price Num", "sum"),
        )
        .sort_values("Sold_For", ascending=False)
    )
    lines.append(
        f"{'Custom Label':14} {'Orders':>6} {'Quantity':>8} "
        f"{'Sold For':>10} {'Shipping And Handling':>22} {'Total Price':>12}"
    )
    for sku, row in sku_summary.iterrows():
        label = str(sku) if pd.notna(sku) else "(blank)"
        lines.append(
            f"{label:14} {int(row['Orders']):>6} {int(row['Quantity']):>8} "
            f"{row['Sold_For']:>10.2f} {row['Shipping']:>22.2f} {row['Total_Price']:>12.2f}"
        )
    lines.append("")

    lines.append("BY DAY")
    lines.append("-" * 70)
    day_summary = (
        working.groupby(working["Sale Date Parsed"].dt.date)
        .agg(Orders=("Order Number", "nunique"), Total_Price=("Total Price Num", "sum"))
        .sort_index()
    )
    lines.append(f"{'Sale Date Parsed':18} {'Orders':>8} {'Total Price':>12}")
    for day, row in day_summary.iterrows():
        lines.append(f"{day} {int(row['Orders']):>8} {row['Total_Price']:>12.2f}")

    return lines, working


def build_sku_detail_lines(working, title, input_file):
    lines = []
    lines.append(title)
    lines.append("=" * 72)
    lines.append(f"Input: {input_file}")
    lines.append(f"Orders: {working['Order Number'].nunique()}")
    lines.append(f"Total Quantity: {int(working['Quantity Num'].sum())}")
    lines.append(f"Total Sold For: USD {working['Sold For Num'].sum():.2f}")
    lines.append(
        f"Total Shipping And Handling: USD {working['Shipping And Handling Num'].sum():.2f}"
    )
    lines.append(f"Total Price: USD {working['Total Price Num'].sum():.2f}")
    lines.append("")

    lines.append("BY SKU")
    lines.append("-" * 72)
    sku_summary = (
        working.groupby("Custom Label", dropna=False)
        .agg(
            Orders=("Order Number", "nunique"),
            Quantity=("Quantity Num", "sum"),
            Sold_For=("Sold For Num", "sum"),
            Shipping=("Shipping And Handling Num", "sum"),
            Total_Price=("Total Price Num", "sum"),
        )
        .sort_values("Sold_For", ascending=False)
    )
    lines.append(
        f"{'Custom Label':14} {'Orders':>6} {'Quantity':>8} "
        f"{'Sold For':>10} {'Shipping And Handling':>22} {'Total Price':>12}"
    )
    for sku, row in sku_summary.iterrows():
        label = str(sku) if pd.notna(sku) else "(blank)"
        lines.append(
            f"{label:14} {int(row['Orders']):>6} {int(row['Quantity']):>8} "
            f"{row['Sold_For']:>10.2f} {row['Shipping']:>22.2f} {row['Total_Price']:>12.2f}"
        )
    lines.append("")

    lines.append("DETAIL")
    lines.append("-" * 72)
    detail_cols = [
        "Order Number",
        "Sale Date",
        "Sale Date Parsed",
        "Item Title",
        "Custom Label",
        "Quantity",
        "Sold For",
        "Shipping And Handling",
        "Total Price",
        "Sold Via Promoted Listings",
    ]
    detail = working[detail_cols].copy()
    detail["Sale Date Parsed"] = detail["Sale Date Parsed"].dt.strftime("%Y-%m-%d")
    lines.append(
        "  ".join(
            [
                "Order Number",
                "Sale Date",
                "Sale Date Parsed",
                "Item Title",
                "Custom Label",
                "Quantity",
                "Sold For",
                "Shipping And Handling",
                "Total Price",
                "Sold Via Promoted Listings",
            ]
        )
    )
    for _, row in detail.sort_values("Sale Date Parsed").iterrows():
        title = str(row["Item Title"]).replace("\n", " ")
        lines.append(
            f"{row['Order Number']} {row['Sale Date']} {row['Sale Date Parsed']} "
            f"{title} {row['Custom Label']} {int(parse_money(row['Quantity']))} "
            f"{parse_money(row['Sold For']):.2f} "
            f"{parse_money(row['Shipping And Handling']):.2f} "
            f"{parse_money(row['Total Price']):.2f} {row['Sold Via Promoted Listings']}"
        )

    return lines


def write_report(path, lines):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {path}")


def month_label(year, month):
    return f"{MONTH_NAMES[month]} {year}"


def default_paths(year, month, sku_prefix=None):
    ym = f"{year:04d}-{month:02d}"
    base = f"reports/f-bargarage_{ym}_all-orders"
    sku_base = f"reports/sku_{sku_prefix}_{ym}_all-orders" if sku_prefix else None
    return base, sku_base


def main():
    parser = argparse.ArgumentParser(description="Generate all-orders summary reports")
    parser.add_argument("--input-file", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--store-name", default="f-bargarage")
    parser.add_argument("--sku-prefix", default=None)
    parser.add_argument("--output-report", default=None)
    parser.add_argument("--output-summary", default=None)
    parser.add_argument("--output-data", default=None)
    args = parser.parse_args()

    input_file = Path(args.input_file)
    df = enrich_orders(load_all_orders(input_file))
    month_df = filter_month(df, args.year, args.month)
    if len(month_df) == 0:
        print(f"No orders found for {args.year}-{args.month:02d} in {input_file}")
        return

    label = month_label(args.year, args.month)
    store_title = f"{label} ALL-ORDERS REPORT ({args.store_name})"
    store_lines, _ = build_summary_lines(month_df, store_title, str(input_file))
    base_report, sku_base = default_paths(args.year, args.month, args.sku_prefix)
    write_report(args.output_report or f"{base_report}_report.txt", store_lines)
    write_report(args.output_summary or f"{base_report}_summary.txt", store_lines[:9])

    if args.sku_prefix:
        sku_df = month_df[
            month_df["Custom Label"].notna()
            & month_df["Custom Label"].astype(str).str.startswith(args.sku_prefix, na=False)
        ]
        sku_title = f"SKU_{args.sku_prefix} REPORT (FROM ALL-ORDERS) - {label.title()}"
        sku_lines = build_sku_detail_lines(sku_df, sku_title, str(input_file))
        write_report(f"{sku_base}_report.txt", sku_lines)
        write_report(f"{sku_base}_summary.txt", sku_lines[:9])

        export_path = Path(args.output_data or f"{sku_base}_data.csv")
        export_path.parent.mkdir(parents=True, exist_ok=True)
        sku_df.to_csv(export_path, index=False)
        print(f"Wrote {export_path}")


if __name__ == "__main__":
    main()
