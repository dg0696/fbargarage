# Reporting Guide

**Audience:** Operations (primary); Developer (secondary)  
**Audiences:** operations, developer  
**Status:** Active  
**Doc-reviewed:** 2026-08-31  
**Summary:** How to generate, validate, and print monthly f-bargarage eBay store reports from SQLite or CSV.

---

This document describes how monthly financial reports are generated, validated, and printed for the f-bargarage eBay store.

## Report Types

Each month can produce up to three report pairs (summary + full report):

| Report | Files | Source data |
|--------|-------|-------------|
| Store all-orders | `f-bargarage_YYYY-MM_all-orders_summary.txt` / `_report.txt` | All orders for the month |
| SKU G all-orders | `sku_G_YYYY-MM_all-orders_summary.txt` / `_report.txt` | Orders with SKU prefix `G` |
| SKU G transactions | `sku_G_YYYY-MM_report_summary.txt` / `_report.txt` | Order-type rows from transaction report |

SKU transaction reports are omitted when there are no G-SKU orders in that month (for example, March 2026).

## Recommended Workflow

### 1. Initialize database (first time)

```bash
python scripts/db/init_db.py
python scripts/db/import_csv.py --all
```

Place new eBay CSV exports in `financials/f-bargarage/` before importing.

### 2. Sync from eBay API (optional, production OAuth required)

```powershell
.\scripts\ebay_user_oauth.ps1
python scripts/db/sync_ebay.py --month 2026-06
```

See `.env.example` for required credentials.

### 3. Generate monthly reports

From the database (default):

```powershell
python scripts/run_monthly_reports.py --year 2026 --month 6 --from-db
```

From CSV exports (legacy path):

```powershell
python scripts/run_monthly_reports.py --year 2026 --month 6 --from-csv
```

Reports are written to `reports/`.

### 4. Validate CSV vs DB parity

After importing CSVs or syncing from the API, confirm DB-backed reports match the legacy CSV scripts:

```powershell
python scripts/reports/compare_reports.py --year 2026 --start-month 1 --end-month 5
```

The script compares summary metrics and full report text (ignoring source path and timestamp lines).

## Summary File Format

All-orders summaries include:

```
Orders: N
Total Quantity: N
Total Sold For: USD X.XX
Total Shipping And Handling: USD X.XX
Total Price: USD X.XX
```

SKU transaction summaries include item-level fee breakdowns and an overall financial summary with gross revenue, fees, net amount, and payout (70% of net profit).

## Printing Reports (Windows)

Print summary and report files to the Brother printer:

```powershell
$printer = "Brother HL-3170CDW series"
$base = "Z:\gitrepos\fbargarage\reports"
@(
  "f-bargarage_2026-03_all-orders_summary.txt",
  "f-bargarage_2026-03_all-orders_report.txt"
) | ForEach-Object {
  Get-Content (Join-Path $base $_) -Raw | Out-Printer -Name $printer
}
```

List installed printers with `Get-Printer`.

## Script Reference

| Script | Purpose |
|--------|---------|
| `scripts/run_monthly_reports.py` | Orchestrates all monthly reports |
| `scripts/analyze_sku_financials.py` | Legacy SKU transaction report from CSV |
| `scripts/analyze_all_orders.py` | Legacy all-orders report from CSV |
| `scripts/reports/sku_transaction_report.py` | SKU transaction report from SQLite |
| `scripts/reports/all_orders_report.py` | All-orders report from SQLite |
| `scripts/reports/compare_reports.py` | CSV vs DB parity validation |
| `scripts/db/import_csv.py` | Import financial CSVs into SQLite |
| `scripts/db/sync_ebay.py` | Sync seller data from eBay REST APIs |

## Data Locations

- Source CSVs: `financials/f-bargarage/`
- SQLite schema: `db/schema.sql`
- Local database: `db/ebay_store.db` (gitignored)
- Generated reports: `reports/`

See [DATA_STRUCTURE.md](DATA_STRUCTURE.md) for CSV column details and [README.md](../README.md) for setup.
