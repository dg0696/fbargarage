# Data Structure Documentation

**Audience:** Developer (primary); Operations (secondary)  
**Audiences:** developer, operations  
**Status:** Active  
**Doc-reviewed:** 2026-08-31  
**Summary:** Layout and formats of local eBay financial CSVs, HTML exports, and the SQLite schema. Those files stay off GitHub.

---

This document describes the structure and format of financial data files used in the eBay Store Financial Analysis project.

## Overview

The `financials/` folder contains various CSV and PDF reports exported from eBay. These files provide comprehensive financial data including sales, fees, transactions, and inventory information. They stay on the NAS share and are gitignored — this GitHub repo is public.

## Purchase and Sales Data Locations

**Important**: Purchase and sales data are distributed across multiple locations in the `financials/` folder:

- **Most eBay Purchases**: Purchase history can be found in the subfolders within `financials/ebay-reports/`, particularly:
  - `financials/ebay-reports/transactionreports/purchaseHistory.html` - Detailed purchase history from eBay
  - Other HTML reports in the `ebay-reports/` subfolders may contain additional purchase and sales information

- **Additional Purchases and Sales**: Additional purchase and sales data is located in:
  - `financials/f-bargarage/` - Contains CSV and PDF files including:
    - Tax Invoice Detail Reports (`2745279534_YYYY-MM.csv/pdf`)
    - Order Earnings Reports (`Order_earnings_*.csv`)
    - Transaction Reports (`Transaction_report_*.csv`)
    - All Orders Reports (`ebay-all-orders-report-*.csv`)
    - Active Listings Reports (`eBay-all-active-listings-report-*.csv`)
    - Promoted Listing Reports (`eBay-promoted-listing-general-listing-report-*.csv`)

When analyzing purchases or sales data, be sure to check both locations to ensure comprehensive coverage.

## SQLite Database

Imported and API-synced data is stored locally in `db/ebay_store.db` (gitignored). The schema is defined in `db/schema.sql`.

**Tables:**

| Table | Contents |
|-------|----------|
| `transactions` | Transaction report rows (orders, payouts, fees) |
| `order_lines` | All-orders report line items |
| `order_earnings` | Order earnings report rows |
| `tax_invoice_lines` | Tax invoice detail lines |
| `promoted_listing_fees` | Promoted listing fee rows |
| `import_runs` | Import/sync audit log |
| `sync_state` | Incremental API sync cursors |

**Import from CSV:**

```bash
python scripts/db/init_db.py
python scripts/db/import_csv.py --all
```

CSV files are read from `financials/f-bargarage/` and `reports/` (for standalone transaction exports). Duplicate files with `(1)` in the name are skipped.

See [REPORTING.md](REPORTING.md) for the full monthly workflow.

## File Types

### 1. Tax Invoice Detail Reports

**File Pattern**: `2745279534_YYYY-MM.csv` and `2745279534_YYYY-MM.pdf`

**Description**: Monthly eBay fee invoices showing all charges, fees, and credits for the month.

**Format**: CSV with the following structure:

- **Header Rows**: Metadata about the invoice (invoice date, seller ID, report name, time period)
- **Data Columns**:
  - `Date`: Transaction date
  - `Description`: Item or service description
  - `Memo`: Additional transaction details
  - `Order number`: eBay order number
  - `Item number`: eBay item number
  - `Fee group`: Category of fee (e.g., "Final value fees", "Ad fees")
  - `Fee type`: Specific fee type (e.g., "Final Value Fee", "Promoted Listings - General fee")
  - `Currency`: Transaction currency (typically USD)
  - `Net amount`: Net fee amount
  - `Taxable Amount`: Taxable portion
  - `Tax (%)`: Tax percentage
  - `Tax amount`: Tax amount
  - `Total amount`: Total amount including tax
  - `Charged by Entity`: Entity charging the fee (typically "MARKETPLACE")

**Use Cases**:
- Monthly expense tracking
- Fee analysis
- Tax documentation

### 2. Order Earnings Reports

**File Pattern**: `Order_earnings_YYYYMMDD_YYYYMMDD.csv` or `Order_earnings-*.csv`

**Description**: Detailed order-level earnings data including revenue, expenses, and net earnings.

**Format**: CSV with extensive columns including:

- `Order creation date`: Date order was created
- `Order number`: eBay order number
- `Item ID`: eBay item ID
- `Item title`: Listing title
- `Buyer name`: Buyer information
- `Ship to city/state/zip/country`: Shipping address
- `Transaction currency`: Currency used
- `eBay collected tax`: Tax collected by eBay
- `Item price`: Item sale price
- `Quantity`: Number of items
- `Item subtotal`: Subtotal before fees
- `Shipping and handling`: Shipping charges
- `Seller collected tax`: Tax collected by seller
- `Discount`: Discounts applied
- `Payout currency`: Currency for payout
- `Gross amount`: Total before fees
- `Final Value Fee - fixed`: Fixed portion of final value fee
- `Final Value Fee - variable`: Variable portion of final value fee
- `Below standard performance fee`: Performance penalty fees
- `Very high "item not as described" fee`: Return-related fees
- `International fee`: International transaction fees
- `Deposit processing fee`: Payment processing fees
- `Regulatory operating fee`: Regulatory fees
- `Promoted Listing Standard fee`: Advertising fees
- `Charity donation`: Charity contributions
- `Shipping labels`: Shipping label costs
- `Payment Dispute Fee`: Dispute-related fees
- `Expenses`: Total expenses
- `Refunds`: Refund amounts
- `Order earnings`: Net earnings after expenses
- `Your cost`: Cost of goods sold
- `Net order earnings`: Final net earnings

**Use Cases**:
- Revenue analysis
- Profit margin calculations
- Expense tracking
- Tax preparation

### 3. Transaction Reports

**File Pattern**: `Transaction_report_YYYYMMDD_YYYYMMDD.csv`

**Description**: Comprehensive transaction-level data including all transaction types (orders, refunds, payouts, fees, etc.).

**Format**: CSV with columns:

- `Transaction creation date`: Date transaction was created
- `Type`: Transaction type (Order, Refund, Payout, Other fee, etc.)
- `Order number`: Associated order number
- `Legacy order ID`: Legacy order identifier
- `Buyer username`: eBay buyer username
- `Buyer name`: Buyer's name
- `Ship to city/state/zip/country`: Shipping address
- `Net amount`: Net transaction amount
- `Payout currency`: Currency for payout
- `Payout date`: Date of payout
- `Payout ID`: Payout identifier
- `Payout method`: Payment method (e.g., "Chase Bank *7243")
- `Payout status`: Status of payout
- `Reason for hold`: Reason if payout is held
- `Item ID`: eBay item ID
- `Transaction ID`: Unique transaction identifier
- `Item title`: Listing title
- `Custom label`: Seller's SKU/custom label
- `Quantity`: Number of items
- `Item subtotal`: Item price
- `Shipping and handling`: Shipping charges
- `Seller collected tax`: Tax collected by seller
- `eBay collected tax`: Tax collected by eBay
- `Final Value Fee - fixed`: Fixed FVF
- `Final Value Fee - variable`: Variable FVF
- `Regulatory operating fee`: Regulatory fees
- `Very high "item not as described" fee`: Return fees
- `Below standard performance fee`: Performance fees
- `International fee`: International fees
- `Charity donation`: Charity contributions
- `Deposit processing fee`: Processing fees
- `Promoted Listing Standard fee`: Advertising fees
- `Gross transaction amount`: Total transaction amount
- `Transaction currency`: Currency
- `Exchange rate`: Currency exchange rate
- `Reference ID`: Reference identifier
- `Description`: Transaction description

**Use Cases**:
- Complete financial reconciliation
- Cash flow analysis
- Fee breakdown analysis
- Transaction auditing

### 4. All Orders Report

**File Pattern**: `ebay-all-orders-report-YYYY-MM-DD-*.csv`

**Description**: Complete order information with buyer details, shipping information, and order status.

**Format**: CSV with many columns including:

- `Sales Record Number`: Sequential record number
- `Order Number`: eBay order number
- `Buyer Username/Name/Email`: Buyer information
- `Buyer Address`: Buyer address details
- `Ship To Name/Phone/Address`: Shipping information
- `Item Number`: eBay item number
- `Item Title`: Listing title
- `Custom label (SKU)`: Seller's SKU
- `Sold Via Promoted Listings`: Whether sold via promoted listings
- `Quantity`: Number of items
- `Sold For`: Sale price
- `Shipping And Handling`: Shipping charges
- `Item Location`: Item location
- `eBay Collect And Remit Tax Rate/Type`: Tax information
- `Total Price`: Total order price
- `Payment Method`: Payment method used
- `Sale Date`: Date of sale
- `Paid On Date`: Payment date
- `Ship By Date`: Required ship date
- `Estimated Delivery Date`: Delivery estimate
- `Shipped On Date`: Actual ship date
- `Feedback Left/Received`: Feedback information
- `Shipping Service`: Shipping service used
- `Tracking Number`: Tracking information
- `Transaction ID`: Transaction identifier

**Use Cases**:
- Order fulfillment tracking
- Customer service
- Shipping analysis
- Sales reporting

### 5. Active Listings Report

**File Pattern**: `eBay-all-active-listings-report-YYYY-MM-DD-*.csv`

**Description**: Current inventory and active listings on eBay.

**Format**: CSV with columns:

- `Item number`: eBay item number
- `Title`: Listing title
- `Variation details`: Product variations
- `Custom label (SKU)`: Seller's SKU
- `Available quantity`: Stock quantity
- `Format`: Listing format (Fixed Price, Auction)
- `Currency`: Currency
- `Start price`: Starting price
- `Current price`: Current listing price
- `Sold quantity`: Number sold
- `Watchers`: Number of watchers
- `Bids`: Number of bids (for auctions)
- `Start date`: Listing start date
- `End date`: Listing end date
- `eBay category`: Category information
- `Condition`: Item condition
- `eBay Product ID (ePID)`: Product identifier
- `Listing site`: Site where listed
- `UPC/EAN/ISBN`: Product identifiers

**Use Cases**:
- Inventory management
- Listing analysis
- Stock level tracking

### 6. Promoted Listing Reports

**File Pattern**: `eBay-promoted-listing-general-listing-report-*.csv`

**Description**: Advertising costs and performance data for promoted listings.

**Format**: CSV with advertising-related columns including:
- Campaign information
- Click data
- Cost per click (CPC)
- Ad spend
- Performance metrics

**Use Cases**:
- Advertising cost analysis
- ROI calculations
- Marketing budget tracking

## Data Processing Notes

### SKU Report Derived Metrics

The SKU report generated by `scripts/analyze_sku_financials.py` includes derived summary metrics:

- `Net Profit (Approximate)`: currently based on `Total Net Amount`
- `Payout (70% of Net Profit)`: calculated as `Net Profit (Approximate) * 0.70`

### Date Formats

- Dates are typically in format: `MMM DD, YYYY HH:MM:SS PDT/PST`
- Some reports use: `YYYY-MM-DD` or `MM-DD-YYYY`
- Timezone information may be included (PDT, PST, UTC)

### Currency

- All amounts are typically in USD
- Some reports may include currency conversion information

### File Encoding

- Files are typically UTF-8 encoded
- Some special characters may be present in item titles/descriptions

### Duplicate Files

- Files with `(1)` suffix are typically duplicates
- These should be excluded from processing or archived

## Data Quality Considerations

1. **Missing Data**: Some fields may be empty (`--` or blank)
2. **Data Consistency**: Field formats may vary between reports
3. **Date Parsing**: Multiple date formats require careful parsing
4. **Currency Handling**: Ensure consistent currency handling
5. **Special Characters**: Item titles may contain special characters

## Recommended Processing Workflow

### CSV-only (legacy)

1. Place exports in `financials/f-bargarage/`
2. Run `scripts/run_monthly_reports.py --from-csv` or individual analysis scripts
3. Output appears in `reports/`

### Database-backed (recommended)

1. Import CSVs: `python scripts/db/import_csv.py --all`
2. Optionally sync from API: `python scripts/db/sync_ebay.py --month YYYY-MM`
3. Generate reports: `python scripts/run_monthly_reports.py --from-db`
4. Validate parity: `python scripts/reports/compare_reports.py`

### General data steps

1. **Load Data**: Read CSV files using appropriate encoding
2. **Parse Dates**: Convert date strings to datetime objects
3. **Clean Data**: Handle missing values and special characters
4. **Validate**: Check data consistency and completeness
5. **Transform**: Calculate derived metrics (margins, totals, etc.)
6. **Aggregate**: Group and summarize data as needed
7. **Export**: Generate reports in required formats

## Example Data Processing

```python
import pandas as pd
from datetime import datetime

# Load order earnings report
df = pd.read_csv('financials/Order_earnings_20250101_20251231.csv', 
                 skiprows=16)  # Skip header rows

# Parse dates
df['Order creation date'] = pd.to_datetime(df['Order creation date'])

# Calculate metrics
df['Net Margin'] = (df['Order earnings'] / df['Gross amount']) * 100

# Filter by date range
df_2025 = df[df['Order creation date'].dt.year == 2025]

# Aggregate
monthly_summary = df_2025.groupby(df_2025['Order creation date'].dt.to_period('M')).agg({
    'Gross amount': 'sum',
    'Order earnings': 'sum',
    'Expenses': 'sum'
})
```

## Questions or Issues

For questions about data structure or to report data issues:
1. Review the specific report file
2. Check eBay's documentation for report formats
3. Open an issue on GitHub with file details
