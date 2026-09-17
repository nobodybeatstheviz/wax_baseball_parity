# viz — the same chart on every door (Keeping Score, Build 2.5)

One question — **home runs I witnessed, by year** (400, the parity harness's G2) — as one bar chart,
remade on each tool a Tableau practitioner is being told to cut over to. The harness next door proves
the *number* is identical everywhere; this folder proves the *picture* is, and writes down how each
door was opened headlessly and where headless stopped.

Three layers, same as the harness:

- **Source** — `spec/hr_by_year.json` (the chart: measure, by-what, sort, title rule) and the NBTV chart
  tokens at `~/.claude/skills/nbtv-design/tokens/chart.json` (one home; nothing copies it). The rows
  come from each engine's governed object through `query.py`.
- **Analysis** — one generator per door (below). `query.py` is shared: `hr_by_year(engine)` → `[(year, hr)]`.
- **Presentation** — `out/` (gitignored except the receipts): the page or workbook, a CSV that sums to 400,
  a PNG for the site's `assets/`.

**Brand is a ceiling, never a blocker.** Floor = the number and the sort. Each door applies what its tool
takes cheaply and the receipt says what it didn't. Fonts are hard; defaults are fine.

## Doors

| Door | Inning | Generator | Headless to… | Where headless stops | State |
|---|---|---|---|---|---|
| Tableau Cloud | 1st | `../../wax_baseball_w5_datasource/build_workbook.py` | publish + PNG/CSV receipt via the Tableau MCP; NBTV mark color + fonts as a `<style>` block from `chart.json` | nowhere — the red bars took (font: default in the PNG, the server accepted the rule but the render didn't show it) | ✅ 9/10 · restyled 9/17 |
| **Claude artifact** | 8th | `build_artifact.py` | the HTML + CSV + PNG; the Artifact tool publishes | nowhere | ✅ **2026-09-16** |
| **Tableau Next** | 3rd | `build_tn_viz.py` | workspace + viz created through the Beta MCP's `create_workspace` / `create_visualization`; receipt via `run_semantic_query` | **the capture** (no image API — `render_visualization` returns JSON) and **the brand** (no mark-color op on `edit_visualization`; tool default ships) | ✅ **2026-09-17** · viz `1AKQL00000MhalT4AR` · ⚡ org expires 2026-10-03 |
| **Streamlit in Snowflake** | 6th | `streamlit/` (`streamlit_app.py` + `snowflake.yml`) | `snow streamlit deploy` from the key-pair connection; receipt via `query.py snowflake` | the screenshot (no image API); brand: Altair takes the bar color + fonts in code | ✅ **2026-09-17** · `BASEBALL.SEMANTICS.KEEPING_SCORE_HR_BY_YEAR` |
| **Databricks AI/BI** | 6th | `build_lakeview.py` | dashboard JSON → `w.lakeview.create/update` + `publish` (SDK); receipt via `query.py databricks` | the screenshot; brand: `spec.mark.colors` sent, unverified until the warehouse renders | 🟡 **2026-09-17 published** · `01f1b29c59d31633894383c3d451a242` · receipt PENDING — the serverless warehouse won't start ("Cannot create the resource"), platform-side |
| **Looker Studio** | 2nd | `build_bq_view.py` | the view `wax_baseball_dbt.v_hr_by_year` + the Linking API URL (`out/looker-studio-link.txt`); receipt via BigQuery | **the report** — open the link, add one bar (Year × Home Runs), screenshot. By design | ✅ headless half 2026-09-17 · GUI half is Wax's |

## The Claude-artifact door — how to

```powershell
cd C:\Users\georg\Documents\CODING\wax_baseball_parity
py viz\build_artifact.py --build --png      # HTML + CSV (PASS on 400) + PNG via headless Edge
```

1. `query.py` runs the BigQuery SQL (`fct_plays`, `event_code = 23`, grouped by year) under
   Application Default Credentials — `gcloud auth application-default login` once.
2. `build_artifact.py` renders one self-contained page: inline SVG (no chart library), 34 bars ≤ 24 px
   thick with a 4 px rounded data-end and 2 px surface gaps, hairline grid, one direct label (the max),
   a hover tooltip, a table view, and light + dark themes from the same token file. The dataviz
   validator passed the bar color on both surfaces (`chart.json` records the run).
3. The CSV is the receipt — it must sum to 400 or the script exits 1.
4. `--png` screenshots the local file with headless Edge (`msedge --headless=new --screenshot`), 2× scale.
5. **Publishing is Claude Code's act**, not the script's: the Artifact tool takes `out/…-artifact.html`
   and returns the URL. Record the URL below. Copy the PNG to the site repo's `assets/` for the bit page.

Where headless stopped: nowhere. The only human step is saying "publish."

**Published:** https://claude.ai/artifact/WqibjHyVJwchcRNjpdRRgf (2026-09-16, version 1, private until shared) · PNG copied to `nobodybeatstheviz.github.io/assets/keeping-score-hr-by-year-artifact.png`

## The Tableau Next door — how to (measured 2026-09-17)

```powershell
claude mcp login tableau-next-pilot          # browser; the token lives ~1 day. Scratch user: `sf org open -o keeping-score-w6a` first, then the OAuth page has a session
py viz\build_tn_viz.py --schema --receipt    # dump the viz/dashboard/workspace tool schemas; run the by-year query -> CSV, PASS on 400
py viz\build_tn_viz.py --call create_workspace viz\out\tn-create-workspace.json     # once: {name, label, description} -> id
py viz\build_tn_viz.py --create viz\out\tn-create-viz-A.json                         # one create_visualization call -> {id, label, name}
py viz\build_tn_viz.py --call get_visualization viz\out\tn-get-viz.json              # read the hydrated bundle back (the git receipt)
```

What the Beta server (`analytics/tableau-next-pilot`, 132 tools on 9/17) actually took — the facts the docs don't spell out:

1. **`run_semantic_query` wants `structuredSemanticQuery`**, not `query` — a `query` key fails with *"Expect message object but got: null."* Same shape as the harness: `semantic_field` + `grouping: ROW_GROUPING` for `Game_Year`, `semantic_field` for `Home_Runs_Witnessed`.
2. **The org had no workspace.** `list_workspaces` → `[]`; `create_workspace` with a snake-case `name` returns the id (`1DyQL0000002fTh0AI` here) — the create-viz call needs both `workspaceId` and `workspaceName`.
3. **Field bindings for model-level calculated fields omit `objectName`.** `Home_Runs_Witnessed` is a calculated measure with `level: AggregateFunction` → bind `{fieldName, displayCategory: Continuous, level: AggregateFunction, function: UserAgg}`. `Game_Year` is a calculated *dimension* (`STR(YEAR(...))`, Text, `level: Row`) → the same rule holds: `{fieldName, displayCategory: Discrete}`, no `objectName`, no function. Both resolved first try (201).
4. **A text year auto-sorts by measure descending** — the server's default for one categorical dimension + one measure. `sortIntent: DimensionAscending` on the create call keeps the years in order (persists to `view.viewSpecification.sortOrders`).
5. **Where headless stops — the capture.** `render_visualization` returns the viz metadata as JSON for an MCP-app widget, not an image; `get_visualization` likewise. The PNG is a screenshot from the Tableau Next GUI (App Launcher → Tableau Next → Workspaces → Keeping Score → the viz). The org base URL comes back in the tool response `_meta`.
6. **Where headless stops — the brand.** The saved style carries an empty mark color (`style.marks.panes.color.color: ""`), but `edit_visualization`'s operation set has no mark-color op and `update_visualization` only re-saves the server-side working definition — there is no headless route to `#DB1D1D` today. The tool default ships; the number and the sort are the floor and they hold.

**Receipts in `out/`:** `keeping-score-hr-by-year-tn.csv` (34 rows = 400) · `tn-tool-schemas.json` · `tn-discovery.json` · `tn-create_workspace-response.json` · `tn-create-visualization-response.json` · `tn-get_visualization-response.json` (the hydrated bundle) · `tn-render_visualization-response.json`.

**Re-mint note:** the scratch org expires 2026-10-03; everything above replays from these files against a new org (re-apply the business preferences first, then workspace, then viz).

## The Streamlit-in-Snowflake door — how to (measured 2026-09-17)

```powershell
cd viz\streamlit
snow streamlit deploy -c wax_baseball_key --replace     # creates the stage + the STREAMLIT object; prints the app URL
cd .. ; py query.py snowflake                           # the receipt: 34 rows = 400
```

- `snowflake.yml` (definition v2) names the object `BASEBALL.SEMANTICS.KEEPING_SCORE_HR_BY_YEAR`, warehouse `WAX_WH`, stage `BASEBALL.SEMANTICS.STREAMLIT_APPS`. The CLI builds a bundle under `streamlit/output/` (gitignored).
- The app reads the **semantic view** (`SEMANTIC_VIEW(... DIMENSIONS plays.play_year METRICS plays.home_runs_witnessed)`) — the same object Cortex Analyst answers from; the two front doors share one definition.
- Brand: Altair takes the bar color, corner radius, and axis fonts in code — the ceiling, reached. The four hexes are constants in the app because Snowflake can't read the token file; that's the one deliberate second appearance, noted in the app.
- Gotcha: a multi-line `-q` argument through `snow sql` on Windows fails silently (rc≠0, empty stderr) — `query.py` collapses the SQL to one line.
- Where headless stops: the screenshot. URL: `https://app.snowflake.com/us-east-1/ylc58210/#/streamlit-apps/BASEBALL.SEMANTICS.KEEPING_SCORE_HR_BY_YEAR`.

## The Databricks AI/BI door — how to (measured 2026-09-17, receipt pending)

```powershell
py viz\build_lakeview.py --build --publish      # JSON -> lakeview.create (or update) -> publish; prints the published URL
py viz\build_lakeview.py --receipt              # SQL warehouse -> CSV, PASS on 400
```

- The serialized dashboard is plain JSON: one dataset (`queryLines` = the `mv_plays` metric-view query), one page, one `bar` widget (`spec.version: 3`, `encodings.x` categorical year, `encodings.y` quantitative measure, `frame.title`). `w.lakeview.create(dashboard=Dashboard(...))` accepted it first try; `publish(embed_credentials=True)` too. Idempotent: reruns find the dashboard by display name and `update`.
- Published: `https://dbc-9a4434eb-8c0f.cloud.databricks.com/sql/dashboardsv3/01f1b29c59d31633894383c3d451a242/published`
- **Open:** the Serverless Starter Warehouse is `STOPPED` and `warehouses.start` returns *"Cannot create the resource, please try again later"* (9/17 morning) — a platform-side start failure, so neither the receipt query nor the dashboard's render can run until it comes back. Rerun `--receipt` later; if it persists, the honest line is "authored and published headlessly; render pending the warehouse."
- Brand: `spec.mark.colors: ["#DB1D1D"]` is sent; whether Lakeview honors it is unverified until it renders. `--no-brand` retries without it.

## The Looker Studio door — how to (the GUI floor, measured 2026-09-17)

```powershell
py viz\build_bq_view.py --build --receipt       # CREATE OR REPLACE VIEW wax_baseball_dbt.v_hr_by_year; prints the Linking API URL; CSV PASS on 400
```

- Headless half: the view (the chart's exact rows, governed by the same `event_code = 23` rule) and the link — `lookerstudio.google.com/reporting/create?ds.connector=bigQuery&ds.type=TABLE&ds.projectId=…&ds.datasetId=wax_baseball_dbt&ds.tableId=v_hr_by_year&r.reportName=…`. Looker Studio has no authoring API; the Linking API opens a **new report with the view attached as its data source**.
- GUI half (Wax): open the link → Add a chart → bar → Dimension `yr`, Metric `hr` → screenshot. That's where headless stops, and the README says so — the reader being cut over to Looker Studio gets the honest boundary.
- Looker proper (the enterprise product) has a full API but no instance here; out of scope.

## Adding a door

Write `build_<door>.py` with the same three verbs (`--build`, `--publish` where the tool has an API,
`--receipt`), read `spec/` + the tokens, get rows from `query.hr_by_year(engine)`, emit a CSV that sums
to 400, and add the row above with where headless stopped. Never patch the output in the GUI — rerun.
