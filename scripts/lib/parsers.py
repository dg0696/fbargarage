"""Shared parsing helpers for eBay financial data."""

import json
import re
from pathlib import Path

import pandas as pd


def find_header_row(file_path, markers, max_rows=30):
    with open(file_path, "r", encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            if i >= max_rows:
                break
            if any(marker in line for marker in markers):
                return i
    return None


def parse_date(value):
    if pd.isna(value) or value in ("--", "", None):
        return None
    text = str(value).strip()
    formats = [
        "%b %d, %Y",
        "%B %d, %Y",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%b-%d-%y",
    ]
    for fmt in formats:
        try:
            return pd.to_datetime(text, format=fmt)
        except ValueError:
            continue
    try:
        return pd.to_datetime(text)
    except (ValueError, TypeError):
        return None


def parse_date_iso(value):
    parsed = parse_date(value)
    if parsed is None or pd.isna(parsed):
        return None
    return parsed.strftime("%Y-%m-%d")


def parse_money(value):
    if pd.isna(value) or value in ("--", "", None):
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    text = re.sub(r"^\s*USD\s*", "", text, flags=re.IGNORECASE).strip()
    try:
        return float(text)
    except ValueError:
        return None


def parse_quantity(value):
    parsed = parse_money(value)
    if parsed is None:
        return None
    return parsed


def clean_str(value):
    if pd.isna(value) or value in ("--", ""):
        return None
    return str(value).strip()


def row_to_json(row):
    return json.dumps({k: (None if pd.isna(v) else v) for k, v in row.items()}, default=str)


def invoice_month_from_filename(path):
    match = re.search(r"2745279534_(\d{4})-(\d{1,2})\.csv", Path(path).name, re.IGNORECASE)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}"
    return None
