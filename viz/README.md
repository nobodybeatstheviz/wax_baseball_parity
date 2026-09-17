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
| Tableau Next | 3rd | `build_tn_viz.py` (planned) | `create_visualization` on the Beta MCP | capture — TBD from the tool's schema | ⬜ ⚡ org expires 2026-10-03 |
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

## Adding a door

Write `build_<door>.py` with the same three verbs (`--build`, `--publish` where the tool has an API,
`--receipt`), read `spec/` + the tokens, get rows from `query.hr_by_year(engine)`, emit a CSV that sums
to 400, and add the row above with where headless stopped. Never patch the output in the GUI — rerun.
