#!/usr/bin/env python3
"""
The Q5/O6 companion — passive Claude Code transcript sweep (phase 2, O6).

The *local* half of O2: O2 captures one live SDK run on demand; this sweeps every
JSONL transcript Claude Code has already written under ~/.claude/projects/ (the
Trio pattern's Source is Anthropic's own log files, never touched, only read) and
lands one row per tool call — timestamp, session, project, server, tool, success —
into a small BigQuery table. Makes MCP usage queryable *by the same BigQuery MCP
it observes*.

Passive by design (Wax's ruling, 2026-09-02): no hook interception — the hookify
exit-49 postmortem showed hook dispatch failing silently on this machine, and a
passive reader can't break a live tool call. Honest limit: this sees Claude-side
surfaces only. Agentforce/Tableau Next calls are covered by their own platform's
native observability (the ADLC observe lane) — a second front door, not a gap in
this one.

⚠️ Anthropic documents the JSONL format as internal and unstable. Every field
access below is defensive (.get() chains, never an index or an assumed key) so a
future format change degrades the row count, not the run.

    py observability/sweep_claude_transcripts.py               # sweep + load + regenerate reader
    py observability/sweep_claude_transcripts.py --dry-run      # sweep + print counts, no BigQuery write
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
from typing import Any

import pandas as pd
from google.cloud import bigquery

BQ_PROJECT = "augmented-world-262319"
BQ_DATASET = "claude_observability"
BQ_TABLE = "tool_calls"
TRANSCRIPTS_ROOT = pathlib.Path.home() / ".claude" / "projects"
READER_PATH = pathlib.Path(r"C:\Users\georg\wax-system\wax-baseball\claude-code-observability-reader.md")


def _project_name(jsonl_path: pathlib.Path) -> str:
    # the project dir name is the cwd with path separators mangled to hyphens.
    # a subagent transcript nests one level deeper: <project>/<sessionId>/subagents/<file>.jsonl
    d = jsonl_path.parent
    if d.name == "subagents":
        return d.parent.parent.name
    return d.name


def sweep_file(path: pathlib.Path) -> list[dict[str, Any]]:
    """One JSONL transcript -> tool-call rows. Two passes: build a tool_use_id ->
    is_error map from every 'user' record's tool_result blocks, then walk every
    'assistant' record's tool_use blocks and join."""
    results: dict[str, bool] = {}
    tool_uses: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        rtype = rec.get("type")
        if rtype == "user":
            content = (rec.get("message") or {}).get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tid = block.get("tool_use_id")
                        if tid:
                            results[tid] = bool(block.get("is_error", False))
        elif rtype == "assistant":
            msg = rec.get("message") or {}
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_uses.append({
                        "tool_use_id": block.get("id"),
                        "name": block.get("name", ""),
                        "timestamp": rec.get("timestamp"),
                        "session_id": rec.get("sessionId"),
                        "model": msg.get("model"),
                    })

    project = _project_name(path)
    rows = []
    for tu in tool_uses:
        name = tu["name"] or ""
        if name.startswith("mcp__"):
            parts = name.split("__", 2)
            server = parts[1] if len(parts) > 1 else "mcp_unknown"
            tool = parts[2] if len(parts) > 2 else name
        else:
            server = "claude_code_builtin"
            tool = name
        is_error = results.get(tu["tool_use_id"])
        rows.append({
            "timestamp": tu["timestamp"],
            "session_id": tu["session_id"],
            "project": project,
            "server": server,
            "tool": tool,
            "success": (None if is_error is None else not is_error),
            "model": tu["model"],
            "source_file": str(path.relative_to(TRANSCRIPTS_ROOT)),
        })
    return rows


def sweep_all() -> pd.DataFrame:
    files = sorted(TRANSCRIPTS_ROOT.rglob("*.jsonl"))
    all_rows: list[dict[str, Any]] = []
    for f in files:
        all_rows.extend(sweep_file(f))
    df = pd.DataFrame(all_rows)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    return df


def load_to_bigquery(df: pd.DataFrame) -> None:
    client = bigquery.Client(project=BQ_PROJECT)
    client.create_dataset(bigquery.Dataset(f"{BQ_PROJECT}.{BQ_DATASET}"), exists_ok=True)
    table_id = f"{BQ_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"
    job = client.load_table_from_dataframe(
        df, table_id,
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
    )
    job.result()
    print(f"loaded {len(df)} rows -> {table_id}")


def which_agent_which_tool_this_month(client: bigquery.Client) -> pd.DataFrame:
    sql = f"""
        SELECT project, server, tool, COUNT(*) AS calls,
               COUNTIF(success = FALSE) AS failures
        FROM `{BQ_PROJECT}.{BQ_DATASET}.{BQ_TABLE}`
        WHERE timestamp >= TIMESTAMP_TRUNC(CURRENT_TIMESTAMP(), MONTH)
        GROUP BY project, server, tool
        ORDER BY calls DESC
        LIMIT 20
    """
    return client.query(sql).to_dataframe()


def render_reader(df: pd.DataFrame, top_month: pd.DataFrame) -> str:
    stamp = datetime.date.today().isoformat()
    n = len(df)
    n_sessions = df["session_id"].nunique() if n else 0
    n_files = df["source_file"].nunique() if n else 0
    date_min = df["timestamp"].min() if n else None
    date_max = df["timestamp"].max() if n else None
    by_server = df.groupby("server").size().sort_values(ascending=False) if n else pd.Series(dtype=int)
    by_tool = df.groupby("tool").size().sort_values(ascending=False).head(15) if n else pd.Series(dtype=int)
    fail_rate = (df["success"] == False).sum() / max((df["success"].notna()).sum(), 1) if n else 0
    known = (df["success"].notna()).sum() if n else 0

    lines = [
        "# Claude Code observability reader — the Q5/O6 companion",
        "",
        "<!-- Generated - do not hand-edit. Rebuild: py observability/sweep_claude_transcripts.py",
        "     in CODING/wax_baseball_parity. Source: every ~/.claude/projects/**/*.jsonl transcript",
        "     Claude Code has already written on this machine, swept passively (no hooks). -->",
        "",
        f"*Generated {stamp}.*",
        "",
        "⚠️ **Honest limit:** this sees Claude-side surfaces only — every tool call any Claude Code "
        "session on this machine made, across every project. Agentforce and Tableau Next calls are "
        "covered by their own platform's native observability (the ADLC observe lane), not this table — "
        "two front doors, on purpose, not a gap here.",
        "",
        "⚠️ Anthropic documents the JSONL transcript format as *internal and unstable*. Every field read "
        "is defensive; a future format change shows up as a lower row count, not a crash.",
        "",
        "## Corpus",
        "",
        f"**{n:,} tool calls** across **{n_sessions:,} sessions** in **{n_files:,} transcript files** "
        f"({date_min} → {date_max}).",
        "",
        f"**Success rate** (where known — {known:,}/{n:,} calls carry a matched result): "
        f"{100 * (1 - fail_rate):.1f}% success.",
        "",
        "## By server",
        "",
        "| Server | Calls |",
        "|---|---|",
    ]
    for server, count in by_server.items():
        lines.append(f"| `{server}` | {count:,} |")
    lines += [
        "",
        "## Top 15 tools",
        "",
        "| Tool | Calls |",
        "|---|---|",
    ]
    for tool, count in by_tool.items():
        lines.append(f"| `{tool}` | {count:,} |")
    lines += [
        "",
        "## \"Which agent called which tool this month\" — the Q6 acceptance query, live",
        "",
        "```sql",
        f"SELECT project, server, tool, COUNT(*) AS calls, COUNTIF(success = FALSE) AS failures",
        f"FROM `{BQ_PROJECT}.{BQ_DATASET}.{BQ_TABLE}`",
        "WHERE timestamp >= TIMESTAMP_TRUNC(CURRENT_TIMESTAMP(), MONTH)",
        "GROUP BY project, server, tool ORDER BY calls DESC LIMIT 20",
        "```",
        "",
        "| Project | Server | Tool | Calls | Failures |",
        "|---|---|---|---|---|",
    ]
    for _, row in top_month.iterrows():
        lines.append(f"| `{row['project']}` | `{row['server']}` | `{row['tool']}` | {row['calls']:,} | {row['failures']:,} |")
    lines += [
        "",
        "---",
        f"*Table: `{BQ_PROJECT}.{BQ_DATASET}.{BQ_TABLE}` · Source: `~/.claude/projects/` · "
        "sweep: `CODING/wax_baseball_parity/observability/sweep_claude_transcripts.py` · "
        "runs at `/sync-check` close.*",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="sweep and print counts; skip BigQuery + reader")
    args = parser.parse_args()

    print(f"sweeping {TRANSCRIPTS_ROOT} ...")
    df = sweep_all()
    print(f"{len(df)} tool-call rows from {df['source_file'].nunique() if len(df) else 0} files")

    if args.dry_run:
        if len(df):
            print(df.groupby("server").size().sort_values(ascending=False).to_string())
        return

    load_to_bigquery(df)
    client = bigquery.Client(project=BQ_PROJECT)
    top_month = which_agent_which_tool_this_month(client)
    READER_PATH.write_text(render_reader(df, top_month), encoding="utf-8")
    print(f"wrote {READER_PATH}")


if __name__ == "__main__":
    main()
