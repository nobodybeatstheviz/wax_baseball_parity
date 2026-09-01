#!/usr/bin/env python3
"""
The golden-question parity harness — v2: DEFINITION parity.

Each engine answers the golden questions THROUGH ITS OWN SEMANTIC LAYER:
    bigquery    MetricFlow (dbt semantic layer, via the mf CLI + SL venv)
    databricks  Unity Catalog metric views (MEASURE() queries, W3s)
    snowflake   Cortex semantic view (W2s; raw-SQL fallback marked until wired)

and the results are diffed against the reference answers recorded from
BigQuery + MetricFlow on 2026-08-31. v1 (data parity, raw SQL over the
ported marts) lives in git history.

Output: regenerates wax-system/wax-baseball/parity-receipts.md (Presentation
layer — never hand-edited).

Usage:
    python scripts/parity_harness.py
"""

from __future__ import annotations

import csv
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _dbx_conn import get_connection as dbx_connection  # noqa: E402

RECEIPT_PATH = pathlib.Path(r"C:\Users\georg\wax-system\wax-baseball\parity-receipts.md")

BQ_PROJECT = "augmented-world-262319"
DBT_PROJECT_DIR = r"C:\Users\georg\Documents\CODING\wax_baseball_dbt"
MF_EXE = r"C:\Users\georg\Documents\CODING\dbt-core-sl-venv\Scripts\mf.exe"
SF = "BASEBALL.WAX_BASEBALL"                 # ported corpus (raw-SQL fallback)
DBX_MV = "wax_baseball.semantics"            # UC metric views (W3s)
SNOW = shutil.which("snow") or r"C:\Users\georg\AppData\Roaming\Python\Python313\Scripts\snow.exe"

ENGINES = ["bigquery", "databricks", "snowflake"]
ENGINE_LAYER = {
    "bigquery": "MetricFlow (dbt SL)",
    "databricks": "UC metric views",
    "snowflake": "native SEMANTIC VIEW (BASEBALL.SEMANTICS.KEEPING_SCORE)",
}

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
REF_G2 = 400
REF_G3 = [("Melissa", 57), ("Bergan", 27), ("Al", 26), ("solo", 16), ("Poppa", 14)]
REF_G4 = {"wins": 90, "decided": 143}
REF_G5 = 44
REF_G0A = {"games_attended": 178, "unique_stadiums": 22}
REF_G0B = 1706

# ---------------------------------------------------------------------------
# Per-engine question specs. Each spec is ("mf", [cli args]) or ("sql", text).
# Comparators consume rows POSITIONALLY (column order is part of the spec),
# so MetricFlow's dunder headers and SQL aliases don't need to agree.
# ---------------------------------------------------------------------------

QUESTIONS = {
    "G1 games attended by year": {
        "kind": "year_counts",
        "reference": REF_G1,
        "bigquery": ("mf", ["--metrics", "games_attended", "--group-by", "metric_time__year", "--order", "metric_time__year"]),
        "databricks": ("sql", f"SELECT YEAR(game_date) AS yr, MEASURE(games_attended) AS n FROM {DBX_MV}.mv_attended_games GROUP BY YEAR(game_date) ORDER BY yr"),
        "snowflake": ("sql", "SELECT * FROM SEMANTIC_VIEW(BASEBALL.SEMANTICS.KEEPING_SCORE DIMENSIONS attended_games.year METRICS attended_games.games_attended) ORDER BY YEAR"),
    },
    "G2 home runs witnessed": {
        "kind": "scalar",
        "reference": REF_G2,
        "bigquery": ("mf", ["--metrics", "home_runs_witnessed"]),
        "databricks": ("sql", f"SELECT MEASURE(home_runs_witnessed) AS v FROM {DBX_MV}.mv_plays"),
        "snowflake": ("sql", "SELECT * FROM SEMANTIC_VIEW(BASEBALL.SEMANTICS.KEEPING_SCORE METRICS plays.home_runs_witnessed)"),
    },
    "G3 top-5 attendees by games": {
        "kind": "ranked",
        "reference": REF_G3,
        "bigquery": ("mf", ["--metrics", "games_per_attendee", "--group-by", "game_attendee__attendee_name", "--order", "-games_per_attendee", "--limit", "5"]),
        "databricks": ("sql", f"SELECT attendee_name AS k, MEASURE(games_per_attendee) AS n FROM {DBX_MV}.mv_game_attendee GROUP BY attendee_name ORDER BY n DESC, k LIMIT 5"),
        "snowflake": ("sql", "SELECT * FROM SEMANTIC_VIEW(BASEBALL.SEMANTICS.KEEPING_SCORE DIMENSIONS game_attendee.attendee_name METRICS game_attendee.games_per_attendee) ORDER BY GAMES_PER_ATTENDEE DESC, ATTENDEE_NAME LIMIT 5"),
    },
    "G4 attended win rate (NYA spot-check)": {
        "kind": "win_rate",
        "reference": REF_G4,
        "bigquery": ("mf", ["--metrics", "team_wins_attended,team_games_decided", "--group-by", "attended_team_game__team", "--where", "{{ Dimension('attended_team_game__team') }} = 'NYA'"]),
        "databricks": ("sql", f"SELECT team_id, MEASURE(team_wins_attended) AS wins, MEASURE(team_games_decided) AS decided FROM {DBX_MV}.mv_attended_team_games WHERE team_id = 'NYA' GROUP BY team_id"),
        "snowflake": ("sql", "SELECT * FROM SEMANTIC_VIEW(BASEBALL.SEMANTICS.KEEPING_SCORE DIMENSIONS attended_team_games.team_id METRICS attended_team_games.team_wins_attended, attended_team_games.team_games_decided) WHERE TEAM_ID = 'NYA'"),
    },
    "G5 Hall of Famers seen": {
        "kind": "scalar",
        "reference": REF_G5,
        "bigquery": ("mf", ["--metrics", "hall_of_famers_seen"]),
        "databricks": ("sql", f"SELECT MEASURE(hall_of_famers_seen) AS v FROM {DBX_MV}.mv_hof_sightings"),
        "snowflake": ("sql", "SELECT * FROM SEMANTIC_VIEW(BASEBALL.SEMANTICS.KEEPING_SCORE METRICS hof_sightings.hall_of_famers_seen)"),
    },
    "G0a games attended / unique stadiums": {
        "kind": "pair",
        "reference": REF_G0A,
        "bigquery": ("mf", ["--metrics", "games_attended,unique_stadiums"]),
        "databricks": ("sql", f"SELECT MEASURE(games_attended) AS a, MEASURE(unique_stadiums) AS b FROM {DBX_MV}.mv_attended_games"),
        "snowflake": ("sql", "SELECT * FROM SEMANTIC_VIEW(BASEBALL.SEMANTICS.KEEPING_SCORE METRICS attended_games.games_attended, attended_games.unique_stadiums)"),
    },
    "G0b runs witnessed": {
        "kind": "scalar",
        "reference": REF_G0B,
        "bigquery": ("mf", ["--metrics", "runs_witnessed"]),
        "databricks": ("sql", f"SELECT MEASURE(runs_witnessed) AS v FROM {DBX_MV}.mv_plays"),
        "snowflake": ("sql", "SELECT * FROM SEMANTIC_VIEW(BASEBALL.SEMANTICS.KEEPING_SCORE METRICS plays.runs_witnessed)"),
    },
}


# ---------------------------------------------------------------------------
# Engine runners — each returns rows as list-of-lists (positional).
# ---------------------------------------------------------------------------

def run_bigquery(spec) -> list[list]:
    """MetricFlow via the SL venv's mf CLI, CSV output."""
    _, args = spec
    with tempfile.TemporaryDirectory() as tmp:
        out_csv = pathlib.Path(tmp) / "out.csv"
        env = dict(os.environ, DBT_PROFILES_DIR=r"C:\Users\georg\.dbt", PYTHONUTF8="1")
        result = subprocess.run(
            [MF_EXE, "query", *args, "--csv", str(out_csv)],
            capture_output=True, text=True, cwd=DBT_PROJECT_DIR, env=env,
        )
        if result.returncode != 0 or not out_csv.exists():
            raise RuntimeError(f"mf query failed: {(result.stderr or result.stdout).strip()[:300]}")
        with out_csv.open(newline="", encoding="utf-8") as fh:
            rows = [row for row in csv.reader(fh) if row]
        # mf --csv may or may not emit a header row; detect by whether the
        # last cell of row 0 parses as a number (all our queries end numeric).
        if rows:
            try:
                float(rows[0][-1])
            except ValueError:
                rows = rows[1:]
        return rows


def run_snowflake(spec) -> list[list]:
    _, sql = spec
    out = subprocess.run(
        [SNOW, "sql", "-c", "wax_baseball_key", "--format", "json", "-q", sql],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"snow sql failed: {out.stderr.strip()[:300]}")
    return [list(row.values()) for row in json.loads(out.stdout)]


_dbx_conn = None


def run_databricks(spec) -> list[list]:
    global _dbx_conn
    if _dbx_conn is None:
        _dbx_conn = dbx_connection()
    _, sql = spec
    cursor = _dbx_conn.cursor()
    cursor.execute(sql)
    rows = [list(r) for r in cursor.fetchall()]
    cursor.close()
    return rows


RUNNERS = {"bigquery": run_bigquery, "snowflake": run_snowflake, "databricks": run_databricks}


# ---------------------------------------------------------------------------
# Comparators — positional. (rows, reference) -> (pass, observed_summary)
# ---------------------------------------------------------------------------

def _year(v) -> int:
    return int(str(v)[:4])


def compare(kind: str, rows: list[list], ref):
    if kind == "scalar":
        got = int(float(rows[0][0]))
        return got == ref, str(got)
    if kind == "pair":
        a, b = (int(float(rows[0][0])), int(float(rows[0][1])))
        want = list(ref.values())
        return [a, b] == want, f"{a} / {b}"
    if kind == "year_counts":
        got = {_year(r[0]): int(float(r[1])) for r in rows}
        return got == ref, f"{len(got)} years, sum {sum(got.values())}"
    if kind == "ranked":
        got = [(str(r[0]), int(float(r[1]))) for r in rows]
        return got == ref, ", ".join(f"{k} {n}" for k, n in got)
    if kind == "win_rate":
        wins, decided = int(float(rows[0][-2])), int(float(rows[0][-1]))
        ok = wins == ref["wins"] and decided == ref["decided"]
        return ok, f"{wins}-{decided - wins} in {decided} decided"
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
            print(f"  {q:40s} {engine:10s} {'PASS' if ok else 'FAIL'}  {obs}")

    all_pass = all(ok for per_q in results.values() for ok, _ in per_q.values())

    stamp = datetime.date.today().isoformat()
    lines = [
        "# Parity receipts — Keeping Score",
        "",
        "<!-- Generated - do not hand-edit. Rebuild: py scripts/parity_harness.py",
        "     in CODING/wax_baseball_parity. v2 = definition parity: each engine",
        "     answers through its own semantic layer. -->",
        "",
        f"*Generated {stamp}. Reference answers: BigQuery via MetricFlow, recorded 2026-08-31.*",
        "",
        "**Answering layer per engine:** "
        + " · ".join(f"{e} = {ENGINE_LAYER[e]}" for e in ENGINES),
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
        "G0a games attended / unique stadiums": "178 / 22",
        "G0b runs witnessed": "1706",
    }
    for q in QUESTIONS:
        cells = []
        for engine in ENGINES:
            ok, obs = results[q][engine]
            cells.append(f"{'✅' if ok else '❌'} {obs}")
        lines.append(f"| {q} | {ref_display[q]} | " + " | ".join(cells) + " | ⬜ awaits W4 |")

    lines += [
        "",
        "Corpus: BigQuery `wax_baseball_dbt` (reference) · Snowflake `BASEBALL.WAX_BASEBALL` · "
        "Databricks `wax_baseball.parity` (semantic layer: `wax_baseball.semantics` metric views) — "
        "8 marts, ported by the generators in `CODING/wax_baseball_parity` + "
        "`CODING/wax_baseball_snowflake`.",
        "",
    ]
    RECEIPT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {RECEIPT_PATH}")
    if not all_pass:
        sys.exit(1)


if __name__ == "__main__":
    main()
