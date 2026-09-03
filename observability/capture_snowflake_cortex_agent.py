#!/usr/bin/env python3
"""
Snowflake Cortex Agent capture — the O5 leg of the O7 trio, and the one cell with
TWO sources to reconcile.

The agent object is pure SQL (wax_baseball_snowflake/sql/30_cortex_agent_keeping_score.sql)
— no UI step, unlike Databricks Genie. This script:

  1. POSTs to the agent's :run endpoint with Accept: text/event-stream and records
     every server-sent event at receipt (wall-clock-stamped — the stream carries
     no timestamps of its own, same gap as O2/O3/O4), keeping the final `response`
     event whose metadata.usage.tokens_consumed[] is the only token accounting.
  2. Waits, then queries SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS for the spans
     Snowflake wrote for this run on its own (scope snow.cortex.agent), and stores
     them beside the stream — so the extractor can say whether the platform's
     event table and the client-observed stream agree on what happened.

Auth: key-pair JWT minted by `snow connection generate-jwt -c wax_baseball_key`
(MFA is enforced on the account; the password connection is dead). The token is
held in memory only.

    py observability/capture_snowflake_cortex_agent.py --trace-out traces/snowflake_cortex/<date>-g2.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import subprocess
import time
from typing import Any

import requests

ACCOUNT_HOST = "OSWNWTM-YLC58210.snowflakecomputing.com"
CONNECTION = "wax_baseball_key"
DEFAULT_AGENT = ("BASEBALL", "SEMANTICS", "KEEPING_SCORE_AGENT")
DEFAULT_QUESTION = "How many home runs have I witnessed in person?"
EVENT_TABLE = "SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS"


def _jwt() -> str:
    out = subprocess.run(
        ["snow", "connection", "generate-jwt", "-c", CONNECTION],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    # the CLI prints warnings first; the token is the last non-empty line
    return [ln for ln in out.stdout.splitlines() if ln.strip()][-1].strip()


def _snow_sql_json(sql: str) -> list[dict[str, Any]]:
    out = subprocess.run(
        ["snow", "sql", "-c", CONNECTION, "--format", "json", "-q", sql],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:400])
    return json.loads(out.stdout)


def _parse_sse(resp: requests.Response, t0: float):
    """Yield (at_ms, event_name, data_dict) for each SSE event as it arrives."""
    event_name, data_lines = None, []
    for raw in resp.iter_lines(decode_unicode=True):
        if raw is None:
            continue
        line = raw.strip("\r")
        if line == "":
            if data_lines:
                payload = "\n".join(data_lines)
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    data = {"_raw": payload}
                yield round((time.time() - t0) * 1000), event_name, data
            event_name, data_lines = None, []
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--database", default=DEFAULT_AGENT[0])
    parser.add_argument("--schema", default=DEFAULT_AGENT[1])
    parser.add_argument("--agent", default=DEFAULT_AGENT[2])
    parser.add_argument("--trace-out", required=True)
    parser.add_argument("--event-table-wait-s", type=int, default=20,
                        help="seconds to wait before querying the event table (ingest lag)")
    args = parser.parse_args()

    url = (f"https://{ACCOUNT_HOST}/api/v2/databases/{args.database}/schemas/{args.schema}"
           f"/agents/{args.agent}:run")
    headers = {
        "Authorization": f"Bearer {_jwt()}",
        "X-Snowflake-Authorization-Token-Type": "KEYPAIR_JWT",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    body = {"messages": [{"role": "user", "content": [{"type": "text", "text": args.question}]}]}

    print(f"=== Snowflake Cortex Agent · {args.database}.{args.schema}.{args.agent} ===")
    print(f"Q: {args.question}\n")

    t0 = time.time()
    events: list[dict[str, Any]] = []
    final: dict[str, Any] | None = None
    error_text: str | None = None
    http_status = None
    request_id = None
    try:
        with requests.post(url, headers=headers, json=body, stream=True, timeout=300) as resp:
            http_status = resp.status_code
            request_id = resp.headers.get("X-Snowflake-Request-Id") or resp.headers.get("x-snowflake-request-id")
            if resp.status_code != 200:
                error_text = f"HTTP {resp.status_code}: {resp.text[:800]}"
                print(error_text)
            else:
                for at_ms, name, data in _parse_sse(resp, t0):
                    events.append({"at_ms": at_ms, "event": name, "data": data})
                    if name == "response":
                        final = data
                    if name in ("response.thinking", "response.text"):
                        print(f"[{at_ms}ms] {name}: {str(data.get('text', ''))[:220]}")
                    elif name == "response.tool_use":
                        print(f"[{at_ms}ms] tool_use {data.get('name')}: {json.dumps(data.get('input'))[:220]}")
                    elif name == "response.tool_result":
                        print(f"[{at_ms}ms] tool_result {data.get('name')} status={data.get('status')}")
                    elif name in ("response.status", "metadata", "error"):
                        print(f"[{at_ms}ms] {name}: {json.dumps(data)[:220]}")
    except Exception as exc:  # noqa: BLE001
        error_text = str(exc)
        print(f"\n=== ENDED WITH ERROR: {exc} ===")

    wall_clock_ms = round((time.time() - t0) * 1000)
    print(f"\n=== DONE · {len(events)} event(s) · {wall_clock_ms} ms · request_id={request_id} ===")
    if final:
        usage = (final.get("metadata") or {}).get("usage")
        print(f"[usage] {json.dumps(usage)[:400]}")

    # The second source: what Snowflake wrote to the event table on its own.
    event_rows: list[dict[str, Any]] = []
    event_table_error: str | None = None
    if http_status == 200:
        print(f"\n[event table] waiting {args.event_table_wait_s}s for ingest…")
        time.sleep(args.event_table_wait_s)
        try:
            started = datetime.datetime.fromtimestamp(t0, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            sql = (
                f"SELECT TIMESTAMP, START_TIMESTAMP, TRACE, SCOPE, RECORD_TYPE, RECORD, RECORD_ATTRIBUTES "
                f"FROM {EVENT_TABLE} "
                f"WHERE TIMESTAMP >= TO_TIMESTAMP_NTZ('{started}') - INTERVAL '2 minutes' "
                f"ORDER BY START_TIMESTAMP"
            )
            event_rows = _snow_sql_json(sql)
            print(f"[event table] {len(event_rows)} row(s) since run start")
            for r in event_rows:
                rec = r.get("RECORD")
                rec = json.loads(rec) if isinstance(rec, str) else (rec or {})
                print(f"  {r.get('RECORD_TYPE')} {rec.get('name')} {r.get('START_TIMESTAMP')} → {r.get('TIMESTAMP')}")
        except Exception as exc:  # noqa: BLE001
            event_table_error = str(exc)
            print(f"[event table] query failed: {exc}")

    trace = {
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "surface": "snowflake_cortex_agent",
        "agent": ".".join((args.database, args.schema, args.agent)),
        "question": args.question,
        "http_status": http_status,
        "request_id": request_id,
        "wall_clock_ms": wall_clock_ms,
        "events": events,
        "final": final,
        "event_table": {"table": EVENT_TABLE, "rows": event_rows, "error": event_table_error},
        "error": error_text,
    }
    out_path = pathlib.Path(args.trace_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")
    print(f"\n[trace] wrote {out_path}")


if __name__ == "__main__":
    main()
