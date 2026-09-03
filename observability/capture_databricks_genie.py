#!/usr/bin/env python3
"""
Databricks Genie capture — the O4 leg of the O7 trio.

The Genie space itself had to be created once through the workspace UI (Wax,
2026-09-03, "Keeping Score" agent) — `GenieAPI.create_space`'s own docstring says
the `serialized_space` payload it needs can only be obtained by reading back an
existing space (`get_space`), so there's no documented way to author one from zero
via API. Everything downstream of a `space_id` existing IS fully scriptable, same
shape as O1-O3.

Genie's conversation API doesn't stream progress the way BigQuery's chat() or an
Agentforce trace does: `start_conversation` returns a pollable `Wait[GenieMessage]`
whose `.status` moves through a fixed ladder (SUBMITTED -> FETCHING_METADATA ->
FILTERING_CONTEXT -> ASKING_AI -> EXECUTING_QUERY -> COMPLETED). This script polls
`get_message` itself and wall-clock-timestamps every status change — the same
self-instrumentation gap as the Claude SDK (O2) and BigQuery CA (O3): none of these
platforms hand you per-step timing, only a capture script that watches and stamps
it does.

    py observability/capture_databricks_genie.py --space-id <id> --trace-out <path>
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import time
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config
from databricks.sdk.service.dashboards import MessageStatus

DEFAULT_QUESTION = "How many home runs were hit in games Wax attended?"
TERMINAL = {MessageStatus.COMPLETED, MessageStatus.FAILED, MessageStatus.CANCELLED, MessageStatus.QUERY_RESULT_EXPIRED}


def _message_to_dict(msg) -> dict[str, Any]:
    attachments = []
    for a in msg.attachments or []:
        entry: dict[str, Any] = {"attachment_id": a.attachment_id}
        if a.text:
            entry["text"] = a.text.content
        if a.query:
            entry["query"] = {
                "title": a.query.title,
                "description": a.query.description,
                "query": a.query.query,
                "statement_id": a.query.statement_id,
                "thoughts": [{"thought_type": str(t.thought_type), "content": t.content} for t in (a.query.thoughts or [])],
                "row_count": a.query.query_result_metadata.row_count if a.query.query_result_metadata else None,
            }
        attachments.append(entry)
    return {
        "message_id": msg.message_id,
        "status": str(msg.status),
        "content": msg.content,
        "created_timestamp": msg.created_timestamp,
        "last_updated_timestamp": msg.last_updated_timestamp,
        "error": str(msg.error) if msg.error else None,
        "attachments": attachments,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--space-id", required=True)
    parser.add_argument("--profile", default="wax_baseball")
    parser.add_argument("--trace-out", required=True)
    parser.add_argument("--poll-interval-ms", type=int, default=400)
    args = parser.parse_args()

    cfg = Config(profile=args.profile)
    w = WorkspaceClient(config=cfg)

    print(f"=== Databricks Genie · space {args.space_id} ===")
    print(f"Q: {args.question}\n")

    t0 = time.time()

    def _at_ms() -> int:
        return round((time.time() - t0) * 1000)

    events: list[dict[str, Any]] = []
    error_text: str | None = None
    final_msg = None
    try:
        waiter = w.genie.start_conversation(space_id=args.space_id, content=args.question)
        conversation_id = waiter.conversation_id
        message_id = waiter.message_id
        events.append({"at_ms": _at_ms(), "phase": "started", "conversation_id": conversation_id, "message_id": message_id})
        print(f"[{_at_ms()}ms] started conversation {conversation_id}, message {message_id}")

        last_status = None
        while True:
            msg = w.genie.get_message(space_id=args.space_id, conversation_id=conversation_id, message_id=message_id)
            status = str(msg.status)
            if status != last_status:
                at = _at_ms()
                events.append({"at_ms": at, "phase": "status", "status": status})
                print(f"[{at}ms] status={status}")
                last_status = status
            if msg.status in TERMINAL:
                final_msg = msg
                break
            time.sleep(args.poll_interval_ms / 1000)

        events.append({"at_ms": _at_ms(), "phase": "final_message", "message": _message_to_dict(final_msg)})
        for a in final_msg.attachments or []:
            if a.text:
                print(f"[final text] {a.text.content}")
            if a.query:
                print(f"[final query] {a.query.query}")
                for t in a.query.thoughts or []:
                    print(f"  thought({t.thought_type}): {t.content[:200]}")
    except Exception as exc:  # noqa: BLE001
        error_text = str(exc)
        print(f"\n=== ENDED WITH ERROR: {exc} ===")

    wall_clock_ms = _at_ms()
    print(f"\n=== DONE · {wall_clock_ms} ms ===")

    trace = {
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "surface": "databricks_genie",
        "space_id": args.space_id,
        "question": args.question,
        "wall_clock_ms": wall_clock_ms,
        "events": events,
        "final_message": _message_to_dict(final_msg) if final_msg else None,
        "error": error_text,
    }
    out_path = pathlib.Path(args.trace_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")
    print(f"\n[trace] wrote {out_path}")


if __name__ == "__main__":
    main()
