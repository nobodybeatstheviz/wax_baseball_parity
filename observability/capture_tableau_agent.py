#!/usr/bin/env python3
"""
Tableau Agent (Concierge) capture — the Tableau Next cell of the O7 matrix.

The surface is the Salesforce Hosted MCP server `analytics/tableau-next` and its
`analyze_data` tool: "when you use Tableau Next MCP, you're using Concierge through
a different frontend interface" (the docs' words). Every answer carries
`troubleshootingInfo` with the literal structured semantic query the agent ran and
a platform `traceId` — the first Tableau surface in this build whose reasoning
artifact is retrievable by API rather than read off a panel.

Auth reuses Claude Code's OAuth for the server (scripts/_hosted_mcp.py); the call
is direct MCP-over-HTTP, wall-clock-timed at the client (the response embeds no
per-step timing or tokens of its own — same gap as the Claude SDK and BigQuery CA).

    py observability/capture_tableau_agent.py --trace-out traces/tableau_agent/<date>-g2.json
    py observability/capture_tableau_agent.py --question "How many games have I attended?" --trace-out ...
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
from _hosted_mcp import HostedMcp  # noqa: E402

DEFAULT_QUESTION = "How many home runs have I witnessed in person?"


def _unescape_query(q: str | None):
    """troubleshootingInfo.query arrives HTML-entity-escaped (&quot;…); return it parsed."""
    if not q:
        return None
    try:
        return json.loads(html.unescape(q))
    except json.JSONDecodeError:
        return html.unescape(q)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--server", default="tableau-next")
    parser.add_argument("--model", default="Keeping_Score")
    parser.add_argument("--trace-out", required=True)
    args = parser.parse_args()

    print(f"=== Tableau Agent (Concierge) via hosted MCP `{args.server}` · SDM {args.model} ===")
    print(f"Q: {args.question}\n")

    error_text = None
    result = None
    t_connect = time.time()
    with HostedMcp(args.server) as mcp:
        connect_ms = round((time.time() - t_connect) * 1000)
        t0 = time.time()
        try:
            result = mcp.call("analyze_data", {
                "utterance": args.question,
                "target_entity_type": "sdm",
                "target_entity_name_or_id": args.model,
            })
        except Exception as exc:  # noqa: BLE001
            error_text = str(exc)
            print(f"=== ENDED WITH ERROR: {exc} ===")
        wall_clock_ms = round((time.time() - t0) * 1000)

    payload = (result or {}).get("json") or {}
    ti = payload.get("troubleshootingInfo") or {}
    answer = html.unescape(payload.get("answer") or "")
    query = _unescape_query(ti.get("query"))
    viz = payload.get("vizMetadata")
    if isinstance(viz, str) and viz:
        try:
            viz = json.loads(html.unescape(viz))
        except json.JSONDecodeError:
            viz = html.unescape(viz)

    print(f"answer: {answer[:300]}")
    print(f"traceId: {ti.get('traceId')}   sdm: {ti.get('sdmApiNames')}")
    print(f"query: {json.dumps(query)[:300] if query else '— (no query ran)'}")
    print(f"viz spec: {'yes' if viz else 'no'}")
    print(f"\n=== DONE · session {connect_ms} ms · turn {wall_clock_ms} ms ===")

    trace = {
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "surface": "tableau_agent",
        "server": args.server,
        "model": args.model,
        "question": args.question,
        "connect_ms": connect_ms,
        "wall_clock_ms": wall_clock_ms,
        "answer": answer,
        "trace_id": ti.get("traceId"),
        "sdm_api_names": ti.get("sdmApiNames"),
        "query": query,
        "ir_spec": ti.get("irSpec"),
        "viz_metadata": viz or None,
        "raw": (result or {}).get("raw"),
        "error": error_text,
    }
    out_path = pathlib.Path(args.trace_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")
    print(f"[trace] wrote {out_path}")


if __name__ == "__main__":
    main()
