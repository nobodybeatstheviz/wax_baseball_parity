#!/usr/bin/env python3
"""
The golden-question parity harness: runs the five golden questions against
every engine holding the Keeping Score corpus and diffs the results against
the reference answers (recorded from BigQuery + MetricFlow, 2026-08-31).

v1 verifies DATA parity: direct SQL against the ported marts. When each
engine's semantic layer lands (W2s Cortex, W3s metric views, W4 SDMs), the
per-engine SQL here upgrades to query THROUGH that semantic layer, making
this definition parity. The reference values do not change either way.

Output: regenerates wax-system/wax-baseball/parity-receipts.md (Presentation
layer — never hand-edited).

Usage:
    python scripts/parity_harness.py

Engines and auth (all pre-verified in Wave 0):
    bigquery   google-cloud-bigquery, ADC
    snowflake  snow CLI, connection wax_baseball_key (keypair)
    databricks databricks-sql-connector via ~/.databrickscfg (see _dbx_conn)
"""

from __future__ import annotations

import datetime
import json
import pathlib
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _dbx_conn import get_connection as dbx_connection  # noqa: E402

from google.cloud import bigquery  # noqa: E402

RECEIPT_PATH = pathlib.Path(r"C:\Users\georg\wax-system\wax-baseball\parity-receipts.md")

BQ_PROJECT = "augmented-world-262319"
BQ = f"`{BQ_PROJECT}.wax_baseball_dbt"          # reference engine: the marts themselves
SF = "BASEBALL.WAX_BASEBALL"                     # ported corpus
DBX = "wax_baseball.parity"                      # ported corpus
SNOW = shutil.which("snow") or r"C:\Users\georg\AppData\Roaming\Python\Python313\Scripts\snow.exe"

# ---------------------------------------------------------------------------
# Reference answers — recorded 2026-08-31 from BigQuery via MetricFlow
# (dbt-core 1.12.3 / metricflow 0.212.0). The parity contract.
# ---------------------------------------------------------------------------

REF_G1 = {
    1984: 1, 1985: 1, 1986: 2, 1987: 3, 1988: 2, 1989: 1, 1990: 1, 1991: 1,
    1992: 3, 1993: 2, 1997: 5, 1998: 6, 1999: 8, 2000: 9, 2001: 17, 2002: 8,
    2003: 17, 2004: 6, 2005: 8, 2006: 9, 2007: 10, 2008: 12, 2009: 8,
    2010: 5, 2011: 11, 2012: 3, 2013: 3, 2014: 1, 2017: 1, 2018: 1,
    2022: 3, 2023: 1, 2024: 5, 2025: 4,
}
REF_G2 = 400                          # home_runs_witnessed
REF_G3 = [("Melissa", 57), ("Bergan", 27), ("Al", 26), ("solo", 16), ("Poppa", 14)]
REF_G4 = {"team": "NYA", "wins": 90, "decided": 143}   # attended_win_rate spot-check
REF_G5 = 44                           # hall_of_famers_seen
REF_SCALARS = {"games_attended": 178, "unique_stadiums": 22, "runs_witnessed": 1706}

# ---------------------------------------------------------------------------
# The questions. Per-engine SQL is intentionally explicit — it is the preview
# of what each engine's semantic layer must re-express in W2s/W3s/W4.
# Snowflake identifiers are quoted lowercase (INFER_SCHEMA preserves Parquet
# column case), matching the Lahman quoted-identifier convention there.
# ---------------------------------------------------------------------------

QUESTIONS = {
    "G1 games attended by year": {
        "kind": "year_counts",
        "reference": REF_G1,
        "bigquery": f"SELECT EXTRACT(YEAR FROM game_date) AS yr, COUNT(*) AS n FROM {BQ}.fct_attended_games` GROUP BY yr ORDER BY yr",
        "snowflake": f'SELECT EXTRACT(YEAR FROM "game_date") AS yr, COUNT(*) AS n FROM {SF}.fct_attended_games GROUP BY yr ORDER BY yr',
        "databricks": f"SELECT EXTRACT(YEAR FROM game_date) AS yr, COUNT(*) AS n FROM {DBX}.fct_attended_games GROUP BY yr ORDER BY yr",
    },
    "G2 home runs witnessed": {
        "kind": "scalar",
        "reference": REF_G2,
        "bigquery": f"SELECT SUM(CASE WHEN event_code = 23 THEN 1 ELSE 0 END) AS v FROM {BQ}.fct_plays`",
        "snowflake": f'SELECT SUM(CASE WHEN "event_code" = 23 THEN 1 ELSE 0 END) AS v FROM {SF}.fct_plays',
        "databricks": f"SELECT SUM(CASE WHEN event_code = 23 THEN 1 ELSE 0 END) AS v FROM {DBX}.fct_plays",
    },
    "G3 top-5 attendees by games": {
        "kind": "ranked",
        "reference": REF_G3,
        "bigquery": f"SELECT attendee_name AS k, COUNT(*) AS n FROM {BQ}.fct_game_attendee` GROUP BY k ORDER BY n DESC, k LIMIT 5",
        "snowflake": f'SELECT "attendee_name" AS k, COUNT(*) AS n FROM {SF}.fct_game_attendee GROUP BY k ORDER BY n DESC, k LIMIT 5',
        "databricks": f"SELECT attendee_name AS k, COUNT(*) AS n FROM {DBX}.fct_game_attendee GROUP BY k ORDER BY n DESC, k LIMIT 5",
    },
    "G4 attended win rate (NYA spot-check)": {
        "kind": "win_rate",
        "reference": REF_G4,
        "bigquery": f"SELECT SUM(CASE WHEN team_won THEN 1 ELSE 0 END) AS wins, SUM(CASE WHEN is_decided THEN 1 ELSE 0 END) AS decided FROM {BQ}.fct_attended_team_games` WHERE team_id = 'NYA'",
        "snowflake": f'SELECT SUM(CASE WHEN "team_won" THEN 1 ELSE 0 END) AS wins, SUM(CASE WHEN "is_decided" THEN 1 ELSE 0 END) AS decided FROM {SF}.fct_attended_team_games WHERE "team_id" = \'NYA\'',
        "databricks": f"SELECT SUM(CASE WHEN team_won THEN 1 ELSE 0 END) AS wins, SUM(CASE WHEN is_decided THEN 1 ELSE 0 END) AS decided FROM {DBX}.fct_attended_team_games WHERE team_id = 'NYA'",
    },
    "G5 Hall of Famers seen": {
        "kind": "scalar",
        "reference": REF_G5,
        "bigquery": f"SELECT COUNT(*) AS v FROM {BQ}.fct_hof_sightings`",
        "snowflake": f"SELECT COUNT(*) AS v FROM {SF}.fct_hof_sightings",
        "databricks": f"SELECT COUNT(*) AS v FROM {DBX}.fct_hof_sightings",
    },
    "G0 corpus scalars (games / stadiums / runs)": {
        "kind": "scalars3",
        "reference": REF_SCALARS,
        "bigquery": f"SELECT (SELECT COUNT(*) FROM {BQ}.fct_attended_games`) AS games_attended, (SELECT COUNT(DISTINCT venue_wax) FROM {BQ}.fct_attended_games`) AS unique_stadiums, (SELECT SUM(runs_on_play) FROM {BQ}.fct_plays`) AS runs_witnessed",
        "snowflake": f'SELECT (SELECT COUNT(*) FROM {SF}.fct_attended_games) AS games_attended, (SELECT COUNT(DISTINCT "venue_wax") FROM {SF}.fct_attended_games) AS unique_stadiums, (SELECT SUM("runs_on_play") FROM {SF}.fct_plays) AS runs_witnessed',
        "databricks": f"SELECT (SELECT COUNT(*) FROM {DBX}.fct_attended_games) AS games_attended, (SELECT COUNT(DISTINCT venue_wax) FROM {DBX}.fct_attended_games) AS unique_stadiums, (SELECT SUM(runs_on_play) FROM {DBX}.fct_plays) AS runs_witnessed",
    },
}

ENGINES = ["bigquery", "snowflake", "databricks"]


# ---------------------------------------------------------------------------
# Engine runners — each returns a list of dicts with lowercase keys.
# ---------------------------------------------------------------------------

def run_bigquery(sql: str) -> list[dict]:
    client = bigquery.Client(project=BQ_PROJECT)
    return [{k.lower(): v for k, v in dict(row).items()} for row in client.query(sql).result()]


def run_snowflake(sql: str) -> list[dict]:
    out = subprocess.run(
        [SNOW, "sql", "-c", "wax_baseball_key", "--format", "json", "-q", sql],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"snow sql failed: {out.stderr.strip()[:500]}")
    return [{k.lower(): v for k, v in row.items()} for row in json.loads(out.stdout)]


_dbx_conn = None


def run_databricks(sql: str) -> list[dict]:
    global _dbx_conn
    if _dbx_conn is None:
        _dbx_conn = dbx_connection()
    cursor = _dbx_conn.cursor()
    cursor.execute(sql)
    cols = [d[0].lower() for d in cursor.description]
    rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    cursor.close()
    return rows


RUNNERS = {"bigquery": run_bigquery, "snowflake": run_snowflake, "databricks": run_databricks}


# ---------------------------------------------------------------------------
# Comparators per question kind: (rows, reference) -> (pass, observed_summary)
# ---------------------------------------------------------------------------

def compare(kind: str, rows: list[dict], ref):
    if kind == "scalar":
        got = int(rows[0]["v"])
        return got == ref, str(got)
    if kind == "scalars3":
        got = {k: int(rows[0][k]) for k in ref}
        return got == ref, " / ".join(str(got[k]) for k in ref)
    if kind == "year_counts":
        got = {int(r["yr"]): int(r["n"]) for r in rows}
        return got == ref, f"{len(got)} years, sum {sum(got.values())}"
    if kind == "ranked":
        got = [(str(r["k"]), int(r["n"])) for r in rows]
        return got == ref, ", ".join(f"{k} {n}" for k, n in got)
    if kind == "win_rate":
        got = {"team": ref["team"], "wins": int(rows[0]["wins"]), "decided": int(rows[0]["decided"])}
        return got == ref, f"{got['wins']}-{got['decided'] - got['wins']} in {got['decided']} decided"
    raise ValueError(kind)


def main() -> None:
    results: dict[str, dict[str, tuple[bool, str]]] = {}
    for q, spec in QUESTIONS.items():
        results[q] = {}
        for engine in ENGINES:
            try:
                rows = RUNNERS[engine](spec[engine])
                results[q][engine] = compare(spec["kind"], rows, spec["reference"])
            except Exception as exc:  # noqa: BLE001 — a failing engine is a finding, not a crash
                results[q][engine] = (False, f"ERROR: {str(exc)[:120]}")
            ok, obs = results[q][engine]
            print(f"  {q:44s} {engine:10s} {'PASS' if ok else 'FAIL'}  {obs}")

    all_pass = all(ok for per_q in results.values() for ok, _ in per_q.values())

    stamp = datetime.date.today().isoformat()
    lines = [
        "# Parity receipts — Keeping Score",
        "",
        "<!-- Generated - do not hand-edit. Rebuild: py scripts/parity_harness.py",
        "     in CODING/wax_baseball_parity (v1 = data parity over the ported marts;",
        "     upgrades to semantic-layer parity as W2s/W3s/W4 land). -->",
        "",
        f"*Generated {stamp}. Reference answers: BigQuery via MetricFlow, recorded 2026-08-31.*",
        "",
        f"**Overall: {'✅ all engines match the reference' if all_pass else '❌ MISMATCH — see table'}**",
        "",
        "| Golden question | Reference | " + " | ".join(ENGINES) + " | D360 |",
        "|---|---|" + "---|" * len(ENGINES) + "---|",
    ]
    ref_display = {
        "G1 games attended by year": "34 years, sum 178 (peaks 2001=17, 2003=17)",
        "G2 home runs witnessed": "400",
        "G3 top-5 attendees by games": "Melissa 57, Bergan 27, Al 26, solo 16, Poppa 14",
        "G4 attended win rate (NYA spot-check)": "90-53 in 143 decided (.629)",
        "G5 Hall of Famers seen": "44",
        "G0 corpus scalars (games / stadiums / runs)": "178 / 22 / 1706",
    }
    for q in QUESTIONS:
        cells = []
        for engine in ENGINES:
            ok, obs = results[q][engine]
            cells.append(f"{'✅' if ok else '❌'} {obs}")
        lines.append(f"| {q} | {ref_display[q]} | " + " | ".join(cells) + " | ⬜ awaits W4 |")

    lines += [
        "",
        "The identical corpus behind these numbers: BigQuery `wax_baseball_dbt` (reference) · "
        "Snowflake `BASEBALL.WAX_BASEBALL` · Databricks `wax_baseball.parity` — 8 marts, "
        "ported by the generators in `CODING/wax_baseball_parity` + "
        "`CODING/wax_baseball_snowflake`.",
        "",
    ]
    RECEIPT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {RECEIPT_PATH}")
    if not all_pass:
        sys.exit(1)


if __name__ == "__main__":
    main()
