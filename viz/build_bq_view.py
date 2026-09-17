"""build_bq_view.py -- Build 2.5, the Looker Studio door (the GUI-floor door): headless up to the data, then a link.

Source:        viz/spec/hr_by_year.json · wax_baseball_dbt.fct_plays on BigQuery.
Analysis:      this script. Creates the view `wax_baseball_dbt.v_hr_by_year` (the chart's exact rows, governed by the
               same event_code = 23 rule) and prints a Looker Studio Linking-API URL that opens a new report with the
               view attached as its data source.
Presentation:  the view · out/keeping-score-hr-by-year-bigquery.csv (sums to 400) · out/looker-studio-link.txt ·
               the report itself is the GUI step (one bar chart, Year x Home Runs) -- where headless stops, by design.

    py viz/build_bq_view.py --build --receipt
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from query import BQ_PROJECT, SQL, hr_by_year  # noqa: E402

OUT = HERE / "out"
SPEC = json.loads((HERE / "spec" / "hr_by_year.json").read_text(encoding="utf-8"))
DATASET, VIEW = "wax_baseball_dbt", "v_hr_by_year"


def build() -> str:
    from google.cloud import bigquery
    client = bigquery.Client(project=BQ_PROJECT)
    ddl = f"CREATE OR REPLACE VIEW `{BQ_PROJECT}.{DATASET}.{VIEW}` AS {SQL['bigquery'].strip()}"
    client.query(ddl).result()
    print(f"  view {DATASET}.{VIEW} created/replaced")
    params = {"ds.connector": "bigQuery", "ds.type": "TABLE", "ds.projectId": BQ_PROJECT,
              "ds.datasetId": DATASET, "ds.tableId": VIEW, "r.reportName": "Keeping Score - HR by Year"}
    url = "https://lookerstudio.google.com/reporting/create?" + urllib.parse.urlencode(params)
    OUT.mkdir(exist_ok=True)
    (OUT / "looker-studio-link.txt").write_text(url + "\n", encoding="utf-8")
    print(f"  Looker Studio link -> out/looker-studio-link.txt\n  {url}")
    return url


def receipt() -> bool:
    rows = hr_by_year("bigquery")
    OUT.mkdir(exist_ok=True)
    csv = OUT / "keeping-score-hr-by-year-bigquery.csv"
    csv.write_text("Year,Home Runs\n" + "".join(f"{y},{h}\n" for y, h in rows), encoding="utf-8")
    total, want = sum(h for _, h in rows), SPEC["golden"]["value"]
    print(f"  {SPEC['golden']['label']}: {total} (want {want}) {'PASS' if total == want else 'FAIL'} -- {len(rows)} rows -> {csv.name}")
    return total == want


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--receipt", action="store_true")
    a = ap.parse_args()
    if not (a.build or a.receipt):
        ap.print_help(); return
    ok = True
    if a.build:
        build()
    if a.receipt:
        ok = receipt() and ok
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
