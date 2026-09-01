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
