"""Extract posted accounting data from Odoo with SQL and load it into the finance warehouse.

1. Runs the queries in sql/ against Odoo's PostgreSQL database.
2. Maps Odoo's Indian chart of accounts onto the warehouse chart (sql/account_mapping.csv).
   Unmapped accounts are kept under their Odoo code, so the warehouse data quality
   check "gl_accounts_exist_in_chart" stops the load and names them.
3. Writes the extracts in the warehouse's source format to output/warehouse_source/.
4. Optionally runs the warehouse ETL (github.com/And3m/finance-data-warehouse) on them.

Usage:
    python scripts/extract_to_warehouse.py --dsn "host=/tmp dbname=erp_demo user=odoo" \
        [--warehouse ../finance-data-warehouse]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import psycopg2

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "sql"
STATE_TO_COST_CENTER = {"KA": "BLR", "TS": "HYD", "TN": "CHN"}
SOURCE_BY_JOURNAL = {"sale": "AR", "purchase": "AP", "bank": "BANK", "cash": "BANK", "general": "STOCK"}
WAREHOUSE_CHART = [
    ("1000", "Cash at Bank", "Asset", "BS", "Debit", ""),
    ("1100", "Accounts Receivable", "Asset", "BS", "Debit", ""),
    ("1200", "Inventory", "Asset", "BS", "Debit", ""),
    ("1300", "Input GST Credit", "Asset", "BS", "Debit", ""),
    ("2000", "Accounts Payable", "Liability", "BS", "Credit", ""),
    ("2100", "Output GST Payable", "Liability", "BS", "Credit", ""),
    ("3000", "Share Capital", "Equity", "BS", "Credit", ""),
    ("4000", "Sales Revenue", "Revenue", "PL", "Credit", "Revenue"),
    ("5000", "Cost of Goods Sold", "Expense", "PL", "Debit", "Cost of Sales"),
]
COST_CENTERS = [("HO", "Head Office", "Bengaluru"), ("BLR", "Sales Bengaluru", "Bengaluru"),
                ("HYD", "Sales Hyderabad", "Hyderabad"), ("CHN", "Sales Chennai", "Chennai")]


def query(cx, name):
    return pd.read_sql((SQL / name).read_text(), cx)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dsn", default="host=/tmp dbname=erp_demo user=odoo password=odoo")
    p.add_argument("--out", default=str(ROOT / "output" / "warehouse_source"))
    p.add_argument("--warehouse", help="path to a finance-data-warehouse checkout to load into")
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    with psycopg2.connect(a.dsn) as cx:
        gl = query(cx, "extract_gl_lines.sql")
        inv = query(cx, "extract_invoices.sql")
        settle = query(cx, "extract_settlements.sql")
    print(f"Extracted {len(gl)} GL lines, {len(inv)} invoices and bills, {len(settle)} settlements")

    mapping = pd.read_csv(SQL / "account_mapping.csv", dtype=str)
    code_map = dict(zip(mapping.odoo_account_code, mapping.dw_account_code))
    unmapped = sorted(set(gl.odoo_account_code) - set(code_map))
    if unmapped:
        print(f"WARNING unmapped Odoo accounts: {unmapped}. The warehouse will reject them.")

    gl["account_code"] = gl.odoo_account_code.map(code_map).fillna(gl.odoo_account_code)
    on_pl = gl.account_code.isin(["4000", "5000"])
    gl["cost_center_code"] = "HO"
    gl.loc[on_pl, "cost_center_code"] = gl.loc[on_pl, "partner_state"].map(STATE_TO_COST_CENTER).fillna("HO")
    gl["source"] = gl.journal_type.map(SOURCE_BY_JOURNAL).fillna("GEN")
    gl_out = gl[["journal_id", "line_no", "posting_date", "account_code", "cost_center_code", "debit",
                 "credit", "source", "doc_ref", "narration"]]

    ar = inv[inv.move_type == "out_invoice"]
    ap = inv[inv.move_type == "in_invoice"]
    cols = ["invoice_no", "partner_id", "invoice_date", "due_date", "net_amount", "gst_amount", "total_amount"]
    rename = lambda df, key: df[cols].rename(columns={"partner_id": key}).assign(
        **{key: df.partner_id.map(lambda i: f"P{i:04d}")})
    tables = {
        "chart_of_accounts": pd.DataFrame(WAREHOUSE_CHART, columns=[
            "account_code", "account_name", "account_type", "statement", "normal_balance", "pnl_group"]),
        "cost_centers": pd.DataFrame(COST_CENTERS, columns=["cost_center_code", "cost_center_name", "city"]),
        "customers": ar.drop_duplicates("partner_id").assign(
            customer_id=lambda d: d.partner_id.map(lambda i: f"P{i:04d}"),
            cost_center_code=lambda d: d.partner_state.map(STATE_TO_COST_CENTER).fillna("HO"),
            credit_terms_days=0)[["customer_id", "partner_name", "partner_city", "cost_center_code",
                                  "credit_terms_days"]].rename(columns={"partner_name": "customer_name",
                                                                        "partner_city": "city"}),
        "vendors": ap.drop_duplicates("partner_id").assign(
            vendor_id=lambda d: d.partner_id.map(lambda i: f"P{i:04d}"), category="Goods",
            payment_terms_days=0)[["vendor_id", "partner_name", "category", "payment_terms_days"]].rename(
            columns={"partner_name": "vendor_name"}),
        "gl_journal_lines": gl_out,
        "ar_invoices": rename(ar, "customer_id"),
        "ap_invoices": rename(ap, "vendor_id"),
        "ar_receipts": settle[settle.move_type == "out_invoice"].rename(columns={
            "settlement_no": "receipt_no", "settlement_date": "receipt_date"})[
            ["receipt_no", "invoice_no", "receipt_date", "amount"]],
        "ap_payments": settle[settle.move_type == "in_invoice"].rename(columns={
            "settlement_no": "payment_no", "settlement_date": "payment_date"})[
            ["payment_no", "invoice_no", "payment_date", "amount"]],
    }
    for name, df in tables.items():
        df.to_csv(out / f"{name}.csv", index=False)
    print(f"Wrote warehouse source files to {out}")

    if a.warehouse:
        wh = Path(a.warehouse).resolve()
        today = date.today()
        fy_start = date(today.year if today.month >= 4 else today.year - 1, 4, 1)
        cmd = [sys.executable, str(wh / "etl" / "run_etl.py"), "--source", str(out),
               "--as-of", today.isoformat(), "--fy-start", fy_start.isoformat(),
               "--db-url", f"sqlite:///{ROOT / 'output' / 'odoo_dw.sqlite'}",
               "--exports", str(ROOT / "output" / "warehouse_exports")]
        print("Running warehouse ETL:", " ".join(cmd[1:3]), "...")
        return subprocess.call(cmd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
