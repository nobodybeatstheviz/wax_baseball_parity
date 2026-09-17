"""query.py -- the one query per engine that yields HR-by-year rows for the Build 2.5 doors.

Source:   each engine's governed object (dbt mart on BigQuery · Snowflake semantic view · Databricks
          metric view). The number (400) is the parity harness's G2; this module only adds the by-year cut.
Analysis: this file. `hr_by_year(engine)` -> [(year:int, hr:int), ...] sorted by year.
Presentation: whatever a door's generator emits from those rows.

Measured 2026-09-16: bigquery -> 34 rows, sum 400, identical to the Tableau Cloud receipt
(workbooks/keeping-score-hr-by-year.csv in wax_baseball_w5_datasource). snowflake / databricks are the
harness's proven connection patterns with the plan's SQL; run them when their doors open.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

BQ_PROJECT = "augmented-world-262319"

SQL = {
    "bigquery": f"""
        SELECT EXTRACT(YEAR FROM game_date) AS yr,
               SUM(CASE WHEN event_code = 23 THEN 1 ELSE 0 END) AS hr
        FROM `{BQ_PROJECT}.wax_baseball_dbt.fct_plays`
        GROUP BY yr ORDER BY yr""",
    # the semantic view already carries play_year (sql/20_semantic_view_wax_baseball.sql:87)
    "snowflake": """
        SELECT * FROM SEMANTIC_VIEW(
            BASEBALL.SEMANTICS.KEEPING_SCORE
            DIMENSIONS plays.play_year
            METRICS    plays.home_runs_witnessed)
        ORDER BY PLAY_YEAR""",
    # mv_plays has no year dimension -- derive it, as the harness does for G1
    "databricks": """
        SELECT YEAR(game_date) AS yr, MEASURE(home_runs_witnessed) AS hr
        FROM wax_baseball.semantics.mv_plays
        GROUP BY YEAR(game_date) ORDER BY yr""",
}


def _bigquery() -> list[tuple[int, int]]:
    from google.cloud import bigquery  # ADC: gcloud auth application-default login
    client = bigquery.Client(project=BQ_PROJECT)
    return [(int(r.yr), int(r.hr)) for r in client.query(SQL["bigquery"]).result()]


def _snowflake() -> list[tuple[int, int]]:
    snow = os.environ.get("SNOW_EXE", "snow")
    out = subprocess.run([snow, "sql", "-c", "wax_baseball_key", "--format", "json", "-q", SQL["snowflake"]],
                         capture_output=True, text=True, encoding="utf-8", shell=(os.name == "nt"))
    if out.returncode:
        raise RuntimeError(out.stderr[-800:])
    rows = json.loads(out.stdout[out.stdout.index("["):])
    return sorted((int(r["PLAY_YEAR"]), int(r["HOME_RUNS_WITNESSED"])) for r in rows)


def _databricks() -> list[tuple[int, int]]:
    from _dbx_conn import get_connection
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(SQL["databricks"])
        return [(int(y), int(h)) for y, h in cur.fetchall()]


ENGINES = {"bigquery": _bigquery, "snowflake": _snowflake, "databricks": _databricks}


def hr_by_year(engine: str = "bigquery") -> list[tuple[int, int]]:
    rows = ENGINES[engine]()
    return sorted(rows)


if __name__ == "__main__":
    eng = sys.argv[1] if len(sys.argv) > 1 else "bigquery"
    rows = hr_by_year(eng)
    print(f"{eng}: {len(rows)} rows, sum {sum(h for _, h in rows)}")
    for y, h in rows:
        print(f"{y},{h}")
