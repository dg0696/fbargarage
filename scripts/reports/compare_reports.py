#!/usr/bin/env python3
"""Compare CSV-generated reports vs DB-generated reports."""

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

REPORT_SPECS = [
    {
        "label": "sku transactions",
        "report": "sku_G_{ym}_report.txt",
        "summary": "sku_G_{ym}_report_summary.txt",
        "metrics": ["total_net", "total_gross", "orders"],
    },
    {
        "label": "sku all-orders",
        "report": "sku_G_{ym}_all-orders_report.txt",
        "summary": "sku_G_{ym}_all-orders_summary.txt",
        "metrics": ["orders", "total_quantity", "total_sold_for", "total_shipping", "total_price"],
    },
    {
        "label": "store all-orders",
        "report": "f-bargarage_{ym}_all-orders_report.txt",
        "summary": "f-bargarage_{ym}_all-orders_summary.txt",
        "metrics": ["orders", "total_quantity", "total_sold_for", "total_shipping", "total_price"],
    },
]


def extract_metric(text, pattern):
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1).strip() if match else None


def parse_summary(path):
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    return {
        "orders": extract_metric(text, r"^Orders:\s*(\d+)"),
        "total_quantity": extract_metric(text, r"^Total Quantity:\s*(\d+)"),
        "total_sold_for": extract_metric(text, r"^Total Sold For:\s*USD\s*([\d.]+)"),
        "total_shipping": extract_metric(
            text, r"^Total Shipping And Handling:\s*USD\s*([\d.]+)"
        ),
        "total_price": extract_metric(text, r"^Total Price:\s*USD\s*([\d.]+)"),
        "total_net": extract_metric(text, r"^Total Net Amount\s+\$\s*([\d,]+\.\d+)"),
        "total_gross": extract_metric(text, r"^Total Gross Revenue\s+\$\s*([\d,]+\.\d+)"),
    }


def normalize_report_text(text):
    text = re.sub(r"^Input:.*$", "Input: <source>", text, flags=re.MULTILINE)
    text = re.sub(r"^Generated:.*$", "Generated: <ts>", text, flags=re.MULTILINE)
    return text


def run_reports(mode, year, month, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ym = f"{year:04d}-{month:02d}"

    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_monthly_reports.py"),
        "--year",
        str(year),
        "--month",
        str(month),
    ]
    if mode == "csv":
        cmd.append("--from-csv")
    else:
        cmd.append("--from-db")

    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if result.returncode not in (0, 1):
        print(result.stderr or result.stdout)
        result.check_returncode()

    copied = {}
    for spec in REPORT_SPECS:
        report_src = REPO_ROOT / "reports" / spec["report"].format(ym=ym)
        summary_src = REPO_ROOT / "reports" / spec["summary"].format(ym=ym)
        if report_src.exists():
            dest = out_dir / f"{spec['label']}_report_{ym}.txt"
            dest.write_text(report_src.read_text(encoding="utf-8"), encoding="utf-8")
            copied[f"{spec['label']}_report"] = dest
        if summary_src.exists():
            dest = out_dir / f"{spec['label']}_summary_{ym}.txt"
            dest.write_text(summary_src.read_text(encoding="utf-8"), encoding="utf-8")
            copied[f"{spec['label']}_summary"] = dest

    return copied


def compare_metric(label, csv_val, db_val):
    if csv_val is None and db_val is None:
        return True, "both missing"
    if csv_val is None or db_val is None:
        return False, f"csv={csv_val} db={db_val}"
    if label in ("total_net", "total_gross"):
        csv_num = float(csv_val.replace(",", ""))
        db_num = float(db_val.replace(",", ""))
        if abs(csv_num - db_num) < 0.01:
            return True, f"{csv_num:.2f}"
        return False, f"csv={csv_num:.2f} db={db_num:.2f}"
    if csv_val == db_val:
        return True, csv_val
    return False, f"csv={csv_val} db={db_val}"


def compare_full_reports(csv_files, db_files, ym, mismatches):
    for spec in REPORT_SPECS:
        label = spec["label"]
        csv_path = csv_files.get(f"{label}_report")
        db_path = db_files.get(f"{label}_report")
        if not csv_path and not db_path:
            continue
        if not csv_path or not db_path:
            detail = f"csv={'yes' if csv_path else 'no'} db={'yes' if db_path else 'no'}"
            print(f"  {label} full report: MISSING ({detail})")
            mismatches.append(f"{ym} {label} full report: {detail}")
            continue

        csv_text = normalize_report_text(csv_path.read_text(encoding="utf-8"))
        db_text = normalize_report_text(db_path.read_text(encoding="utf-8"))
        if csv_text == db_text:
            print(f"  {label} full report: OK")
            continue

        csv_lines = csv_text.splitlines()
        db_lines = db_text.splitlines()
        detail = f"line count csv={len(csv_lines)} db={len(db_lines)}"
        for i, (left, right) in enumerate(zip(csv_lines, db_lines)):
            if left != right:
                detail = f"first diff line {i + 1}: csv={left[:80]!r} db={right[:80]!r}"
                break
        print(f"  {label} full report: MISMATCH ({detail})")
        mismatches.append(f"{ym} {label} full report: {detail}")


def main():
    parser = argparse.ArgumentParser(description="Compare CSV vs DB report outputs")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--start-month", type=int, default=1)
    parser.add_argument("--end-month", type=int, default=5)
    args = parser.parse_args()

    csv_dir = REPO_ROOT / "reports" / "_compare_csv"
    db_dir = REPO_ROOT / "reports" / "_compare_db"
    mismatches = []

    for month in range(args.start_month, args.end_month + 1):
        ym = f"{args.year:04d}-{month:02d}"
        print(f"\n=== {ym} ===")
        csv_files = run_reports("csv", args.year, month, csv_dir)
        db_files = run_reports("db", args.year, month, db_dir)

        for spec in REPORT_SPECS:
            label = spec["label"]
            csv_path = csv_files.get(f"{label}_summary")
            db_path = db_files.get(f"{label}_summary")
            if not csv_path and not db_path:
                print(f"  {label}: no reports (expected for some months)")
                continue
            csv_metrics = parse_summary(csv_path) if csv_path else {}
            db_metrics = parse_summary(db_path) if db_path else {}
            for metric in spec["metrics"]:
                ok, detail = compare_metric(metric, csv_metrics.get(metric), db_metrics.get(metric))
                status = "OK" if ok else "MISMATCH"
                print(f"  {label} {metric}: {status} ({detail})")
                if not ok:
                    mismatches.append(f"{ym} {label} {metric}: {detail}")

        compare_full_reports(csv_files, db_files, ym, mismatches)

    print("\n=== Summary ===")
    if mismatches:
        print(f"{len(mismatches)} mismatch(es):")
        for item in mismatches:
            print(f"  - {item}")
        sys.exit(1)
    print("All compared metrics and full reports match.")


if __name__ == "__main__":
    main()
