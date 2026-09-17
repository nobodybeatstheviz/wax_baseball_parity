"""build_lakeview.py -- Build 2.5, the Databricks AI/BI door: the same G2 bar (400 home runs witnessed, by year)
as a Lakeview (AI/BI) dashboard, authored as JSON and created + published headlessly through the Databricks SDK.

Source:        viz/spec/hr_by_year.json · the metric view wax_baseball.semantics.mv_plays · the NBTV chart tokens.
Analysis:      this script. One dataset (the metric-view query), one page, one bar widget.
Presentation:  out/keeping-score-hr-by-year-lakeview.json (the serialized dashboard, the git receipt) ·
               the published dashboard in the workspace · out/keeping-score-hr-by-year-databricks.csv (sums to 400).

    py viz/build_lakeview.py --build                 # write the dashboard JSON
    py viz/build_lakeview.py --build --publish       # ...create it (or update if it exists) and publish
    py viz/build_lakeview.py --receipt               # the query through the SQL warehouse -> CSV, PASS on 400
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "scripts"))
from query import SQL, hr_by_year  # noqa: E402

OUT = HERE / "out"
SPEC = json.loads((HERE / "spec" / "hr_by_year.json").read_text(encoding="utf-8"))
TOKENS = pathlib.Path(os.environ.get("NBTV_CHART_TOKENS",
                                     pathlib.Path.home() / ".claude" / "skills" / "nbtv-design" / "tokens" / "chart.json"))
WAREHOUSE_ID = "873a5fb5d84620c1"          # same warehouse _dbx_conn.py uses
DISPLAY_NAME = "Keeping Score - HR by Year"
STEM = "keeping-score-hr-by-year"


def serialized(brand: bool) -> dict:
    t = json.loads(TOKENS.read_text(encoding="utf-8")) if TOKENS.exists() else None
    door = SPEC["doors"]["databricks_aibi"]["door"]
    spec = {
        "version": 3,
        "widgetType": "bar",
        "encodings": {
            "x": {"fieldName": "yr", "scale": {"type": "categorical"}, "displayName": "Year"},
            "y": {"fieldName": "hr", "scale": {"type": "quantitative"}, "displayName": "Home runs witnessed"},
        },
        "frame": {"showTitle": True, "title": SPEC["title"],
                  "showDescription": True, "description": SPEC["subtitle_pattern"].format(door=door)},
    }
    if brand and t:
        spec["mark"] = {"colors": [t["light"]["bar"]]}
    return {
        "datasets": [{"name": "hr_by_year", "displayName": "HR by year (mv_plays)",
                      "queryLines": [SQL["databricks"].strip()]}],
        "pages": [{"name": "page_1", "displayName": SPEC["title"], "layout": [{
            "widget": {"name": "hr_by_year_bar",
                       "queries": [{"name": "main_query", "query": {
                           "datasetName": "hr_by_year",
                           "fields": [{"name": "yr", "expression": "`yr`"}, {"name": "hr", "expression": "`hr`"}],
                           "disaggregated": True}}],
                       "spec": spec},
            "position": {"x": 0, "y": 0, "width": 6, "height": 7}}]}],
    }


def publish(payload: dict) -> str:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.dashboards import Dashboard
    w = WorkspaceClient(profile="wax_baseball")
    me = w.current_user.me().user_name
    parent = f"/Users/{me}/keeping-score"
    try:
        w.workspace.mkdirs(parent)
    except Exception:  # noqa: BLE001 -- exists
        pass
    existing = next((d for d in w.lakeview.list() if d.display_name == DISPLAY_NAME), None)
    body = json.dumps(payload)
    if existing:
        d = w.lakeview.update(existing.dashboard_id, dashboard=Dashboard(
            display_name=DISPLAY_NAME, warehouse_id=WAREHOUSE_ID, serialized_dashboard=body))
        print(f"  updated dashboard {d.dashboard_id}")
    else:
        d = w.lakeview.create(dashboard=Dashboard(
            display_name=DISPLAY_NAME, warehouse_id=WAREHOUSE_ID, serialized_dashboard=body, parent_path=parent))
        print(f"  created dashboard {d.dashboard_id} at {d.path}")
    w.lakeview.publish(d.dashboard_id, embed_credentials=True, warehouse_id=WAREHOUSE_ID)
    url = f"{w.config.host}/sql/dashboardsv3/{d.dashboard_id}/published"
    print(f"  published: {url}")
    return url


def receipt() -> bool:
    rows = hr_by_year("databricks")
    OUT.mkdir(exist_ok=True)
    csv = OUT / f"{STEM}-databricks.csv"
    csv.write_text("Year,Home Runs\n" + "".join(f"{y},{h}\n" for y, h in rows), encoding="utf-8")
    total, want = sum(h for _, h in rows), SPEC["golden"]["value"]
    print(f"  {SPEC['golden']['label']}: {total} (want {want}) {'PASS' if total == want else 'FAIL'} -- {len(rows)} rows -> {csv.name}")
    return total == want


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--receipt", action="store_true")
    ap.add_argument("--no-brand", action="store_true", help="omit the mark color (the brand-ceiling retry)")
    a = ap.parse_args()
    if not (a.build or a.publish or a.receipt):
        ap.print_help(); return
    ok = True
    payload = serialized(brand=not a.no_brand)
    if a.build:
        OUT.mkdir(exist_ok=True)
        p = OUT / f"{STEM}-lakeview.json"
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"  wrote {p.name}")
    if a.publish:
        publish(payload)
    if a.receipt:
        ok = receipt() and ok
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
