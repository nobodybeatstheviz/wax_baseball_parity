"""build_dashboard.py -- Build 2.5, door 7: the same G2 bar (400 home runs witnessed, by year) as a
Claude Dashboard (the claude.ai Dashboard artifact type), generated from the spec + the NBTV chart tokens
+ the engine query.

Source:        viz/spec/hr_by_year.json (the chart) · ~/.claude/skills/nbtv-design/tokens/chart.json (the
               brand) · the engine's governed object via query.py (the rows).
Analysis:      this script. It emits the three documents the Dashboard type stores -- the dataset, the page,
               the meta -- plus the CSV receipt. It never talks to claude.ai: the store writes are Claude
               Code's act (ArtifactData), the same split as build_artifact.py's "publishing is the tool's act".
Presentation:  out/dashboard/<engine>/index.html (the page, d3 v7 over the type's `dash` API) ·
               out/dashboard/<engine>/dataset.json · out/dashboard/<engine>/meta.json ·
               out/keeping-score-hr-by-year-dashboard-<engine>.csv (the receipt; sums to 400).

    py viz/build_dashboard.py --build                       # BigQuery rows -> CSV + the three documents
    py viz/build_dashboard.py --build --engine data360      # the Data 360 SDM leg (rows via --rows-json)
    py viz/build_dashboard.py --build --live bigquery:execute_sql_readonly   # emit the dataset as a LIVE query
                                                            # on a claude.ai connector instead of a fixed file

Two dataset shapes, measured against the type's reference docs (2026-10-21):
  * fixed file -- when the rows came from a tool that exists only in this session (the local BigQuery
    toolbox, the local Data 360 jar). The type says a reader's page can't call those, so the dataset is the
    CSV, `fixed: true`, and the description carries the SQL so the query is still shown.
  * live query -- when a claude.ai connector the reader also holds ran the call. `--live connector:tool`
    writes `source.kind = "query"` with the same SQL; the store write then re-runs it per reader.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from query import SQL, hr_by_year  # noqa: E402

OUT = HERE / "out"
SPEC = HERE / "spec" / "hr_by_year.json"
TOKENS = pathlib.Path(os.environ.get("NBTV_CHART_TOKENS",
                                     pathlib.Path.home() / ".claude" / "skills" / "nbtv-design" / "tokens" / "chart.json"))
DOOR = "claude_dashboards"
DATASET_ID = "hr_by_year"
STEM = "keeping-score-hr-by-year-dashboard"

# The Data 360 leg: the SDM's governed measure, by the calculated year dimension (same names as the
# Tableau Next door; resolved by label in devorg -- see README § door 7b).
SQL["data360"] = "SDM Keeping_Score · dimension Game_Year · measure Home_Runs_Witnessed (d360_sdm_query)"

ENGINE_LABEL = {"bigquery": "BigQuery (dbt mart fct_plays)", "data360": "Data 360 (Keeping_Score semantic data model, devorg)"}

# ---------------------------------------------------------------- the page
# Plain HTML inside #dash-root. No external <link>/<script> -- the type drops them -- so the brand font
# stack is declared with the type's own font as the last fallback: it renders where the reader has
# Cascadia installed, and degrades to the type's sans elsewhere. Mark color is CSS, so brand red holds.
PAGE = r"""
<style>
  .ks { font-family: var(--font-anthropic-sans); max-width: 980px; margin-inline: auto; }
  .ks-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--cds-gap-md); margin-bottom: var(--cds-gap-md); }
  .ks-title { font-family: __FONT_DISPLAY__, var(--font-anthropic-serif); font-weight: 400; font-size: var(--cds-font-size-title); margin: 0; }
  .ks-total { font-family: var(--font-anthropic-serif); font-weight: 400; font-size: 2.6rem; line-height: 1; color: __BAR__; font-variant-numeric: tabular-nums; }
  .ks-take { color: var(--color-fg-muted); font-size: var(--cds-font-size-body); margin: 0 0 var(--cds-gap-md); }
  .ks-card { background: var(--color-panel); border: 1px solid var(--color-border-line); border-radius: var(--cds-radius); padding: var(--cds-pad-lg); margin-bottom: var(--cds-gap-md); }
  .ks-card h2 { font-size: var(--cds-font-size-heading); font-weight: var(--cds-font-weight-medium); margin: 0 0 var(--cds-gap-xs); }
  .ks-note { color: var(--color-fg-muted); font-size: var(--cds-font-size-caption); margin: 0 0 var(--cds-gap-sm); }
  .ks-chart { position: relative; min-height: 360px; }
  .ks-chart svg { display: block; width: 100%; height: auto; }
  .ks-chart .bar { fill: __BAR__; }
  .ks-chart .bar.is-hover { fill-opacity: .72; }
  .ks-chart .grid line { stroke: var(--cds-chart-grid); stroke-width: 1; }
  .ks-chart .axis text { fill: var(--color-fg-muted); font-size: var(--cds-font-size-caption); font-family: var(--font-anthropic-sans); }
  .ks-chart .axis path, .ks-chart .axis line { stroke: var(--cds-chart-axis); }
  .ks-chart .direct { fill: var(--color-fg); font-size: var(--cds-font-size-caption); font-variant-numeric: tabular-nums; text-anchor: middle; }
  .ks-tip { position: absolute; pointer-events: none; background: var(--cds-surface-popover); border: 1px solid var(--cds-border); border-radius: var(--cds-radius); box-shadow: var(--cds-shadow-popover); padding: var(--cds-pad-xs) var(--cds-pad-sm); font-size: var(--cds-font-size-caption); white-space: nowrap; display: none; }
  .ks-tip .yr { color: var(--cds-text-secondary); }
  .ks-tbl { max-height: 320px; overflow: auto; }
  .ks-tbl table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; font-size: var(--cds-font-size-body); }
  .ks-tbl th { position: sticky; top: 0; background: var(--color-panel); text-align: left; font-weight: var(--cds-font-weight-medium); border-bottom: 1px solid var(--color-border-line); padding: var(--cds-pad-xs) var(--cds-pad-sm); }
  .ks-tbl td { padding: var(--cds-pad-xs) var(--cds-pad-sm); border-bottom: 1px solid var(--color-border-line); }
  .ks-tbl td.n, .ks-tbl th.n { text-align: right; }
  .ks-tbl td.n span { display: inline-block; height: .7em; background: __BAR__; vertical-align: middle; margin-left: var(--cds-gap-xs); border-radius: 2px; }
  .ks-foot { color: var(--color-fg-muted); font-size: var(--cds-font-size-caption); }
  [data-dash-source-state=empty] { color: transparent; }
  [data-dash-source-state=refreshing] { opacity: .5; transition: opacity var(--cds-dur-slow); }
</style>
<div class="ks">
  <div class="ks-head">
    <h1 class="ks-title" id="title">__TITLE__</h1>
    <div class="ks-total dash-skeleton" data-source="total" data-field="hr">—</div>
  </div>
  <p class="ks-take" id="take">__SUBTITLE__</p>
  <section class="ks-card" id="by-year">
    <h2>__QUESTION__</h2>
    <p class="ks-note">__YEARS_RULE__</p>
    <div class="ks-chart dash-skeleton" data-source="__DS__"><div class="ks-tip"></div></div>
  </section>
  <section class="ks-card" id="table">
    <h2>Every season</h2>
    <p class="ks-note">The same rows as the chart; the receipt is the total.</p>
    <div class="ks-tbl"><table data-source="__DS__" data-row-key="yr">
      <thead><tr><th data-field="yr">Year</th><th class="n" data-field="hr">Home runs</th></tr></thead>
      <tbody></tbody>
    </table></div>
  </section>
  <p class="ks-foot" id="foot">__FOOT__</p>
</div>
<script>
  const DS = '__DS__';
  const num = (v) => Number(v);
  const rowsOf = (d) => (d.status === 'ok' ? d.data : []).map((r) => ({ yr: num(r.yr), hr: num(r.hr) })).sort((a, b) => a.yr - b.yr);

  dash.calc('total', {
    inputs: [DS],
    title: 'Home runs witnessed, total',
    description: 'The sum of the by-year rows; the golden number is 400.',
    fn: (hr_by_year) => [{ hr: hr_by_year.reduce((s, r) => s + Number(r.hr), 0) }],
  });

  const chart = document.querySelector('.ks-chart');
  const tip = chart.querySelector('.ks-tip');
  const tbody = document.querySelector('.ks-tbl tbody');
  const totalEl = document.querySelector('.ks-total');
  const fmt = d3.format(',');

  function failLine(el) {
    el.replaceChildren();
    const d = document.createElement('div');
    d.style.cssText = 'display:flex;align-items:center;justify-content:center;gap:.5rem;min-height:360px;color:var(--color-fg-muted);font-size:var(--cds-font-size-caption)';
    d.innerHTML = '<span style="width:.375rem;height:.375rem;border-radius:50%;background:var(--color-bad)"></span>';
    d.append(document.createTextNode('Failed to load'));
    el.append(d, tip);
  }

  function draw(rows) {
    chart.classList.remove('dash-skeleton');
    const W = Math.max(320, chart.clientWidth), H = 360;
    const m = { t: 24, r: 12, b: 36, l: 12 };
    chart.querySelector('svg')?.remove();
    const svg = d3.select(chart).insert('svg', ':first-child').attr('viewBox', `0 0 ${W} ${H}`).attr('width', '100%');
    const y = d3.scaleLinear([0, d3.max(rows, (r) => r.hr) || 1], [H - m.b, m.t]).nice();
    // left margin from the widest tick as drawn
    const probe = svg.append('text').attr('class', 'axis').style('visibility', 'hidden');
    m.l = d3.max(y.ticks(5), (t) => { probe.text(fmt(t)); return probe.node().getComputedTextLength(); }) + 14;
    probe.remove();
    const x = d3.scaleBand(rows.map((r) => r.yr), [m.l, W - m.r]).paddingInner(__GAP_RATIO__);
    const bw = Math.min(x.bandwidth(), __BAR_MAX__);
    const bx = (yr) => x(yr) + (x.bandwidth() - bw) / 2;

    svg.append('g').attr('class', 'grid').selectAll('line').data(y.ticks(5)).join('line')
      .attr('x1', m.l).attr('x2', W - m.r).attr('y1', (t) => y(t)).attr('y2', (t) => y(t));
    svg.append('g').attr('class', 'axis').attr('transform', `translate(${m.l},0)`)
      .call(d3.axisLeft(y).ticks(5).tickSize(0).tickFormat(fmt)).attr('font-size', null).attr('font-family', null)
      .call((g) => g.select('.domain').remove());
    const first = rows[0]?.yr, last = rows[rows.length - 1]?.yr;
    const label = (yr) => yr % 5 === 0 || yr === first || yr === last;
    svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${H - m.b})`)
      .call(d3.axisBottom(x).tickSize(0).tickValues(rows.map((r) => r.yr).filter(label)))
      .attr('font-size', null).attr('font-family', null)
      .call((g) => g.select('.domain').attr('d', `M${m.l},0H${W - m.r}`));

    const bars = svg.append('g').selectAll('rect').data(rows).join('rect').attr('class', 'bar')
      .attr('x', (r) => bx(r.yr)).attr('width', bw).attr('rx', Math.min(__RADIUS__, bw / 2))
      .attr('y', (r) => y(r.hr)).attr('height', (r) => Math.max(0, y(0) - y(r.hr)));
    const top = rows.reduce((a, r) => (r.hr > a.hr ? r : a), rows[0]);
    if (top) svg.append('text').attr('class', 'direct').attr('x', bx(top.yr) + bw / 2).attr('y', y(top.hr) - 6).text(`${top.yr} · ${fmt(top.hr)}`);

    svg.on('mousemove', (ev) => {
      const [px] = d3.pointer(ev);
      const i = Math.min(rows.length - 1, Math.max(0, Math.floor((px - m.l) / x.step())));
      const r = rows[i]; if (!r) return;
      bars.classed('is-hover', (d) => d === r);
      tip.innerHTML = `<span class="yr">${r.yr}</span> &nbsp; ${fmt(r.hr)} home run${r.hr === 1 ? '' : 's'}`;
      tip.style.display = 'block';
      const box = chart.getBoundingClientRect();
      const left = Math.min(box.width - tip.offsetWidth - 4, Math.max(4, (bx(r.yr) + bw / 2) / W * box.width - tip.offsetWidth / 2));
      tip.style.left = left + 'px';
      tip.style.top = Math.max(0, y(r.hr) / H * box.height - tip.offsetHeight - 10) + 'px';
    }).on('mouseleave', () => { tip.style.display = 'none'; bars.classed('is-hover', false); });
  }

  function table(rows) {
    const max = d3.max(rows, (r) => r.hr) || 1;
    tbody.replaceChildren(...rows.map((r) => {
      const tr = document.createElement('tr');
      const a = document.createElement('td'); a.textContent = String(r.yr);
      const b = document.createElement('td'); b.className = 'n'; b.textContent = fmt(r.hr);
      const bar = document.createElement('span'); bar.style.width = (r.hr / max * 80) + 'px'; b.append(bar);
      tr.append(a, b); return tr;
    }));
  }

  dash.onData(() => {
    const d = dash.data(DS);
    const t = dash.data('total');
    if (t.status === 'ok' && t.data?.[0]) { totalEl.classList.remove('dash-skeleton'); totalEl.textContent = fmt(t.data[0].hr); }
    if (d.status === 'error' || d.status === 'connect') { failLine(chart); tbody.replaceChildren(); return; }
    if (d.status !== 'ok') return;
    const rows = rowsOf(d);
    draw(rows); table(rows);
  });
</script>
"""


def render_page(spec: dict, t: dict, engine: str) -> str:
    bar_max = t["mark"]["bar_max_px"]
    gap_ratio = round(t["mark"]["bar_gap_px"] / (bar_max + t["mark"]["bar_gap_px"]), 3)
    return (PAGE
            .replace("__FONT_DISPLAY__", t["font"]["display"])
            .replace("__BAR__", t["light"]["bar"])
            .replace("__TITLE__", spec["title"])
            .replace("__SUBTITLE__", spec["subtitle_pattern"].format(door="Claude Dashboards"))
            .replace("__QUESTION__", spec["question"])
            .replace("__YEARS_RULE__", spec["years_rule"].split(" (")[0] + ".")
            .replace("__DS__", DATASET_ID)
            .replace("__FOOT__", f"Source: {ENGINE_LABEL[engine]}. Every number on this page shows its query in Sources. "
                                 f"Brand: NBTV chart tokens, bar {t['light']['bar']}.")
            .replace("__GAP_RATIO__", str(gap_ratio))
            .replace("__BAR_MAX__", str(bar_max))
            .replace("__RADIUS__", str(t["mark"]["bar_radius_px"])))


def dataset_doc(engine: str, live: str | None, file_url: str | None, csv_name: str, now: str) -> dict:
    sql = " ".join(SQL[engine].split())
    desc_live = f"Home runs witnessed (event_code = 23) by season, from {ENGINE_LABEL[engine]}. Reads {sql}"
    if live:
        connector, tool = live.split(":", 1)
        return {"title": "Home runs by year", "description": desc_live,
                "source": {"kind": "query", "connector": connector, "tool": tool, "args": {"sql": sql}}}
    return {"title": "Home runs by year",
            "description": (f"Home runs witnessed (event_code = 23) by season, from {ENGINE_LABEL[engine]}. "
                            f"Fixed copy: the rows came from a tool that exists only in the author's Claude Code session "
                            f"(a local MCP server), which a reader's page cannot call. The query was: {sql}"),
            "source": {"kind": "file", "url": file_url or "__UPLOAD_URL__", "name": csv_name, "format": "csv"},
            "updated": {"at": now, "by": "George Weatherwax (Claude Code)"},
            "fixed": True}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--engine", default="bigquery", choices=["bigquery", "data360"])
    ap.add_argument("--rows-json", help="rows as [[year, hr], ...] when the engine isn't in query.py (data360)")
    ap.add_argument("--live", help="connector:tool -- emit a live-query dataset instead of a fixed file")
    ap.add_argument("--file-url", help="the uploaded CSV's /_blob/ url, once known")
    a = ap.parse_args()
    if not a.build:
        ap.print_help(); return

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    tokens = json.loads(TOKENS.read_text(encoding="utf-8"))
    rows = [tuple(map(int, r)) for r in json.loads(pathlib.Path(a.rows_json).read_text())] if a.rows_json else hr_by_year(a.engine)
    rows = sorted(rows)
    total = sum(h for _, h in rows)
    golden = spec["golden"]["value"]

    out_dir = OUT / "dashboard" / a.engine
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_name = f"{STEM}-{a.engine}.csv"
    (OUT / csv_name).write_text("yr,hr\n" + "".join(f"{y},{h}\n" for y, h in rows), encoding="utf-8", newline="\n")
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    (out_dir / "index.html").write_text(render_page(spec, tokens, a.engine), encoding="utf-8", newline="\n")
    (out_dir / "page.json").write_text(json.dumps({"text": render_page(spec, tokens, a.engine)}), encoding="utf-8")
    (out_dir / "dataset.json").write_text(json.dumps(dataset_doc(a.engine, a.live, a.file_url, csv_name, now), indent=2), encoding="utf-8")
    title = "Keeping Score — Home runs witnessed" + (" (Data 360)" if a.engine == "data360" else "")
    (out_dir / "meta.json").write_text(json.dumps({"title": title}), encoding="utf-8")

    status = "PASS" if total == golden else "FAIL"
    print(f"{status}: {len(rows)} rows, sum {total} (golden {golden}) -> {OUT / csv_name}")
    print(f"documents -> {out_dir}  ({'live ' + a.live if a.live else 'fixed file'})")
    sys.exit(0 if total == golden else 1)


if __name__ == "__main__":
    main()
