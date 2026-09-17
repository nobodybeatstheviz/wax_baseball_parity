"""build_tn_viz.py -- Build 2.5, the Tableau Next door: the same G2 bar (400 home runs witnessed, by year)
created HEADLESSLY on Tableau Next through the Salesforce-hosted Beta MCP server `tableau-next-pilot`.

Source:        viz/spec/hr_by_year.json · the Keeping_Score semantic model in scratch org keeping-score-w6a
               (expires 2026-10-03) · the NBTV chart tokens.
Analysis:      this script, over scripts/_hosted_mcp.py (reuses Claude Code's OAuth; never refreshes).
Presentation:  out/tn-tool-schemas.json (what the Beta server says the viz tools take) ·
               out/keeping-score-hr-by-year-tn.csv (the receipt, via run_semantic_query) ·
               out/tn-create-visualization-response.json (what the tool gave back) · a PNG when a capture path exists.

    py viz/build_tn_viz.py --schema                 # tools/list -> dump the viz/workspace/dashboard tool schemas
    py viz/build_tn_viz.py --receipt                # run_semantic_query: Game_Year x Home_Runs_Witnessed -> CSV, PASS on 400
    py viz/build_tn_viz.py --create payload.json    # one create_visualization call with that JSON as arguments
    py viz/build_tn_viz.py --call <tool> args.json  # any other Beta tool, same plumbing (read-back, edit, delete)

Auth: `claude mcp login tableau-next-pilot` in a terminal first (the token lives ~1 day). On 401 do it again.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
from _hosted_mcp import HostedMcp, semantic_query_rows  # noqa: E402

OUT = HERE / "out"
SPEC = json.loads((HERE / "spec" / "hr_by_year.json").read_text(encoding="utf-8"))
SERVER = "tableau-next-pilot"
MODEL = "Keeping_Score"
KEYWORDS = ("visual", "dashboard", "workspace", "semantic_model", "semantic_query", "metric")


def dump_schemas(mcp: HostedMcp) -> None:
    tools = mcp.list_tools()
    picked = [t for t in tools if any(k in t["name"] for k in KEYWORDS)]
    OUT.mkdir(exist_ok=True)
    out = OUT / "tn-tool-schemas.json"
    out.write_text(json.dumps({"server": SERVER, "tool_count": len(tools),
                               "tools": {t["name"]: t for t in picked}}, indent=2), encoding="utf-8")
    print(f"  {len(tools)} tools on {SERVER}; {len(picked)} matched {KEYWORDS} -> {out.name}")
    for t in picked:
        req = (t.get("inputSchema") or {}).get("required", [])
        props = list(((t.get("inputSchema") or {}).get("properties") or {}).keys())
        print(f"  - {t['name']}: required={req} props={props[:12]}{' …' if len(props) > 12 else ''}")


def receipt(mcp: HostedMcp) -> bool:
    query = {"fields": [
        {"expression": {"semantic_field": {"name": "Game_Year"}}, "alias": "yr", "grouping": "ROW_GROUPING"},
        {"expression": {"semantic_field": {"name": "Home_Runs_Witnessed"}}, "alias": "hr"},
    ]}
    res = mcp.call("run_semantic_query", {"semanticModelApiName": MODEL, "source": "wax_baseball_parity",
                                          "structuredSemanticQuery": query})
    rows = sorted((int(str(y)[:4]), int(float(h))) for y, h in semantic_query_rows(res))
    OUT.mkdir(exist_ok=True)
    csv = OUT / "keeping-score-hr-by-year-tn.csv"
    csv.write_text("Year,Home Runs\n" + "".join(f"{y},{h}\n" for y, h in rows), encoding="utf-8")
    total, want = sum(h for _, h in rows), SPEC["golden"]["value"]
    print(f"  {SPEC['golden']['label']}: {total} (want {want}) {'PASS' if total == want else 'FAIL'} -- {len(rows)} rows -> {csv.name}")
    return total == want


def call(mcp: HostedMcp, tool: str, args_path: str, out_name: str) -> None:
    args = json.loads(pathlib.Path(args_path).read_text(encoding="utf-8"))
    try:
        res = mcp.call(tool, args)
        body = res["json"] if res.get("json") is not None else res["text"]
    except RuntimeError as exc:                    # keep the server's own words as the receipt
        body = {"error": str(exc)}
    OUT.mkdir(exist_ok=True)
    out = OUT / out_name
    out.write_text(json.dumps({"tool": tool, "arguments": args, "response": body}, indent=2, default=str), encoding="utf-8")
    print(f"  {tool} -> {out.name}")
    print(json.dumps(body, indent=2, default=str)[:2500])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", action="store_true")
    ap.add_argument("--receipt", action="store_true")
    ap.add_argument("--create", metavar="PAYLOAD_JSON")
    ap.add_argument("--call", nargs=2, metavar=("TOOL", "ARGS_JSON"))
    a = ap.parse_args()
    if not (a.schema or a.receipt or a.create or a.call):
        ap.print_help()
        return
    ok = True
    with HostedMcp(SERVER) as mcp:
        if a.schema:
            dump_schemas(mcp)
        if a.receipt:
            ok = receipt(mcp) and ok
        if a.create:
            call(mcp, "create_visualization", a.create, "tn-create-visualization-response.json")
        if a.call:
            call(mcp, a.call[0], a.call[1], f"tn-{a.call[0]}-response.json")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
