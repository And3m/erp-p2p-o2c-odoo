"""Run the business analysis queries in sql/reports/ against Odoo and save each as CSV."""
import argparse
from pathlib import Path

import pandas as pd
import psycopg2

ROOT = Path(__file__).resolve().parents[1]

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--dsn", default="host=/tmp dbname=erp_demo user=odoo password=odoo")
a = p.parse_args()
out = ROOT / "output" / "reports"
out.mkdir(parents=True, exist_ok=True)
with psycopg2.connect(a.dsn) as cx:
    for f in sorted((ROOT / "sql" / "reports").glob("*.sql")):
        df = pd.read_sql(f.read_text(), cx)
        df.to_csv(out / f"{f.stem}.csv", index=False)
        print(f"\n== {f.stem} ({len(df)} rows)")
        print(df.to_string(index=False))
