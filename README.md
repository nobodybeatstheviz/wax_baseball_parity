# wax_baseball_parity

Ports the Keeping Score parity corpus — the small, already-attended-games-scoped
dbt marts in BigQuery's `wax_baseball_dbt` dataset (`fct_attended_games`,
`fct_plays`, `fct_game_attendee`, `dim_attendee`, `dim_event_code`,
`fct_games`) — to Snowflake and Databricks, so the same ~15K-row corpus is
queryable identically across all three warehouses. It's a generator, not a
data dump: rerun `scripts/export_bigquery.py` any time the upstream marts
change, then rerun the Databricks loader below (the Snowflake loader lives
in the sibling `wax_baseball_snowflake` repo). Both loaders are idempotent
(`CREATE OR REPLACE TABLE`), so reruns are always safe.

## Rerun

```powershell
# 1. Export BigQuery marts to local Parquet (data/, gitignored)
cd C:\Users\georg\Documents\CODING\wax_baseball_parity
python scripts\export_bigquery.py

# 2. Load into Databricks (wax_baseball.parity, or the lahman_baseball.wax_baseball fallback)
python scripts\load_databricks.py

# 3. Load into Snowflake (BASEBALL.WAX_BASEBALL) - lives in the sibling repo
cd ..\wax_baseball_snowflake
.\scripts\load_wax_baseball_parity.ps1
```

Add a new mart (e.g. `fct_attended_team_games`) by adding one entry to the
`TABLES` list at the top of both `scripts/export_bigquery.py` and
`scripts/load_databricks.py`.

## Observability (phase 2, O7) — `observability/`

The same golden question (G2, home runs witnessed, reference 400) through each
surface's native agent, with what each platform lets you see of how the answer
was reached. Three layers, same shape as the harness:

- **Source** — `observability/traces/<surface>/…`: captured traces, git-tracked,
  never edited. Agentforce traces are copied out of the DX project's gitignored
  `.sfdx/agents/<agent>/sessions/<id>/` (an `sf agent preview` session) or saved
  from `sf agent test run --json` (Testing Center). `surfaces.json` is the
  hand-kept seed for cells that have no trace yet (what the docs say); a row
  leaves it the moment a trace lands for that surface.
- **Analysis** — `observability/extract_observability.py` reads the five rubric
  columns (plan/reasoning · tool-or-SQL · grounding source · tokens+latency ·
  retrieval path) out of the traces. No hand edits.
- **Presentation** — regenerates `wax-system/wax-baseball/observability-receipts.md`,
  every cell marked measured or read.

```powershell
python observability\extract_observability.py
```

Capture a new Agentforce preview session: run `sf agent preview` in the
`wax-baseball-agentforce` project, then copy the session folder into
`observability/traces/agentforce/<date>-preview-session-<id8>/`. A Testing Center
run: `sf agent test run --api-name Baseball_Scout_Keeping_Score -o devorg --wait 10 --json > observability\traces\agentforce\<date>-testing-center.json`.
