#!/usr/bin/env python3
"""
Analyze Financial Data for SKUs Starting with Specific Prefix

This script extracts and analyzes financial data for products with SKUs
starting with a specified prefix (e.g., "G") for a given year.
"""

import argparse
import pandas as pd
from datetime import datetime
from pathlib import Path
import sys

INTEGER_SUMMARY_KEYS = {"Total Orders", "Total Quantity Sold"}


def format_summary_value(key, value):
    if key in INTEGER_SUMMARY_KEYS:
        return f"{int(round(value)):,}"
    return f"${float(value):,.2f}"


def normalize_detail_display(df):
    """Match legacy CSV report formatting for whole-number money/quantity values."""
    out = df.copy()
    for col in out.columns:
        if not pd.api.types.is_numeric_dtype(out[col]):
            continue
        out[col] = out[col].apply(
            lambda value: int(value)
            if pd.notna(value) and float(value) == int(float(value))
            else value
        )
    return out


def find_header_row(file_path, max_rows=30):
    """Find the row number where the actual data columns start."""
    with open(file_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i >= max_rows:
                break
            # Look for common column names
            if 'Custom label' in line or 'Transaction creation date' in line:
                return i
    return None


def load_transaction_report(file_path):
    """Load transaction report CSV file."""
    print(f"Loading transaction report: {file_path}")
    
    # Try to find the header row
    header_row = find_header_row(file_path)
    
    if header_row is None:
        # Try common skip values
        for skip_rows in [4, 5, 6, 7]:
            try:
                df = pd.read_csv(file_path, skiprows=skip_rows, nrows=1)
                if 'Custom label' in df.columns or 'Transaction creation date' in df.columns:
                    header_row = skip_rows
                    break
            except:
                continue
    
    if header_row is None:
        raise ValueError("Could not find header row in transaction report")
    
    print(f"Reading data starting from row {header_row + 1}")
    
    # Read the full file
    df = pd.read_csv(file_path, skiprows=header_row, low_memory=False)
    
    # Clean column names (remove extra spaces)
    df.columns = df.columns.str.strip()
    
    return df


def parse_date(date_str):
    """Parse various date formats from eBay reports."""
    if pd.isna(date_str) or date_str == '--' or date_str == '':
        return None
    
    # Common formats
    formats = [
        '%b %d, %Y',
        '%B %d, %Y',
        '%Y-%m-%d',
        '%m/%d/%Y',
        '%d/%m/%Y',
    ]
    
    for fmt in formats:
        try:
            return pd.to_datetime(date_str, format=fmt)
        except:
            continue
    
    # Try pandas auto-parsing
    try:
        return pd.to_datetime(date_str)
    except:
        return None


def filter_sku_data(df, sku_prefix, year):
    """Filter data for SKUs starting with prefix and for specified year."""
    print(f"\nFiltering for SKUs starting with '{sku_prefix}' for year {year}...")
    
    # Ensure we have the required columns
    required_cols = ['Custom label', 'Transaction creation date', 'Type']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        print(f"Warning: Missing columns: {missing_cols}")
        print(f"Available columns: {list(df.columns)}")
        return None
    
    # Filter by SKU prefix
    if 'Custom label' in df.columns:
        # Handle NaN values
        df_filtered = df[df['Custom label'].notna()].copy()
        df_filtered = df_filtered[df_filtered['Custom label'].astype(str).str.startswith(sku_prefix, na=False)]
    else:
        print("Error: 'Custom label' column not found")
        return None
    
    print(f"Found {len(df_filtered)} transactions with SKU starting with '{sku_prefix}'")

    if len(df_filtered) == 0:
        return df_filtered

    # Parse dates and filter by year
    df_filtered['Transaction creation date'] = pd.to_datetime(
        df_filtered['Transaction creation date'].apply(parse_date), errors='coerce'
    )
    df_filtered = df_filtered[df_filtered['Transaction creation date'].notna()]
    df_filtered = df_filtered[df_filtered['Transaction creation date'].dt.year == year]
    
    # Filter for Order transactions only (exclude Payout, Refund, etc.)
    df_filtered = df_filtered[df_filtered['Type'] == 'Order']
    
    print(f"Found {len(df_filtered)} orders in {year} with SKU starting with '{sku_prefix}'")
    
    return df_filtered


def calculate_financial_summary(df):
    """Calculate financial summary for filtered data."""
    if df is None or len(df) == 0:
        return None
    
    # Convert numeric columns, handling '--' and empty values
    numeric_cols = [
        'Gross transaction amount',
        'Item subtotal',
        'Shipping and handling',
        'Final Value Fee - fixed',
        'Final Value Fee - variable',
        'Regulatory operating fee',
        'Promoted Listing Standard fee',
        'Net amount',
        'Quantity'
    ]
    
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].replace('--', 0).replace('', 0), errors='coerce').fillna(0)

    if 'Quantity' in df.columns:
        df['Quantity'] = df['Quantity'].round().astype(int)
    
    # Calculate summary
    summary = {
        'Total Orders': len(df),
        'Total Quantity Sold': int(df['Quantity'].sum()) if 'Quantity' in df.columns else 0,
        'Total Gross Revenue': df['Gross transaction amount'].sum() if 'Gross transaction amount' in df.columns else 0,
        'Total Item Subtotal': df['Item subtotal'].sum() if 'Item subtotal' in df.columns else 0,
        'Total Shipping Revenue': df['Shipping and handling'].sum() if 'Shipping and handling' in df.columns else 0,
        'Total Final Value Fees (Fixed)': df['Final Value Fee - fixed'].sum() if 'Final Value Fee - fixed' in df.columns else 0,
        'Total Final Value Fees (Variable)': df['Final Value Fee - variable'].sum() if 'Final Value Fee - variable' in df.columns else 0,
        'Total Regulatory Fees': df['Regulatory operating fee'].sum() if 'Regulatory operating fee' in df.columns else 0,
        'Total Promoted Listing Fees': df['Promoted Listing Standard fee'].sum() if 'Promoted Listing Standard fee' in df.columns else 0,
        'Total Net Amount': df['Net amount'].sum() if 'Net amount' in df.columns else 0,
    }
    
    # Calculate total fees
    summary['Total Fees'] = (
        abs(summary['Total Final Value Fees (Fixed)']) +
        abs(summary['Total Final Value Fees (Variable)']) +
        abs(summary['Total Regulatory Fees']) +
        abs(summary['Total Promoted Listing Fees'])
    )
    
    # Calculate net profit (approximate - Net amount is after fees)
    summary['Net Profit (Approximate)'] = summary['Total Net Amount']
    # Payout is defined as 70% of approximate net profit.
    summary['Payout (70% of Net Profit)'] = summary['Net Profit (Approximate)'] * 0.70
    
    return summary


def generate_summary_report(df, summary, sku_prefix, year, output_file):
    """Generate a detailed summary report with item-level breakdowns and percentages."""
    report_lines = []
    report_lines.append("=" * 100)
    report_lines.append(f"FINANCIAL SUMMARY REPORT: SKUs Starting with '{sku_prefix}' - Year {year}")
    report_lines.append("=" * 100)
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    
    if df is None or len(df) == 0:
        report_lines.append("No transactions found.")
        report_text = "\n".join(report_lines)
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_text)
        return report_text
    
    # Calculate item-level fees breakdown
    df_report = df.copy()
    
    # Ensure numeric columns are numeric
    numeric_cols = [
        'Gross transaction amount',
        'Item subtotal',
        'Shipping and handling',
        'Final Value Fee - fixed',
        'Final Value Fee - variable',
        'Regulatory operating fee',
        'Promoted Listing Standard fee',
        'Net amount',
        'Quantity'
    ]
    
    for col in numeric_cols:
        if col in df_report.columns:
            df_report[col] = pd.to_numeric(
                df_report[col].astype(str).replace('--', '0').replace('', '0'), 
                errors='coerce'
            ).fillna(0)
    
    # Calculate total fees per item (handle missing columns)
    df_report['Total Fees'] = 0
    
    if 'Final Value Fee - fixed' in df_report.columns:
        df_report['Total Fees'] += df_report['Final Value Fee - fixed'].abs()
    if 'Final Value Fee - variable' in df_report.columns:
        df_report['Total Fees'] += df_report['Final Value Fee - variable'].abs()
    if 'Regulatory operating fee' in df_report.columns:
        df_report['Total Fees'] += df_report['Regulatory operating fee'].abs()
    if 'Promoted Listing Standard fee' in df_report.columns:
        df_report['Total Fees'] += df_report['Promoted Listing Standard fee'].abs()
    
    # Sort by date
    df_report = df_report.sort_values('Transaction creation date')
    
    # ITEM-LEVEL BREAKDOWN
    report_lines.append("ITEM-LEVEL FINANCIAL BREAKDOWN")
    report_lines.append("-" * 100)
    report_lines.append("")
    
    for idx, row in df_report.iterrows():
        # Format date
        sale_date = row['Transaction creation date']
        if pd.notna(sale_date):
            if isinstance(sale_date, pd.Timestamp):
                sale_date_str = sale_date.strftime('%Y-%m-%d')
            else:
                sale_date_str = str(sale_date)
        else:
            sale_date_str = "N/A"
        
        # Get item details
        order_num = row.get('Order number', 'N/A')
        sku = row.get('Custom label', 'N/A')
        item_title = str(row.get('Item title', 'N/A'))[:60] + ('...' if len(str(row.get('Item title', ''))) > 60 else '')
        quantity = int(row.get('Quantity', 0) or 0)
        
        # Financial details (handle missing columns safely)
        gross = float(row.get('Gross transaction amount', 0) or 0)
        item_subtotal = float(row.get('Item subtotal', 0) or 0)
        shipping = float(row.get('Shipping and handling', 0) or 0)
        fvf_fixed = float(row.get('Final Value Fee - fixed', 0) or 0)
        fvf_var = float(row.get('Final Value Fee - variable', 0) or 0)
        reg_fee = float(row.get('Regulatory operating fee', 0) or 0)
        promo_fee = float(row.get('Promoted Listing Standard fee', 0) or 0)
        total_fees = float(row.get('Total Fees', 0) or 0)
        net = float(row.get('Net amount', 0) or 0)
        
        # Calculate percentages for this item
        fees_pct = (total_fees / gross * 100) if gross > 0 else 0
        net_pct = (net / gross * 100) if gross > 0 else 0
        
        report_lines.append(f"Sale Date: {sale_date_str} | Order: {order_num} | SKU: {sku}")
        report_lines.append(f"Description: {item_title}")
        report_lines.append(f"Quantity: {quantity}")
        report_lines.append("")
        report_lines.append(f"  Gross Revenue:                    ${gross:>12,.2f} (100.00%)")
        report_lines.append(f"    Item Subtotal:                  ${item_subtotal:>12,.2f}")
        report_lines.append(f"    Shipping & Handling:            ${shipping:>12,.2f}")
        report_lines.append("")
        report_lines.append(f"  Fees Breakdown:")
        report_lines.append(f"    Final Value Fee (Fixed):        ${abs(fvf_fixed):>12,.2f}")
        report_lines.append(f"    Final Value Fee (Variable):     ${abs(fvf_var):>12,.2f}")
        report_lines.append(f"    Regulatory Operating Fee:       ${abs(reg_fee):>12,.2f}")
        report_lines.append(f"    Promoted Listing Fee:           ${abs(promo_fee):>12,.2f}")
        report_lines.append(f"    TOTAL FEES:                     ${total_fees:>12,.2f} ({fees_pct:>6.2f}% of gross)")
        report_lines.append("")
        report_lines.append(f"  Net Amount:                       ${net:>12,.2f} ({net_pct:>6.2f}% of gross)")
        report_lines.append("-" * 100)
        report_lines.append("")
    
    # OVERALL SUMMARY
    total_gross = summary.get('Total Gross Revenue', 0)
    total_fees = summary.get('Total Fees', 0)
    total_net = summary.get('Total Net Amount', 0)
    
    fees_percentage = (total_fees / total_gross * 100) if total_gross > 0 else 0
    net_percentage = (total_net / total_gross * 100) if total_gross > 0 else 0
    
    report_lines.append("OVERALL FINANCIAL SUMMARY")
    report_lines.append("=" * 100)
    report_lines.append("")
    report_lines.append(f"{'Metric':<50} {'Amount':>20} {'Percentage':>15}")
    report_lines.append("-" * 100)
    report_lines.append(
        f"{'Total Orders':<50} {int(summary.get('Total Orders', 0)):>20,}"
    )
    report_lines.append(
        f"{'Total Quantity Sold':<50} {int(summary.get('Total Quantity Sold', 0)):>20,}"
    )
    report_lines.append("")
    report_lines.append(f"{'Total Gross Revenue':<50} ${total_gross:>19,.2f} {'100.00%':>15}")
    report_lines.append(f"  {'Item Subtotal':<48} ${summary.get('Total Item Subtotal', 0):>19,.2f}")
    report_lines.append(f"  {'Shipping Revenue':<48} ${summary.get('Total Shipping Revenue', 0):>19,.2f}")
    report_lines.append("")
    report_lines.append(f"{'Total Fees':<50} ${total_fees:>19,.2f} {fees_percentage:>14.2f}%")
    report_lines.append(f"  {'Final Value Fee (Fixed)':<48} ${abs(summary.get('Total Final Value Fees (Fixed)', 0)):>19,.2f}")
    report_lines.append(f"  {'Final Value Fee (Variable)':<48} ${abs(summary.get('Total Final Value Fees (Variable)', 0)):>19,.2f}")
    report_lines.append(f"  {'Regulatory Operating Fee':<48} ${summary.get('Total Regulatory Fees', 0):>19,.2f}")
    report_lines.append(f"  {'Promoted Listing Fee':<48} ${summary.get('Total Promoted Listing Fees', 0):>19,.2f}")
    report_lines.append("")
    report_lines.append(f"{'Total Net Amount':<50} ${total_net:>19,.2f} {net_percentage:>14.2f}%")
    report_lines.append("")
    report_lines.append("=" * 100)
    report_lines.append("")
    
    # SUMMARY BY SKU
    if 'Custom label' in df.columns:
        report_lines.append("SUMMARY BY SKU")
        report_lines.append("-" * 100)
        
        sku_summary = df_report.groupby('Custom label').agg({
            'Quantity': 'sum',
            'Gross transaction amount': 'sum',
            'Total Fees': 'sum',
            'Net amount': 'sum'
        }).sort_values('Gross transaction amount', ascending=False)
        
        report_lines.append("")
        report_lines.append(f"{'SKU':<15} {'Quantity':>10} {'Gross Revenue':>18} {'Total Fees':>18} {'Net Amount':>18} {'Fees %':>10} {'Net %':>10}")
        report_lines.append("-" * 100)
        
        for sku, row in sku_summary.iterrows():
            sku_gross = row['Gross transaction amount']
            sku_fees = row['Total Fees']
            sku_net = row['Net amount']
            sku_qty = row['Quantity']
            
            sku_fees_pct = (sku_fees / sku_gross * 100) if sku_gross > 0 else 0
            sku_net_pct = (sku_net / sku_gross * 100) if sku_gross > 0 else 0
            
            report_lines.append(
                f"{sku:<15} {sku_qty:>10.0f} ${sku_gross:>17,.2f} ${sku_fees:>17,.2f} "
                f"${sku_net:>17,.2f} {sku_fees_pct:>9.2f}% {sku_net_pct:>9.2f}%"
            )
        
        # Add totals row
        report_lines.append("-" * 100)
        report_lines.append(
            f"{'TOTAL':<15} {sku_summary['Quantity'].sum():>10.0f} "
            f"${sku_summary['Gross transaction amount'].sum():>17,.2f} "
            f"${sku_summary['Total Fees'].sum():>17,.2f} "
            f"${sku_summary['Net amount'].sum():>17,.2f} "
            f"{fees_percentage:>9.2f}% {net_percentage:>9.2f}%"
        )
        report_lines.append("")
    
    report_text = "\n".join(report_lines)
    
    # Save to file
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_text)
        print(f"\nSummary report saved to: {output_path}")
    
    # Also print to console
    print("\n" + report_text)
    
    return report_text


def generate_report(df, summary, sku_prefix, year, output_file):
    """Generate a detailed report (original format)."""
    # Generate both the original format and the new summary format
    summary_output = output_file.replace('.txt', '_summary.txt') if output_file else None
    
    # Generate summary report
    generate_summary_report(df, summary, sku_prefix, year, summary_output)
    
    # Also generate original format
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append(f"FINANCIAL REPORT: SKUs Starting with '{sku_prefix}' - Year {year}")
    report_lines.append("=" * 80)
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    
    if summary:
        report_lines.append("FINANCIAL SUMMARY")
        report_lines.append("-" * 80)
        for key, value in summary.items():
            report_lines.append(f"{key:.<50} {format_summary_value(key, value)}")
        report_lines.append("")
    
    if df is not None and len(df) > 0:
        report_lines.append("DETAILED TRANSACTIONS")
        report_lines.append("-" * 80)
        
        # Select key columns for detail
        detail_cols = [
            'Transaction creation date',
            'Order number',
            'Item title',
            'Custom label',
            'Quantity',
            'Gross transaction amount',
            'Item subtotal',
            'Shipping and handling',
            'Net amount'
        ]
        
        available_cols = [col for col in detail_cols if col in df.columns]
        df_detail = normalize_detail_display(df[available_cols].copy())
        
        # Sort by date
        df_detail = df_detail.sort_values('Transaction creation date')
        
        # Format the detail table
        report_lines.append(df_detail.to_string(index=False))
        report_lines.append("")
        
        # Summary by SKU
        if 'Custom label' in df.columns:
            report_lines.append("SUMMARY BY SKU")
            report_lines.append("-" * 80)
            sku_summary = df.groupby('Custom label').agg({
                'Quantity': 'sum',
                'Gross transaction amount': 'sum',
                'Net amount': 'sum'
            }).sort_values('Gross transaction amount', ascending=False)
            report_lines.append(sku_summary.to_string())
            report_lines.append("")
    
    report_text = "\n".join(report_lines)
    
    # Save to file
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_text)
        print(f"Detailed report saved to: {output_path}")
    
    return report_text


def main():
    parser = argparse.ArgumentParser(
        description="Analyze financial data for SKUs starting with a specific prefix",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--sku-prefix',
        type=str,
        default='G',
        help="SKU prefix to filter (default: G)"
    )
    
    parser.add_argument(
        '--year',
        type=int,
        default=2025,
        help="Year to analyze (default: 2025)"
    )
    
    parser.add_argument(
        '--input-file',
        type=str,
        default='financials/f-bargarage/Transaction_report_20250101_20251231.csv',
        help="Path to transaction report CSV file"
    )
    
    parser.add_argument(
        '--output-file',
        type=str,
        default=None,
        help="Path to output report file (default: reports/sku_G_2025_report.txt)"
    )
    
    parser.add_argument(
        '--export-csv',
        type=str,
        default=None,
        help="Path to export detailed data as CSV (default: reports/sku_G_2025_data.csv)"
    )
    
    args = parser.parse_args()
    
    # Set default output file if not provided
    if args.output_file is None:
        args.output_file = f"reports/sku_{args.sku_prefix}_{args.year}_report.txt"
    
    if args.export_csv is None:
        args.export_csv = f"reports/sku_{args.sku_prefix}_{args.year}_data.csv"
    
    # Load data
    try:
        df = load_transaction_report(args.input_file)
    except Exception as e:
        print(f"Error loading transaction report: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Filter data
    df_filtered = filter_sku_data(df, args.sku_prefix, args.year)
    
    if df_filtered is None or len(df_filtered) == 0:
        print(f"\nNo data found for SKUs starting with '{args.sku_prefix}' in year {args.year}")
        sys.exit(0)
    
    # Calculate summary
    summary = calculate_financial_summary(df_filtered)
    
    # Export to CSV if requested
    if args.export_csv and df_filtered is not None and len(df_filtered) > 0:
        csv_path = Path(args.export_csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        df_filtered.to_csv(csv_path, index=False)
        print(f"\nDetailed data exported to CSV: {csv_path}")
    
    # Generate report
    generate_report(df_filtered, summary, args.sku_prefix, args.year, args.output_file)


if __name__ == "__main__":
    main()
