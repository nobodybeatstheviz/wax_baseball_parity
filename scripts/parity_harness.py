#!/usr/bin/env python3
"""
The golden-question parity harness — v2: DEFINITION parity.

Each engine answers the golden questions THROUGH ITS OWN SEMANTIC LAYER:
    bigquery    MetricFlow (dbt semantic layer, via the mf CLI + SL venv)
    databricks  Unity Catalog metric views (MEASURE() queries, W3s)
    snowflake   Cortex semantic view (W2s; raw-SQL fallback marked until wired)
    d360        Keeping_Score SDM via /semantic-engine/gateway (W4) — raw REST
                through `sf api request rest` (same transport as apply_sdm.py;
                the d360 MCP query tool wraps this same gateway). Org alias via
                D360_ORG env var (default devorg); the model id is resolved by
                apiName at runtime, so the scratch-org replay needs no edits.
    tableau_next  the SAME Keeping_Score SDM, reached through Tableau Next's
                own surface: the Salesforce Hosted MCP server
                `analytics/tableau-next-pilot` → `run_semantic_query` (W6a,
                2026-09-05). Same definitions, different transport and query
                dialect (proto-shaped snake_case) — a surface-parity column,
                driven deterministically over MCP-HTTP with Claude Code's OAuth
                (scripts/_hosted_mcp.py). Requires `claude mcp login
                tableau-next-pilot` once.

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
from _hosted_mcp import HostedMcp, semantic_query_rows, to_snake_query  # noqa: E402

RECEIPT_PATH = pathlib.Path(r"C:\Users\georg\wax-system\wax-baseball\parity-receipts.md")

BQ_PROJECT = "augmented-world-262319"
DBT_PROJECT_DIR = r"C:\Users\georg\Documents\CODING\wax_baseball_dbt"
MF_EXE = r"C:\Users\georg\Documents\CODING\dbt-core-sl-venv\Scripts\mf.exe"
SF = "BASEBALL.WAX_BASEBALL"                 # ported corpus (raw-SQL fallback)
DBX_MV = "wax_baseball.semantics"            # UC metric views (W3s)
SNOW = shutil.which("snow") or r"C:\Users\georg\AppData\Roaming\Python\Python313\Scripts\snow.exe"
SF_EXE = shutil.which("sf")                  # npm shim — shutil.which resolves sf.cmd
D360_ORG = os.environ.get("D360_ORG", "devorg")
D360_MODEL = "Keeping_Score"
D360_GATEWAY = "/services/data/v66.0/semantic-engine/gateway"

TN_MCP_SERVER = os.environ.get("TN_MCP_SERVER", "tableau-next-pilot")

ENGINES = ["bigquery", "databricks", "snowflake", "d360", "tableau_next"]
ENGINE_LAYER = {
    "bigquery": "MetricFlow (dbt SL)",
    "databricks": "UC metric views",
    "snowflake": "native SEMANTIC VIEW (BASEBALL.SEMANTICS.KEEPING_SCORE)",
    "d360": f"Keeping_Score SDM (/semantic-engine/gateway, org {D360_ORG})",
    "tableau_next": f"Keeping_Score SDM via the hosted Tableau Next MCP (`{TN_MCP_SERVER}` · run_semantic_query)",
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
# Per-engine question specs. Each spec is ("mf", [cli args]), ("sql", text),
# or ("sdm", structuredSemanticQuery, transform-name-or-None).
# Comparators consume rows POSITIONALLY (column order is part of the spec),
# so MetricFlow's dunder headers and SQL aliases don't need to agree.
#
# SDM notes: calc measures/dims are MODEL-level -> semanticField; raw columns
# -> tableField with tableName. The gateway has no documented order/filter
# syntax, so G3's top-5 and G4's NYA selection are named client-side
# transforms — the DEFINITION stays team/attendee-as-dimension either way.
# ---------------------------------------------------------------------------


def _sf(name: str, alias: str, group: bool = False) -> dict:
    field = {"expression": {"semanticField": {"name": name}}, "alias": alias}
    if group:
        field["rowGrouping"] = True
    return field


def _tf(table: str, name: str, alias: str) -> dict:
    return {"rowGrouping": True, "alias": alias,
            "expression": {"tableField": {"name": name, "tableName": table}}}


def _sdm(fields: list[dict], transform: str | None = None, limit: int = 100):
    return ("sdm", {"fields": fields, "options": {"limitOptions": {"limit": limit}}}, transform)


SDM_TRANSFORMS = {
    "top5": lambda rows: sorted(rows, key=lambda r: (-int(float(r[1])), str(r[0])))[:5],
    "nya": lambda rows: [r for r in rows if str(r[0]) == "NYA"],
}

QUESTIONS = {
    "G1 games attended by year": {
        "kind": "year_counts",
        "reference": REF_G1,
        "bigquery": ("mf", ["--metrics", "games_attended", "--group-by", "metric_time__year", "--order", "metric_time__year"]),
        "databricks": ("sql", f"SELECT YEAR(game_date) AS yr, MEASURE(games_attended) AS n FROM {DBX_MV}.mv_attended_games GROUP BY YEAR(game_date) ORDER BY yr"),
        "snowflake": ("sql", "SELECT * FROM SEMANTIC_VIEW(BASEBALL.SEMANTICS.KEEPING_SCORE DIMENSIONS attended_games.year METRICS attended_games.games_attended) ORDER BY YEAR"),
        "d360": _sdm([_sf("Game_Year", "yr", group=True), _sf("Games_Attended", "n")]),
    },
    "G2 home runs witnessed": {
        "kind": "scalar",
        "reference": REF_G2,
        "bigquery": ("mf", ["--metrics", "home_runs_witnessed"]),
        "databricks": ("sql", f"SELECT MEASURE(home_runs_witnessed) AS v FROM {DBX_MV}.mv_plays"),
        "snowflake": ("sql", "SELECT * FROM SEMANTIC_VIEW(BASEBALL.SEMANTICS.KEEPING_SCORE METRICS plays.home_runs_witnessed)"),
        "d360": _sdm([_sf("Home_Runs_Witnessed", "hr")]),
    },
    "G3 top-5 attendees by games": {
        "kind": "ranked",
        "reference": REF_G3,
        "bigquery": ("mf", ["--metrics", "games_per_attendee", "--group-by", "game_attendee__attendee_name", "--order", "-games_per_attendee", "--limit", "5"]),
        "databricks": ("sql", f"SELECT attendee_name AS k, MEASURE(games_per_attendee) AS n FROM {DBX_MV}.mv_game_attendee GROUP BY attendee_name ORDER BY n DESC, k LIMIT 5"),
        "snowflake": ("sql", "SELECT * FROM SEMANTIC_VIEW(BASEBALL.SEMANTICS.KEEPING_SCORE DIMENSIONS game_attendee.attendee_name METRICS game_attendee.games_per_attendee) ORDER BY GAMES_PER_ATTENDEE DESC, ATTENDEE_NAME LIMIT 5"),
        "d360": _sdm([_tf("Game_Attendee", "attendee_name", "k"), _sf("Games_per_Attendee", "n")], transform="top5"),
    },
    "G4 attended win rate (NYA spot-check)": {
        "kind": "win_rate",
        "reference": REF_G4,
        "bigquery": ("mf", ["--metrics", "team_wins_attended,team_games_decided", "--group-by", "attended_team_game__team", "--where", "{{ Dimension('attended_team_game__team') }} = 'NYA'"]),
        "databricks": ("sql", f"SELECT team_id, MEASURE(team_wins_attended) AS wins, MEASURE(team_games_decided) AS decided FROM {DBX_MV}.mv_attended_team_games WHERE team_id = 'NYA' GROUP BY team_id"),
        "snowflake": ("sql", "SELECT * FROM SEMANTIC_VIEW(BASEBALL.SEMANTICS.KEEPING_SCORE DIMENSIONS attended_team_games.team_id METRICS attended_team_games.team_wins_attended, attended_team_games.team_games_decided) WHERE TEAM_ID = 'NYA'"),
        "d360": _sdm([_tf("Attended_Team_Games", "team_id", "team"), _sf("Team_Wins_Attended", "wins"), _sf("Team_Games_Decided", "decided")], transform="nya"),
    },
    "G5 Hall of Famers seen": {
        "kind": "scalar",
        "reference": REF_G5,
        "bigquery": ("mf", ["--metrics", "hall_of_famers_seen"]),
        "databricks": ("sql", f"SELECT MEASURE(hall_of_famers_seen) AS v FROM {DBX_MV}.mv_hof_sightings"),
        "snowflake": ("sql", "SELECT * FROM SEMANTIC_VIEW(BASEBALL.SEMANTICS.KEEPING_SCORE METRICS hof_sightings.hall_of_famers_seen)"),
        "d360": _sdm([_sf("Hall_of_Famers_Seen", "hof")]),
    },
    "G0a games attended / unique stadiums": {
        "kind": "pair",
        "reference": REF_G0A,
        "bigquery": ("mf", ["--metrics", "games_attended,unique_stadiums"]),
        "databricks": ("sql", f"SELECT MEASURE(games_attended) AS a, MEASURE(unique_stadiums) AS b FROM {DBX_MV}.mv_attended_games"),
        "snowflake": ("sql", "SELECT * FROM SEMANTIC_VIEW(BASEBALL.SEMANTICS.KEEPING_SCORE METRICS attended_games.games_attended, attended_games.unique_stadiums)"),
        "d360": _sdm([_sf("Games_Attended", "a"), _sf("Unique_Stadiums", "b")]),
    },
    "G0b runs witnessed": {
        "kind": "scalar",
        "reference": REF_G0B,
        "bigquery": ("mf", ["--metrics", "runs_witnessed"]),
        "databricks": ("sql", f"SELECT MEASURE(runs_witnessed) AS v FROM {DBX_MV}.mv_plays"),
        "snowflake": ("sql", "SELECT * FROM SEMANTIC_VIEW(BASEBALL.SEMANTICS.KEEPING_SCORE METRICS plays.runs_witnessed)"),
        "d360": _sdm([_sf("Runs_Witnessed", "r")]),
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


_d360_model_id: str | None = None


def _sf_rest(endpoint: str, payload: dict | None = None) -> dict:
    """POST (or GET when payload is None) via the sf CLI's auth for D360_ORG —
    the same transport apply_sdm.py proved out."""
    cmd = [SF_EXE, "api", "request", "rest", endpoint, "-o", D360_ORG]
    tmp = None
    if payload is not None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(payload, fh)
            tmp = fh.name
        cmd += ["--method", "POST", "--body", f"@{tmp}", "--header", "Content-Type: application/json"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True)
        text = (out.stdout or out.stderr).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise RuntimeError(f"sf api request non-JSON: {text[:200]}")
    finally:
        if tmp:
            pathlib.Path(tmp).unlink(missing_ok=True)


def run_d360(spec) -> list[list]:
    global _d360_model_id
    if _d360_model_id is None:
        models = _sf_rest("/services/data/v66.0/ssot/semantic/models")
        match = [m for m in models.get("items", []) if m.get("apiName") == D360_MODEL]
        if not match:
            raise RuntimeError(f"SDM {D360_MODEL} not found in org {D360_ORG}")
        _d360_model_id = match[0]["id"]
    _, query, transform = spec
    data = _sf_rest(D360_GATEWAY, {"semanticModelId": _d360_model_id, "structuredSemanticQuery": query})
    if data.get("status") != "SUCCESS":
        raise RuntimeError(f"semantic query failed: {json.dumps(data)[:200]}")
    rows = [list(r["values"]) for r in data["queryResults"]["queryData"]["rows"]]
    return SDM_TRANSFORMS[transform](rows) if transform else rows


_tn_mcp: HostedMcp | None = None


def run_tableau_next(spec) -> list[list]:
    """The d360 spec, re-dialected: same fields/transform, sent as the Beta MCP's
    proto-shaped structuredSemanticQuery. One MCP session per harness run."""
    global _tn_mcp
    if _tn_mcp is None:
        _tn_mcp = HostedMcp(TN_MCP_SERVER)
    _, query, transform = spec
    res = _tn_mcp.call("run_semantic_query", {
        "semanticModelApiName": D360_MODEL,
        "source": "wax_baseball_parity",
        "structuredSemanticQuery": to_snake_query(query),
    })
    rows = semantic_query_rows(res)
    return SDM_TRANSFORMS[transform](rows) if transform else rows


RUNNERS = {"bigquery": run_bigquery, "snowflake": run_snowflake,
           "databricks": run_databricks, "d360": run_d360,
           "tableau_next": run_tableau_next}

# tableau_next answers the d360 spec through its own transport — one definition, two surfaces.
for _q in QUESTIONS.values():
    _q.setdefault("tableau_next", _q["d360"])


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
        "| Golden question | Reference | " + " | ".join(ENGINES) + " |",
        "|---|---|" + "---|" * len(ENGINES),
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
        lines.append(f"| {q} | {ref_display[q]} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "Corpus: BigQuery `wax_baseball_dbt` (reference) · Snowflake `BASEBALL.WAX_BASEBALL` · "
        "Databricks `wax_baseball.parity` (semantic layer: `wax_baseball.semantics` metric views) — "
        "8 marts, ported by the generators in `CODING/wax_baseball_parity` + "
        "`CODING/wax_baseball_snowflake`. D360: two-cloud zero-copy federation "
        "(BigQuery + Databricks) + `Keeping_Score` SDM, deployed by "
        "`CODING/wax_baseball_datacloud_deploy` — queried through the semantic-engine "
        "gateway, org-alias-parameterized for the scratch-org replay. Tableau Next: the same SDM "
        f"through the Salesforce Hosted MCP server `analytics/{TN_MCP_SERVER}` (`run_semantic_query`), "
        "authenticated with Claude Code's OAuth for that server — the six-measure single-call form "
        "hits the same `NO_PATH` join-graph limit D360 does, so questions run one join tree at a time.",
        "",
    ]
    if _tn_mcp is not None:
        _tn_mcp.close()
    RECEIPT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {RECEIPT_PATH}")
    if not all_pass:
        sys.exit(1)


if __name__ == "__main__":
    main()
