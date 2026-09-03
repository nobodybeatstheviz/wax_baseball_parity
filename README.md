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
run: `sf agent test run --api-name Baseball_Scout_Keeping_Score -o devorg --wait 10 --json > observability\traces\agentforce\<date>-testing-center.json`
(**measured 2026-09-03: this async job can wedge at `IN_PROGRESS` indefinitely with
no error and no timeout** — if it's been stuck more than a couple minutes, kill it
and use the `sf agent preview start`/`send`/`end` trio instead, same capture route
as the reference cell).

Capture a new Claude SDK query-agent run: `wax_baseball_dbt/agents/agent_queries_metric.py`
carries an additive `--trace-out <path>` flag (default behavior unchanged) that writes
every tool call/result plus the full `ResultMessage` (via `dataclasses.asdict`),
wall-clock-timestamped in the capturing process since the SDK emits no per-step
timing of its own:

```powershell
cd C:\Users\georg\Documents\CODING\wax_baseball_dbt
python agents\agent_queries_metric.py --question "How many home runs have I witnessed live at games I attended?" `
  --model sonnet --trace-out ..\wax_baseball_parity\observability\traces\claude_sdk\<date>-g2-semantic-layer.json
```

OTel export (`CLAUDE_CODE_ENABLE_TELEMETRY=1` + `OTEL_METRICS_EXPORTER=console` /
`OTEL_LOGS_EXPORTER=console`) was measured 2026-09-03 and found **broken** on CLI
2.1.257 under individual-plan auth: `claude --debug-file <path>` shows
`isTelemetryEnabled=true` but `getOtlpReaders`/`getOtlpLogExporters` report
`types=[]` and `Created 0 log exporter(s)` — no metric or log line is ever emitted,
on stdout, stderr, or the debug file. The in-process `--trace-out` capture is the
reliable route; don't spend more time on the OTel path without a re-check against a
newer CLI version first.

Capture a new BigQuery Conversational Analytics run: `observability/capture_bigquery_ca.py`
(needs `pip install google-cloud-geminidataanalytics` and `gcloud auth
application-default login` against a project with `geminidataanalytics.googleapis.com`
enabled). Streams `DataChatServiceClient.chat()`, wall-clock-timestamps every message,
and — since the response carries a BigQuery job id — looks that job up afterward for
its real `total_bytes_billed`, so cost is measured, not estimated:

```powershell
cd C:\Users\georg\Documents\CODING\wax_baseball_parity
python observability\capture_bigquery_ca.py --trace-out observability\traces\bigquery_ca\<date>-g2.json
```

Two things measured 2026-09-03, worth knowing before repeating this: the API's own
**discovery document** (`$discovery/rest?version=v1`) 403s even with a valid `gcloud`
OAuth token — the typed Python client is the only route that actually works, the REST
reference docs alone aren't enough to hand-build a request correctly. And **the
Conversational Analytics API's own per-call/token pricing is undocumented** — Google's
pricing page returns no billing figures on fetch; only the BigQuery warehouse scan
underneath a call is priced here (via the job lookup), not the API's own service fee.

Capture a new Databricks Genie run: `observability/capture_databricks_genie.py` (needs
`databricks-sdk`, already installed for the `_dbx_conn.py`/metric-view scripts, and the
`wax_baseball` profile in `~/.databrickscfg`). **The Genie space itself must exist
before this can run — and it cannot be created via API.** `GenieAPI.create_space`'s own
docstring says its `serialized_space` payload is only obtainable by reading back an
*existing* space (`get_space`); there's no documented way to author one from zero. One
space — "Keeping Score", bound to `wax_baseball.semantics`'s five metric views — was
created once through the workspace UI (Wax, 2026-09-03), `space_id
01f1a7accb3713fca8a7ee2e13c8d652`. Everything past that point is fully scriptable, same
as the other three surfaces:

```powershell
cd C:\Users\georg\Documents\CODING\wax_baseball_parity
python observability\capture_databricks_genie.py --space-id 01f1a7accb3713fca8a7ee2e13c8d652 `
  --trace-out observability\traces\databricks_genie\<date>-g2.json
```

Genie's conversation API streams no progress of its own — `start_conversation` returns
a pollable `Wait[GenieMessage]`, and the script calls `get_message` itself in a loop,
wall-clock-timestamping every status change (SUBMITTED → FETCHING_METADATA →
FILTERING_CONTEXT → ASKING_AI → PENDING_WAREHOUSE → **ASKING_AI again** → COMPLETED —
measured 2026-09-03: the model is invoked twice per turn, once to plan the query and
once to phrase the final answer).
