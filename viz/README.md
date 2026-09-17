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
| Tableau Cloud | 1st | `../../wax_baseball_w5_datasource/build_workbook.py` | publish + PNG/CSV receipt via the Tableau MCP | nowhere | ✅ 9/10 (unstyled; style block pending) |
| **Claude artifact** | 8th | `build_artifact.py` | the HTML + CSV + PNG; the Artifact tool publishes | nowhere | ✅ **2026-09-16** |
| **Tableau Next** | 3rd | `build_tn_viz.py` | workspace + viz created through the Beta MCP's `create_workspace` / `create_visualization`; receipt via `run_semantic_query` | **the capture** (no image API — `render_visualization` returns JSON) and **the brand** (no mark-color op on `edit_visualization`; tool default ships) | ✅ **2026-09-17** · viz `1AKQL00000MhalT4AR` · ⚡ org expires 2026-10-03 |
| Streamlit in Snowflake | 6th | `streamlit/` (planned) | `snow streamlit deploy` | the screenshot | ⬜ |
| Databricks AI/BI | 6th | `build_lakeview.py` (planned) | `w.lakeview.create` + publish | the screenshot; format unmeasured | ⬜ |
| Looker Studio | 2nd | `build_bq_view.py` (planned) | the BigQuery view + a Linking API URL | the report itself (GUI) | ⬜ |

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

## Adding a door

Write `build_<door>.py` with the same three verbs (`--build`, `--publish` where the tool has an API,
`--receipt`), read `spec/` + the tokens, get rows from `query.hr_by_year(engine)`, emit a CSV that sums
to 400, and add the row above with where headless stopped. Never patch the output in the GUI — rerun.
