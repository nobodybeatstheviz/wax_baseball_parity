"""build_artifact.py -- Build 2.5, the Claude-artifact door: the same G2 bar (400 home runs witnessed,
by year) as one self-contained HTML page, generated from the spec + the NBTV chart tokens + the engine query.

Source:        viz/spec/hr_by_year.json (the chart) · ~/.claude/skills/nbtv-design/tokens/chart.json (the
               brand) · the BigQuery mart via query.py (the rows).
Analysis:      this script. Inline SVG, no library: 34 bars, <=24px thick, 4px rounded data-end, 2px gap,
               hairline grid, one direct label, hover tooltip, a table view, light + dark from the same tokens.
Presentation:  out/keeping-score-hr-by-year-artifact.html (the page the Artifact tool publishes) ·
               out/…-artifact.csv (the receipt; sums to 400) · out/…-artifact.png (headless Edge screenshot).

    py viz/build_artifact.py --build              # write the HTML + CSV, check the golden number
    py viz/build_artifact.py --build --png        # …and screenshot it with headless Edge (or Chrome)
    py viz/build_artifact.py --engine snowflake   # any engine query.py knows

Publishing is the Artifact tool's act (Claude Code), not this script's -- see README.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from query import hr_by_year  # noqa: E402

OUT = HERE / "out"
SPEC = HERE / "spec" / "hr_by_year.json"
TOKENS = pathlib.Path(os.environ.get("NBTV_CHART_TOKENS",
                                     pathlib.Path.home() / ".claude" / "skills" / "nbtv-design" / "tokens" / "chart.json"))
DOOR = "claude_artifact"
STEM = "keeping-score-hr-by-year-artifact"
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe"]

# ---------------------------------------------------------------- chart geometry
W, H = 880, 440
PAD = {"l": 44, "r": 16, "t": 16, "b": 40}


def _bars_svg(rows: list[tuple[int, int]], t: dict) -> str:
    n = len(rows)
    max_hr = max(h for _, h in rows)
    top = ((max_hr // 10) + 1) * 10                      # clean ceiling: 44 -> 50
    plot_w, plot_h = W - PAD["l"] - PAD["r"], H - PAD["t"] - PAD["b"]
    slot = plot_w / n
    bw = min(t["mark"]["bar_max_px"], slot - t["mark"]["bar_gap_px"])
    r = t["mark"]["bar_radius_px"]
    x0, y0 = PAD["l"], PAD["t"] + plot_h                # baseline
    sy = plot_h / top

    g = []
    for v in range(0, top + 1, 10):                       # hairline grid + y ticks
        y = y0 - v * sy
        g.append(f'<line class="grid" x1="{x0}" x2="{x0 + plot_w}" y1="{y:.1f}" y2="{y:.1f}"/>')
        g.append(f'<text class="tick" x="{x0 - 8}" y="{y + 4:.1f}" text-anchor="end">{v}</text>')

    first, last = rows[0][0], rows[-1][0]
    labeled = {yr for yr, _ in rows if yr % 5 == 0} | {last}
    if all(abs(rows[i][0] - first) > 1 for i in range(1, min(3, n)) if rows[i][0] in labeled):
        labeled.add(first)                               # first year only if no label sits next to it
    for i, (yr, hr) in enumerate(rows):
        cx = x0 + slot * (i + 0.5)
        bx = cx - bw / 2
        hgt = hr * sy
        if hr > 0:                                       # 4px rounded data-end, square baseline
            rr = min(r, hgt / 2)
            d = (f"M{bx:.1f},{y0} v{-(hgt - rr):.1f} q0,{-rr} {rr},{-rr} h{bw - 2 * rr:.1f} "
                 f"q{rr},0 {rr},{rr} v{hgt - rr:.1f} z")
            g.append(f'<path class="bar" d="{d}" data-yr="{yr}" data-hr="{hr}"><title>{yr}: {hr} home runs</title></path>')
        # hit target wider than the mark, full plot height
        g.append(f'<rect class="hit" x="{x0 + slot * i:.1f}" y="{PAD["t"]}" width="{slot:.1f}" height="{plot_h}" '
                 f'data-yr="{yr}" data-hr="{hr}"/>')
        if yr in labeled:
            g.append(f'<text class="tick" x="{cx:.1f}" y="{y0 + 18}" text-anchor="middle">{yr}</text>')
        if hr == max_hr:                                 # the one direct label
            g.append(f'<text class="label" x="{cx:.1f}" y="{y0 - hgt - 6:.1f}" text-anchor="middle">{hr}</text>')
    g.append(f'<line class="axis" x1="{x0}" x2="{x0 + plot_w}" y1="{y0}" y2="{y0}"/>')
    return "\n".join(g)


def render_html(rows: list[tuple[int, int]], spec: dict, t: dict, engine: str) -> str:
    total = sum(h for _, h in rows)
    door = spec["doors"][DOOR]["door"]
    subtitle = spec["subtitle_pattern"].format(door=door)
    table = "\n".join(f"<tr><td>{y}</td><td>{h}</td></tr>" for y, h in rows)
    today = dt.date.today().isoformat()
    L, D, F = t["light"], t["dark"], t["font"]
    return f"""<title>Home Runs Witnessed</title>
<script>(function(){{var m=/theme=(light|dark)/.exec(location.search);if(m)document.documentElement.dataset.theme=m[1];}})();</script>
<link rel="stylesheet" href="{F['google_fonts_css']}">
<style>
:root {{ color-scheme: light;
  --surface:{L['surface']}; --bar:{L['bar']}; --ink:{L['ink']}; --muted:{L['muted']}; --grid:{L['grid']}; --card:{L['card']}; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ color-scheme: dark;
  --surface:{D['surface']}; --bar:{D['bar']}; --ink:{D['ink']}; --muted:{D['muted']}; --grid:{D['grid']}; --card:{D['card']}; }} }}
:root[data-theme="dark"] {{ color-scheme: dark;
  --surface:{D['surface']}; --bar:{D['bar']}; --ink:{D['ink']}; --muted:{D['muted']}; --grid:{D['grid']}; --card:{D['card']}; }}
body {{ margin:0; background:var(--surface); color:var(--ink); font-family:{F['body']}; font-size:16px; line-height:1.5; }}
.wrap {{ max-width:920px; margin:0 auto; padding-block:28px; padding-inline:16px; }}
.eyebrow {{ font-family:{F['display']}; font-size:12px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); margin:0 0 6px; }}
h1 {{ font-family:{F['display']}; font-weight:700; font-size:clamp(20px,3.2vw,28px); line-height:1.2; margin:0 0 4px; text-wrap:balance; }}
.sub {{ margin:0 0 18px; color:var(--muted); font-size:14px; }}
.sub b {{ color:var(--ink); font-weight:600; }}
figure {{ margin:0; position:relative; }}
svg {{ width:100%; height:auto; display:block; }}
.bar {{ fill:var(--bar); }}
.hit {{ fill:transparent; cursor:default; }}
.hit:hover + text, .hit:hover {{ }}
.grid {{ stroke:var(--grid); stroke-width:1; }}
.axis {{ stroke:var(--muted); stroke-width:1; }}
.tick {{ fill:var(--muted); font-family:{F['display']}; font-size:11px; font-variant-numeric:tabular-nums; }}
.label {{ fill:var(--ink); font-family:{F['display']}; font-size:12px; font-weight:700; }}
.tip {{ position:absolute; pointer-events:none; background:var(--ink); color:var(--surface); font-family:{F['display']};
  font-size:12px; padding:4px 8px; border-radius:2px; transform:translate(-50%,-130%); white-space:nowrap; visibility:hidden; }}
details {{ margin-top:18px; font-size:14px; }}
summary {{ cursor:pointer; font-family:{F['display']}; color:var(--muted); }}
table {{ border-collapse:collapse; margin-top:8px; font-variant-numeric:tabular-nums; }}
td, th {{ padding:2px 14px 2px 0; text-align:right; border-bottom:1px solid var(--grid); }}
th {{ font-family:{F['display']}; font-weight:400; color:var(--muted); font-size:12px; }}
.foot {{ margin-top:22px; padding-top:10px; border-top:1px dashed var(--grid); color:var(--muted); font-size:12px; font-family:{F['display']}; }}
.foot a {{ color:inherit; }}
@media (prefers-reduced-motion: no-preference) {{ .bar {{ transition: opacity .12s; }} }}
</style>
<div class="wrap">
  <p class="eyebrow">Keeping Score · Nobody Beats The Viz</p>
  <h1>{spec['title']}</h1>
  <p class="sub">{subtitle.replace('400', '<b>400</b>', 1)}</p>
  <figure aria-label="Bar chart: home runs witnessed by year, 1984 to 2025, 34 seasons attended, 400 in total">
    <svg viewBox="0 0 {W} {H}" role="img">
{_bars_svg(rows, t)}
    </svg>
    <div class="tip" id="tip"></div>
  </figure>
  <details>
    <summary>Table view · {len(rows)} seasons</summary>
    <table><tr><th>Year</th><th>Home runs</th></tr>{table}<tr><th>Total</th><th>{total}</th></tr></table>
  </details>
  <p class="foot">Source: <code>wax_baseball_dbt.fct_plays</code> on BigQuery, <code>event_code = 23</code> · engine <code>{engine}</code> ·
    generated {today} by <code>build_artifact.py</code> · the number is the parity harness's G2 (400 on six surfaces) ·
    <a href="https://nobodybeatstheviz.com/bits/wax-baseball/">the scorecard</a></p>
</div>
<script>
(function(){{
  var tip=document.getElementById('tip'), fig=document.querySelector('figure');
  document.querySelectorAll('.hit').forEach(function(h){{
    h.addEventListener('mousemove',function(e){{
      var r=fig.getBoundingClientRect();
      tip.textContent=h.dataset.yr+' · '+h.dataset.hr+(h.dataset.hr==='1'?' home run':' home runs');
      tip.style.left=(e.clientX-r.left)+'px'; tip.style.top=(e.clientY-r.top)+'px'; tip.style.visibility='visible';
    }});
    h.addEventListener('mouseleave',function(){{ tip.style.visibility='hidden'; }});
  }});
}})();
</script>
"""


def screenshot(html: pathlib.Path, png: pathlib.Path) -> bool:
    exe = next((b for b in BROWSERS if pathlib.Path(b).exists()), None)
    if not exe:
        print("  no Edge/Chrome found; PNG skipped")
        return False
    subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                    f"--screenshot={png}", "--window-size=920,700", html.resolve().as_uri() + "?theme=light"],
                   capture_output=True, text=True, timeout=90)
    ok = png.exists() and png.stat().st_size > 0
    print(f"  png: {png.name} ({png.stat().st_size} bytes)" if ok else "  png: screenshot failed")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--png", action="store_true")
    ap.add_argument("--engine", default="bigquery")
    a = ap.parse_args()
    if not (a.build or a.png):
        ap.print_help()
        return

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    tokens = json.loads(TOKENS.read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    html_path, csv_path, png_path = (OUT / f"{STEM}.{ext}" for ext in ("html", "csv", "png"))

    if a.build:
        rows = hr_by_year(a.engine)
        html_path.write_text(render_html(rows, spec, tokens, a.engine), encoding="utf-8")
        csv_path.write_text("Year,Home Runs\n" + "".join(f"{y},{h}\n" for y, h in rows), encoding="utf-8")
        total, want = sum(h for _, h in rows), spec["golden"]["value"]
        print(f"  wrote {html_path.name} ({html_path.stat().st_size} bytes) + {csv_path.name}")
        print(f"  {spec['golden']['label']}: {total} (want {want}) {'PASS' if total == want else 'FAIL'} -- {len(rows)} bars")
        if total != want:
            sys.exit(1)
    if a.png:
        if not screenshot(html_path, png_path):
            sys.exit(1)


if __name__ == "__main__":
    main()
