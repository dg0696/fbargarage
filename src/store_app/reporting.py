"""Monthly financial reports (same files as scripts/run_monthly_reports.py)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports"
SQLITE_PATH = REPO_ROOT / "db" / "ebay_store.db"
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+\.txt$")

REPORT_SPECS = (
    ("all-orders-summary", "Store all-orders summary", "f-bargarage_{ym}_all-orders_summary.txt"),
    ("all-orders-report", "Store all-orders report", "f-bargarage_{ym}_all-orders_report.txt"),
    ("sku-orders-summary", "SKU G all-orders summary", "sku_G_{ym}_all-orders_summary.txt"),
    ("sku-orders-report", "SKU G all-orders report", "sku_G_{ym}_all-orders_report.txt"),
    ("sku-tx-summary", "SKU G transactions summary", "sku_G_{ym}_report_summary.txt"),
    ("sku-tx-report", "SKU G transactions report", "sku_G_{ym}_report.txt"),
)


def ym_label(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def sqlite_ready() -> bool:
    return SQLITE_PATH.is_file() and SQLITE_PATH.stat().st_size > 0


def month_files(year: int, month: int) -> list[dict[str, Any]]:
    ym = ym_label(year, month)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for key, label, pattern in REPORT_SPECS:
        name = pattern.format(ym=ym)
        path = REPORTS_DIR / name
        rows.append(
            {
                "key": key,
                "label": label,
                "name": name,
                "exists": path.is_file(),
            }
        )
    return rows


def list_months() -> list[str]:
    found: set[str] = set()
    if REPORTS_DIR.is_dir():
        for path in REPORTS_DIR.glob("f-bargarage_*_all-orders_summary.txt"):
            match = re.search(r"(\d{4}-\d{2})", path.name)
            if match:
                found.add(match.group(1))
    return sorted(found, reverse=True)


def read_report(name: str) -> str:
    if not SAFE_NAME.match(name) or ".." in name:
        raise ValueError("Invalid report name")
    path = (REPORTS_DIR / name).resolve()
    if path.parent != REPORTS_DIR.resolve() or not path.is_file():
        raise FileNotFoundError(name)
    return path.read_text(encoding="utf-8", errors="replace")


def generate_month(year: int, month: int) -> list[str]:
    if year < 2020 or year > date.today().year + 1 or month < 1 or month > 12:
        raise ValueError("Invalid year or month")
    if not sqlite_ready():
        raise RuntimeError("SQLite financials missing (db/ebay_store.db). Import CSVs first.")
    import contextlib
    import io

    from run_monthly_reports import run_db_reports

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return run_db_reports(year, month, "G", SQLITE_PATH)
