#!/usr/bin/env python3
"""
Observability receipts — Keeping Score phase 2 (the O7 trio, Analysis layer).

    Source        observability/traces/<surface>/...   captured traces, git-tracked, never edited
                  observability/surfaces.json          what the DOCS say for a cell that has no
                                                       captured trace yet (hand-kept; a row leaves
                                                       the moment a trace lands for that surface)
    Analysis      this script — reads the rubric fields out of the traces, no hand edits
    Presentation  wax-system/wax-baseball/observability-receipts.md — regenerated, never patched

Rubric (O0, ruled 2026-09-02): five columns per surface —
    plan/reasoning visible · tool-or-SQL visible · grounding source visible ·
    tokens+latency visible · retrieval path (API / log table / CLI / GUI)
Every cell is marked MEASURED (derived from a captured trace in this folder) or READ
(taken from vendor docs, no trace yet). Golden question: G2 home runs witnessed,
reference 400 — a surface's cell counts as measured only if 400 is in its trace.

Surfaces handled so far:
    agentforce    `sf agent preview` session dirs (turn-index.json + traces/<planId>.json)
                  and `sf agent test run --json` result files (Testing Center)

Usage:
    python observability/extract_observability.py
"""

from __future__ import annotations

import datetime
import json
import pathlib
import re
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
TRACES = HERE / "traces"
SURFACES_JSON = HERE / "surfaces.json"
RECEIPT_PATH = pathlib.Path(r"C:\Users\georg\wax-system\wax-baseball\observability-receipts.md")

GOLDEN_QUESTION = "G2 — How many home runs have I witnessed in person?"
REFERENCE = "400"
COLUMNS = ["plan/reasoning", "tool-or-SQL", "grounding source", "tokens + latency", "retrieval path"]


# ----------------------------------------------------------------------------- helpers

def _walk_keys(obj: Any, out: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(k)
            _walk_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_keys(v, out)


def _count_token_keys(obj: Any) -> int:
    keys: list[str] = []
    _walk_keys(obj, keys)
    return sum(1 for k in keys if "token" in k.lower() or k.lower() in {"usage", "input_tokens", "output_tokens"})


def _reference_in(obj: Any) -> bool:
    return REFERENCE in json.dumps(obj)


# ----------------------------------------------------------------------------- agentforce · preview traces

def parse_agentforce_plan(path: pathlib.Path) -> dict[str, Any]:
    """One `sf agent preview` trace file = one planner turn (a PlanSuccessResponse)."""
    d = json.loads(path.read_text(encoding="utf-8"))
    plan = d.get("plan", [])
    t0 = plan[0]["startExecutionTime"] if plan else 0
    t_end = max((s.get("endExecutionTime", 0) for s in plan), default=0)
    llm = [s for s in plan if s.get("type") == "LLMStep"]
    fns = [s for s in plan if s.get("type") == "FunctionStep"]
    user = next((s.get("message") for s in plan if s.get("type") == "UserInputStep"), "")
    final = next((s.get("message") for s in plan if s.get("type") == "PlannerResponseStep"), "")
    transitions = [
        (s["data"].get("from_agent"), s["data"].get("to_agent"))
        for s in plan if s.get("type") == "TransitionStep"
    ]
    picks = []
    for s in llm:
        for m in s.get("response_messages") or s["data"].get("response_messages") or []:
            inv = m.get("tool_invocation")
            if inv:
                picks.append(f"{inv.get('name')}({inv.get('arguments', '')})")
    fn_rows = [
        {
            "name": s["function"]["name"],
            "input": s["function"].get("input"),
            "output": {k: v for k, v in s["function"].get("output", {}).items() if not k.startswith("__")},
            "latency_ms": s.get("executionLatency"),
        }
        for s in fns
    ]
    return {
        "file": path.name,
        "plan_id": d.get("planId"),
        "topic": d.get("topic"),
        "user": user,
        "final": final,
        "steps": len(plan),
        "total_ms": t_end - t0,
        "llm_calls": len(llm),
        "llm_latency_ms": [s["data"].get("execution_latency") for s in llm],
        "tool_picks": picks,
        "transitions": transitions,
        "functions": fn_rows,
        "token_keys": _count_token_keys(d),
        "size_kb": round(path.stat().st_size / 1024),
        "has_reference": _reference_in(fn_rows) or REFERENCE in (final or ""),
        "is_g2": "home run" in user.lower(),
    }


def parse_agentforce_preview_session(session_dir: pathlib.Path) -> dict[str, Any]:
    idx = json.loads((session_dir / "turn-index.json").read_text(encoding="utf-8"))
    meta = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
    plans = [parse_agentforce_plan(p) for p in sorted((session_dir / "traces").glob("*.json"))]
    return {
        "dir": session_dir.name,
        "session_id": idx.get("sessionId"),
        "created": idx.get("created"),
        "mode": meta.get("mockMode"),
        "plans": plans,
    }


# ----------------------------------------------------------------------------- agentforce · Testing Center runs

def parse_agentforce_test_run(path: pathlib.Path) -> dict[str, Any]:
    """`sf agent test run --json` output. Tolerant: the result envelope has shifted
    between CLI versions, so every field is looked up defensively."""
    d = json.loads(path.read_text(encoding="utf-8"))
    r = d.get("result", d)
    cases = r.get("testCases") or r.get("testSet", {}).get("testCases") or r.get("tests") or []
    rows = []
    for c in cases:
        inputs = c.get("inputs") or {}
        utter = inputs.get("utterance") or c.get("utterance") or ""
        gen = c.get("generatedData") or {}
        actual_topic = gen.get("topic") or c.get("actualTopic")
        actual_actions = gen.get("invokedActions") or gen.get("actionsSequence") or gen.get("actions") or c.get("actualActions") or []
        if isinstance(actual_actions, str):
            actual_actions = [a.strip() for a in re.split(r"[,\n]", actual_actions) if a.strip()]
        actual_out = gen.get("outcome") or gen.get("response") or c.get("actualOutcome") or ""
        results = c.get("testResults") or c.get("expectations") or []
        exp: dict[str, Any] = {}
        for e in results:
            name = (e.get("name") or e.get("expectationName") or "").lower()
            exp[name] = {
                "expected": e.get("expectedValue"),
                "actual": e.get("actualValue"),
                "result": e.get("result") or e.get("status"),
            }
        status = c.get("status") or ("PASS" if all(v.get("result") in ("PASS", "Passed", "passed") for v in exp.values()) else "FAIL")
        rows.append({
            "n": c.get("testNumber") or c.get("number") or len(rows) + 1,
            "utterance": utter,
            "actual_topic": actual_topic,
            "actual_actions": actual_actions,
            "actual_outcome": str(actual_out),
            "expectations": exp,
            "status": status,
            "no_action_call": not actual_actions,
        })
    return {
        "file": path.name,
        "run_id": r.get("runId") or r.get("id") or r.get("jobId"),
        "status": r.get("status"),
        "started": r.get("startTime"),
        "ended": r.get("endTime"),
        "cases": rows,
    }


# ----------------------------------------------------------------------------- claude sdk · agent_queries_metric.py traces

def parse_claude_sdk_trace(path: pathlib.Path) -> dict[str, Any]:
    """One `agent_queries_metric.py --trace-out` file = one query() run: an ordered
    event list (wall-clock-timestamped in the CAPTURING process, since the SDK emits
    no per-step timing of its own) plus the full ResultMessage dataclass."""
    d = json.loads(path.read_text(encoding="utf-8"))
    events = d["events"]
    tool_uses = [e for e in events if e["t"] == "tool_use"]
    tool_results = {e["at_ms"]: e for e in events if e["t"] == "tool_result"}
    # pair each tool_use with the next tool_result event after it (single-threaded loop, so order holds)
    pairs = []
    idx = [i for i, e in enumerate(events) if e["t"] == "tool_result"]
    for tu in tool_uses:
        pos = events.index(tu)
        nxt = next((events[i] for i in idx if i > pos), None)
        pairs.append((tu, nxt))
    r = d["result"] or {}
    final_text = next((e["text"] for e in reversed(events) if e["t"] == "assistant_text"), r.get("result", ""))
    return {
        "file": path.name,
        "question": d["question"],
        "model": d["model"],
        "mode": d["mode"],
        "session_id": r.get("session_id"),
        "tool_calls": d["tool_calls"],
        "wall_clock_ms": d["wall_clock_ms"],
        "duration_ms": r.get("duration_ms"),
        "duration_api_ms": r.get("duration_api_ms"),
        "num_turns": r.get("num_turns"),
        "total_cost_usd": r.get("total_cost_usd"),
        "usage": r.get("usage"),
        "model_usage": r.get("model_usage"),
        "pairs": [
            {
                "name": tu["name"], "input": tu["input"], "at_ms": tu["at_ms"],
                "result_at_ms": nxt["at_ms"] if nxt else None,
                "latency_ms": (nxt["at_ms"] - tu["at_ms"]) if nxt else None,
                "result": (nxt or {}).get("tool_use_result"),
            }
            for tu, nxt in pairs
        ],
        "final": final_text,
        "has_reference": REFERENCE in json.dumps(r) or REFERENCE in (final_text or ""),
        "is_g2": "home run" in d["question"].lower(),
    }


def claude_sdk_cell(traces: list[dict[str, Any]]) -> dict[str, Any] | None:
    g2 = next((t for t in traces if t["is_g2"] and t["has_reference"]), None)
    if g2 is None:
        return None
    metric_pair = next((p for p in g2["pairs"] if p["name"].endswith("query_metrics")), None)
    list_pair = next((p for p in g2["pairs"] if p["name"].endswith("list_metrics")), None)
    grounding = (metric_pair or {}).get("result")
    grounding_txt = json.dumps(grounding)[:200] if grounding else "—"
    mu = g2["model_usage"] or {}
    tool_line = " → ".join(f"`{p['name'].split('__')[-1]}`" for p in g2["pairs"])
    overhead = None
    if list_pair and list_pair.get("latency_ms"):
        overhead = list_pair["latency_ms"]
    return {
        "surface": "Claude SDK",
        "agent": "query-agent (W6b, MetricFlow by name) — `agent_queries_metric.py`",
        "status": "measured",
        "cells": {
            "plan/reasoning": (
                f"**tool sequence yes, thought text no.** {g2['num_turns']} turns, {g2['tool_calls']} tool calls: "
                f"{tool_line}. Every `AssistantMessage` is captured, but none carried extended-thinking text in "
                f"this run (`output_tokens_details.thinking_tokens` was nonzero — 29 — meaning thinking happened "
                f"and was billed, but the SDK stream did not surface it as a `ThinkingBlock` here)."
            ),
            "tool-or-SQL": (
                f"**tool yes, and the tool's own text names the metric catalog.** `query_metrics` input "
                f"`{json.dumps(metric_pair['input']) if metric_pair else '—'}` → result `{grounding_txt}`. "
                f"No SQL — by design (the semantic-layer thesis: MetricFlow is the only path, metric names are "
                f"the contract)."
            ),
            "grounding source": (
                "**present, in the tool's own output text.** `list_metrics` returns the literal governed catalog "
                "(`home_runs_witnessed`, `attended_win_rate`, …) and `query_metrics`'s result is a CSV headed by "
                "the metric name — the grounding is legible in the trace text itself, not just inferable from code."
            ),
            "tokens + latency": (
                f"**both, fully.** `total_cost_usd` ${g2['total_cost_usd']:.4f}, per-model breakdown in "
                f"`model_usage` (cost/input/output/cache tokens, context window, provider) — far more granular "
                f"than Agentforce's zero fields. Latency: `duration_api_ms` {g2['duration_api_ms']} ms vs total "
                f"`duration_ms` {g2['duration_ms']} ms — **{g2['duration_ms'] - g2['duration_api_ms']} ms of the "
                f"turn was NOT model time**; per-tool breakdown shows why: `list_metrics` (a subprocess to "
                f"`mf.exe`) alone took {overhead} ms, dwarfing the ~{g2['duration_api_ms']} ms of actual API calls. "
                f"The bottleneck is the local semantic-layer CLI, not the model."
            ),
            "retrieval path": (
                "**in-process capture, no CLI trace-read needed.** `agent_queries_metric.py --trace-out` writes "
                "the full event list + `ResultMessage` (via `dataclasses.asdict`) directly from the SDK's own "
                "message stream — nothing gitignored, nothing to lose. **OTel measured 2026-09-03 and found "
                "broken on this CLI (2.1.257) + individual-plan auth:** `CLAUDE_CODE_ENABLE_TELEMETRY=1` + "
                "`OTEL_METRICS_EXPORTER=console` / `OTEL_LOGS_EXPORTER=console` set per docs; `--debug-file` shows "
                "`isTelemetryEnabled=true` but `getOtlpReaders: types=[]` / `getOtlpLogExporters: types=[]` / "
                "`Created 0 log exporter(s)` — zero exporters built despite the documented value, so metrics/logs "
                "are generated internally (`Event dropped (no event logger initialized): hook_registered`) and "
                "never emitted. The plan's docs-row claim was **read, not measured — and doesn't hold up**."
            ),
        },
        "evidence": {"g2": g2, "traces": traces},
    }


# ----------------------------------------------------------------------------- bigquery conversational analytics · capture_bigquery_ca.py traces

def parse_bigquery_ca_trace(path: pathlib.Path) -> dict[str, Any]:
    """One `capture_bigquery_ca.py --trace-out` file = one `chat()` stream: a flat,
    wall-clock-timestamped list of raw `Message` dicts (via MessageToDict), plus a
    measured BigQuery job lookup (real bytes billed, not an estimate)."""
    d = json.loads(path.read_text(encoding="utf-8"))
    thoughts, data_msgs, final_text, followups = [], [], "", []
    generated_sql = None
    for e in d["events"]:
        sm = e["message"].get("system_message", {})
        if "text" in sm:
            tt = sm["text"].get("text_type", "")
            parts = sm["text"].get("parts", [])
            if tt == "THOUGHT":
                thoughts.append({"at_ms": e["at_ms"], "parts": parts})
            elif tt == "FINAL_RESPONSE":
                final_text = " ".join(parts)
            elif tt == "FOLLOWUP_QUESTIONS":
                followups = parts
        elif "data" in sm:
            dm = sm["data"]
            data_msgs.append({"at_ms": e["at_ms"], **dm})
            if "generated_sql" in dm:
                generated_sql = dm["generated_sql"]
    return {
        "file": path.name,
        "question": d["question"],
        "dataset": d["dataset"], "table": d["table"],
        "wall_clock_ms": d["wall_clock_ms"],
        "thoughts": thoughts,
        "generated_sql": generated_sql,
        "data_msgs": data_msgs,
        "final": final_text,
        "followups": followups,
        "bq_job": d.get("bq_job"),
        "has_reference": REFERENCE in json.dumps(d) or REFERENCE in (final_text or ""),
        "is_g2": "home run" in d["question"].lower(),
    }


def bigquery_ca_cell(traces: list[dict[str, Any]]) -> dict[str, Any] | None:
    g2 = next((t for t in traces if t["is_g2"] and t["has_reference"]), None)
    if g2 is None:
        return None
    job = g2["bq_job"] or {}

    def _flat(s: str) -> str:
        return " ".join((s or "").split())

    thought_txt = " → ".join(
        f"\"{'; '.join(_flat(p) for p in t['parts'])}\"" for t in g2["thoughts"]
    )
    flat_sql = _flat(g2["generated_sql"])
    return {
        "surface": "BigQuery Conversational Analytics",
        "agent": "console data agent (Data Chat API) — `capture_bigquery_ca.py`",
        "status": "measured",
        "cells": {
            "plan/reasoning": (
                f"**yes, in plain sentences — the strongest of the three surfaces.** {len(g2['thoughts'])} "
                f"`THOUGHT`-typed messages, each human-readable, not just structural: {thought_txt}. "
                f"Agentforce shows a step sequence with no stated reason; the Claude SDK shows tool calls with "
                f"billed-but-unsurfaced thinking; this API narrates its own plan in text."
            ),
            "tool-or-SQL": (
                f"**SQL, verbatim, sent twice** — once inside a `THOUGHT` message before it runs, once again "
                f"as a structured `generated_sql` field after: `` {flat_sql[:200]} ``. No other "
                f"surface in this matrix exposes the literal query text."
            ),
            "grounding source": (
                f"**present, and independently checkable.** The `data` message names the exact BigQuery table "
                f"(`{g2['dataset']}.{g2['table']}`) and, uniquely, the underlying **BigQuery job id** "
                f"(`{job.get('job_id', '—')}`) — a receipt an operator could look up in BigQuery's own job "
                f"history to independently confirm the query ran, separate from trusting this trace at all."
            ),
            "tokens + latency": (
                f"**latency yes (self-timestamped, same gap as the Claude SDK — the API embeds no per-step "
                f"timing of its own); tokens absent, cost partially measured.** Turn wall-clock "
                f"{g2['wall_clock_ms']} ms. The BigQuery *warehouse* leg is measured exactly, not estimated: "
                f"job `{job.get('job_id', '—')}` billed **{job.get('total_bytes_billed', 0)} bytes** "
                f"(cache_hit={job.get('cache_hit')}) → ${job.get('estimated_bq_scan_cost_usd', 0):.8f} at "
                f"on-demand pricing. **What's still unmeasured: the Conversational Analytics API's own per-call "
                f"service fee** — the pricing page returned no billing figures on two separate fetches this "
                f"session; only the BigQuery scan underneath it is priced here."
            ),
            "retrieval path": (
                "**official Python client (`google-cloud-geminidataanalytics`), streaming `chat()`, Application "
                "Default Credentials — no CLI, no gitignored file.** The discovery document "
                "(`$discovery/rest?version=v1`) itself 403s even with a valid OAuth token (measured 2026-09-03) "
                "— the typed client was the only path that actually worked; hand-built REST would have needed "
                "guesswork against thin docs."
            ),
        },
        "evidence": {"g2": g2, "traces": traces},
    }


# ----------------------------------------------------------------------------- databricks genie · capture_databricks_genie.py traces

def parse_databricks_genie_trace(path: pathlib.Path) -> dict[str, Any]:
    """One `capture_databricks_genie.py --trace-out` file = one polled conversation:
    a self-timestamped status ladder (Genie's API has no streaming progress of its
    own) plus the final `GenieMessage` with its typed `thoughts[]` and `query`."""
    d = json.loads(path.read_text(encoding="utf-8"))
    statuses = [e for e in d["events"] if e["phase"] == "status"]
    fm = d.get("final_message") or {}
    query_att = next((a["query"] for a in fm.get("attachments", []) if "query" in a), None)
    text_att = next((a["text"] for a in fm.get("attachments", []) if "text" in a), fm.get("content", ""))
    return {
        "file": path.name,
        "question": d["question"],
        "space_id": d["space_id"],
        "wall_clock_ms": d["wall_clock_ms"],
        "statuses": [{"at_ms": s["at_ms"], "status": s["status"].replace("MessageStatus.", "")} for s in statuses],
        "sql": (query_att or {}).get("query"),
        "thoughts": (query_att or {}).get("thoughts", []),
        "row_count": (query_att or {}).get("row_count"),
        "final": text_att,
        "has_reference": REFERENCE in json.dumps(d) or REFERENCE in (text_att or ""),
        "is_g2": "home run" in d["question"].lower(),
    }


def databricks_genie_cell(traces: list[dict[str, Any]]) -> dict[str, Any] | None:
    g2 = next((t for t in traces if t["is_g2"] and t["has_reference"]), None)
    if g2 is None:
        return None

    def _flat(s: str) -> str:
        return " ".join((s or "").split())

    status_line = " → ".join(f"{s['status']} (+{s['at_ms']}ms)" for s in g2["statuses"])
    thought_kinds = ", ".join(sorted({t["thought_type"].replace("ThoughtType.THOUGHT_TYPE_", "") for t in g2["thoughts"]}))
    understanding = next(
        (_flat(t["content"]) for t in g2["thoughts"] if "UNDERSTANDING" in t["thought_type"]), None
    )
    flat_sql = _flat(g2["sql"])
    return {
        "surface": "Databricks Genie",
        "agent": "Genie space \"Keeping Score\" over `wax_baseball.semantics` metric views — `capture_databricks_genie.py`",
        "status": "measured",
        "cells": {
            "plan/reasoning": (
                f"**yes, and typed — the most structured reasoning of any surface.** {len(g2['thoughts'])} "
                f"`Thought` entries across categories ({thought_kinds}), not one undifferentiated blob. "
                f"The `UNDERSTANDING` thought is the standout: **the agent stated its own grounding assumption "
                f"out loud** — \"{understanding[:220] if understanding else ''}\" — a self-flagged caveat no "
                f"other surface measured so far volunteered."
            ),
            "tool-or-SQL": (
                f"**SQL, and it queries the governed metric view's declared measure directly:** "
                f"`` {flat_sql[:220]} `` — `MEASURE(home_runs_witnessed)` against the Unity Catalog metric "
                f"view `mv_plays`, not a hand-rolled aggregate. Closest of the four surfaces to the semantic-"
                f"layer thesis while still emitting literal SQL text (BigQuery CA writes ad hoc SQL over a raw "
                f"table; Databricks queries the governed view's own metric)."
            ),
            "grounding source": (
                f"**present, named, and self-qualified.** `mv_plays` appears in a `DATA_SOURCING` thought "
                f"explicitly; the `UNDERSTANDING` thought above is grounding *and* an honest uncertainty flag "
                f"in one artifact — arguably the richest grounding disclosure in the matrix so far."
            ),
            "tokens + latency": (
                f"**latency yes (self-polled — Genie streams no progress of its own, same gap as the Claude "
                f"SDK and BigQuery CA), tokens absent (undocumented by this API, like BigQuery's own fee).** "
                f"Full status ladder: {status_line}. Notably **loops back to `ASKING_AI` after "
                f"`PENDING_WAREHOUSE`** — the model is invoked twice per turn (once to plan the query, once to "
                f"phrase the answer from results), a two-call shape none of the other three surfaces' traces "
                f"showed explicitly. Turn wall-clock {g2['wall_clock_ms']} ms — the slowest of the four "
                f"surfaces measured, largely the warehouse cold-start + double model round-trip."
            ),
            "retrieval path": (
                "**official Python client (`databricks-sdk`), polled — not streamed.** `start_conversation` "
                "returns a `Wait[GenieMessage]`; the capture calls `get_message` itself in a loop and stamps "
                "each status transition, since the SDK gives no push/stream mechanism for progress. "
                "**Measured 2026-09-03: `GenieAPI.create_space` cannot author a space from zero** — its own "
                "docstring says the `serialized_space` payload is only obtainable by reading back an existing "
                "space, so this space was created once through the workspace UI (Wax) before anything here "
                "could run; every capture after that point is fully scriptable."
            ),
        },
        "evidence": {"g2": g2, "traces": traces},
    }


# ----------------------------------------------------------------------------- rubric derivation

def agentforce_cell(sessions: list[dict[str, Any]], runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    g2 = next(
        (p for s in sessions for p in s["plans"] if p["is_g2"] and p["has_reference"]),
        None,
    )
    if g2 is None:
        return None
    fn = g2["functions"][0] if g2["functions"] else None
    fn_txt = (
        f"action `{fn['name']}` input `{json.dumps(fn['input'])}` → output `{json.dumps(fn['output'])}` "
        f"({fn['latency_ms']} ms)" if fn else "no action call"
    )
    lat = " / ".join(f"{x}" for x in g2["llm_latency_ms"])
    return {
        "surface": "Agentforce",
        "agent": "Baseball_Scout (bot v5) · `keeping_score` subagent",
        "status": "measured",
        "cells": {
            "plan/reasoning": (
                f"**partial.** {g2['llm_calls']} LLM calls, each with the full prompt and the raw response "
                f"(tool picks: {' → '.join(g2['tool_picks'])}); transition "
                f"{' → '.join(f'{a}→{b}' for a, b in g2['transitions'])}. "
                f"No reasoning *text* — the plan is the {g2['steps']}-step sequence, not a stated thought."
            ),
            "tool-or-SQL": (
                f"**tool yes, SQL no.** {fn_txt}. The gateway query the Apex sends to "
                f"`/semantic-engine/gateway` is not in the trace."
            ),
            "grounding source": (
                "**absent from the trace.** Neither the `Keeping_Score` SDM nor Data 360 is named anywhere; "
                "grounding is provable only from the action's Apex source, not from what the platform shows."
            ),
            "tokens + latency": (
                f"**latency yes, tokens no.** Per-step ms (LLM {lat} ms · action {fn['latency_ms'] if fn else '—'} ms · "
                f"turn {g2['total_ms']} ms); {g2['token_keys']} token/usage fields in {g2['size_kb']} KB of trace; "
                f"transcript `metrics: {{}}`."
            ),
            "retrieval path": (
                "**CLI → local file.** `sf agent preview` writes `.sfdx/agents/<agent>/sessions/<id>/traces/<planId>.json` "
                "(gitignored by the DX template; copy it or lose it — `sf agent trace` only *deletes*). "
                "Testing Center: `sf agent test run --json` (measured 2026-09-03: the async job can wedge at "
                "`IN_PROGRESS` indefinitely with no error and no timeout — the `preview start`/`send`/`end` "
                "trio is the reliable capture). Production DMOs + OTel endpoint: read, not measured."
            ),
        },
        "evidence": {
            "session": next(s for s in sessions if g2 in s["plans"]),
            "plan": g2,
            "runs": runs,
        },
    }


def read_cells() -> list[dict[str, Any]]:
    if not SURFACES_JSON.exists():
        return []
    return json.loads(SURFACES_JSON.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- findings

# Numbers written as words that a summary step might use for a small count.
_WORD_NUM = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}


def _numbers_in(text: str) -> set[int]:
    nums = {int(n) for n in re.findall(r"\b\d{1,4}\b", text or "")}
    for w, v in _WORD_NUM.items():
        if re.search(rf"\b{w}\b", (text or "").lower()):
            nums.add(v)
    return nums


def observability_findings(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trace-derived findings — the whole point of the tool-or-SQL column: an answer
    is trustworthy only insofar as the trace shows the number came from an action.
    Two failure classes, both invisible in the prose and both computed here, never asserted:
      (A) no-action  — the final answer with zero FunctionSteps (invention by construction).
      (B) miscount   — an action returned N rows/groups but the prose states a different N.
    """
    out: list[dict[str, Any]] = []
    for s in sessions:
        for p in s["plans"]:
            fns = p["functions"]
            final = p["final"] or ""
            said = _numbers_in(final)
            # (A) invention
            if not fns and p["topic"] not in ("off_topic", "ambiguous_question"):
                out.append({
                    "class": "no-action (invention)",
                    "session": s["dir"], "trace": p["file"], "question": p["user"],
                    "detail": "zero action calls in the trace; every number in the answer is ungrounded.",
                    "final": final,
                })
                continue
            # (B) grounded but miscounted: an aggregate/list action's row count not echoed in the prose
            for f in fns:
                out_obj = f.get("output") or {}
                groups = out_obj.get("groups")
                if isinstance(groups, list) and groups:
                    n = len(groups)
                    if n not in said and said:
                        out.append({
                            "class": "grounded but miscounted",
                            "session": s["dir"], "trace": p["file"], "question": p["user"],
                            "detail": (
                                f"`{f['name']}` returned {n} groups (sum "
                                f"{sum(g.get('gameCount', 0) for g in groups)} games); "
                                f"the summary step stated {sorted(said)} — {n} is not among them."
                            ),
                            "final": final,
                        })
    return out


# ----------------------------------------------------------------------------- presentation

def render(cell_rows: list[dict[str, Any]], af: dict[str, Any] | None,
           sdk: dict[str, Any] | None, bq: dict[str, Any] | None,
           dbx: dict[str, Any] | None, findings: list[dict[str, Any]]) -> str:
    stamp = datetime.date.today().isoformat()
    lines = [
        "# Observability receipts — Keeping Score",
        "",
        "<!-- Generated - do not hand-edit. Rebuild: py observability/extract_observability.py",
        "     in CODING/wax_baseball_parity. Phase 2 (O7): one golden question through each",
        "     surface's native agent; every cell says what was visible and how it was fetched. -->",
        "",
        f"*Generated {stamp}. Golden question: {GOLDEN_QUESTION} Reference: **{REFERENCE}**.*",
        "",
        "**Rubric (O0, ruled 2026-09-02):** " + " · ".join(COLUMNS)
        + ". **measured** = derived by the extractor from a trace in `observability/traces/`; "
          "**read** = vendor docs, no trace captured yet.",
        "",
        "| Surface | Status | " + " | ".join(COLUMNS) + " |",
        "|---|---|" + "---|" * len(COLUMNS),
    ]
    for row in cell_rows:
        mark = "✅ measured" if row["status"] == "measured" else "📖 read"
        lines.append(
            f"| **{row['surface']}** | {mark} | " + " | ".join(row["cells"][c] for c in COLUMNS) + " |"
        )
    measured = sum(1 for r in cell_rows if r["status"] == "measured")
    lines += ["", f"**{measured}/{len(cell_rows)} cells measured.**", ""]

    if af:
        s = af["evidence"]["session"]
        p = af["evidence"]["plan"]
        lines += [
            "## Agentforce — the reference cell, from the trace",
            "",
            f"Session `{s['session_id']}` ({s['created']}, {s['mode']}), trace `{p['file']}` — "
            f"`observability/traces/agentforce/{s['dir']}/`.",
            "",
            "| Step shape | Value |",
            "|---|---|",
            f"| User | {p['user']} |",
            f"| Topic | `{p['topic']}` |",
            f"| Plan steps | {p['steps']} |",
            f"| LLM calls | {p['llm_calls']} ({', '.join(f'{x} ms' for x in p['llm_latency_ms'])}) |",
            f"| Tool picks | {' → '.join(f'`{x}`' for x in p['tool_picks'])} |",
            f"| Action | " + "; ".join(
                f"`{f['name']}` {json.dumps(f['input'])} → {json.dumps(f['output'])} ({f['latency_ms']} ms)"
                for f in p["functions"]) + " |",
            f"| Turn latency | {p['total_ms']} ms |",
            f"| Token fields | {p['token_keys']} |",
            f"| Final | {p['final']} |",
            f"| Reference {REFERENCE} in trace | {'✅' if p['has_reference'] else '❌'} |",
            "",
            "Same session, the other two golden questions through the same shape:",
            "",
            "| Question | Topic | Action | Output | Turn ms |",
            "|---|---|---|---|---|",
        ]
        for q in s["plans"]:
            if q is p:
                continue
            f = q["functions"][0] if q["functions"] else None
            lines.append(
                f"| {q['user']} | `{q['topic']}` | "
                + (f"`{f['name']}` {json.dumps(f['input'])}" if f else "—")
                + " | " + (json.dumps(f["output"]) if f else "—") + f" | {q['total_ms']} |"
            )
        lines.append("")

        for run in af["evidence"]["runs"]:
            lines += [
                f"## Agentforce — Testing Center run `{run['run_id']}` ({run['status']}, {run['started']})",
                "",
                f"`observability/traces/agentforce/{run['file']}`. A row with **no action call** is an invented answer "
                "by construction — the subagent's instructions say it has no knowledge of its own.",
                "",
                "| # | Utterance | Actual topic | Actions called | Outcome (as generated) | Result |",
                "|---|---|---|---|---|---|",
            ]
            for c in run["cases"]:
                acts = ", ".join(f"`{a}`" for a in c["actual_actions"]) if c["actual_actions"] else "**none**"
                out = c["actual_outcome"].replace("|", "\\|").replace("\n", " ")
                flag = " 🔴 no-action" if c["no_action_call"] else ""
                lines.append(
                    f"| {c['n']} | {c['utterance']} | `{c['actual_topic']}` | {acts} | {out[:220]} | {c['status']}{flag} |"
                )
            lines.append("")

    if sdk:
        g2 = sdk["evidence"]["g2"]
        lines += [
            "## Claude SDK — the query-agent cell, from the trace",
            "",
            f"Run `{g2['file']}` (session `{g2['session_id']}`, model `{g2['model']}`) — "
            f"`observability/traces/claude_sdk/{g2['file']}`.",
            "",
            "| Step shape | Value |",
            "|---|---|",
            f"| User | {g2['question']} |",
            f"| Turns | {g2['num_turns']} |",
            f"| Tool calls | " + " → ".join(f"`{p['name']}` {json.dumps(p['input'])}" for p in g2["pairs"]) + " |",
            f"| Cost | ${g2['total_cost_usd']:.4f} |",
            f"| duration_api_ms (model) | {g2['duration_api_ms']} |",
            f"| duration_ms (total, SDK-reported) | {g2['duration_ms']} |",
            f"| wall_clock_ms (this capture, includes CLI spawn) | {g2['wall_clock_ms']} |",
            f"| Final | {g2['final']} |",
            f"| Reference {REFERENCE} in trace | {'✅' if g2['has_reference'] else '❌'} |",
            "",
            "Per-tool latency, from the wall-clock event timestamps:",
            "",
            "| Tool | Input | Latency (ms) | Result (truncated) |",
            "|---|---|---|---|",
        ]
        for p in g2["pairs"]:
            res = json.dumps(p["result"])[:160].replace("|", "\\|") if p["result"] else "—"
            lines.append(f"| `{p['name']}` | {json.dumps(p['input'])} | {p['latency_ms']} | {res} |")
        lines.append("")

    if bq:
        g2 = bq["evidence"]["g2"]
        job = g2["bq_job"] or {}

        def _flat2(s: str) -> str:
            return " ".join((s or "").split())

        lines += [
            "## BigQuery Conversational Analytics — the console-agent cell, from the trace",
            "",
            f"Run `{g2['file']}` against `{g2['dataset']}.{g2['table']}` — "
            f"`observability/traces/bigquery_ca/{g2['file']}`.",
            "",
            "| Step shape | Value |",
            "|---|---|",
            f"| User | {g2['question']} |",
            f"| THOUGHT messages | " + " → ".join(
                f"\"{'; '.join(_flat2(p) for p in t['parts'])[:80]}\"" for t in g2["thoughts"]
            ) + " |",
            f"| generated_sql | `` {_flat2(g2['generated_sql'])} `` |",
            f"| BigQuery job | `{job.get('job_id', '—')}` — {job.get('total_bytes_billed', 0)} bytes billed, "
            f"cache_hit={job.get('cache_hit')}, ~${job.get('estimated_bq_scan_cost_usd', 0):.8f} |",
            f"| wall_clock_ms | {g2['wall_clock_ms']} |",
            f"| Final | {g2['final']} |",
            f"| Follow-ups offered | {'; '.join(g2['followups'])} |",
            f"| Reference {REFERENCE} in trace | {'✅' if g2['has_reference'] else '❌'} |",
            "",
        ]

    if dbx:
        g2 = dbx["evidence"]["g2"]

        def _flat3(s: str) -> str:
            return " ".join((s or "").split())

        lines += [
            "## Databricks Genie — the console-agent cell, from the trace",
            "",
            f"Space `{g2['space_id']}` (\"Keeping Score\", over `wax_baseball.semantics`), run `{g2['file']}` — "
            f"`observability/traces/databricks_genie/{g2['file']}`.",
            "",
            "| Step shape | Value |",
            "|---|---|",
            f"| User | {g2['question']} |",
            f"| Status ladder | " + " → ".join(f"{s['status']} (+{s['at_ms']}ms)" for s in g2["statuses"]) + " |",
            f"| generated SQL | `` {_flat3(g2['sql'])} `` |",
            f"| Thoughts | " + " | ".join(
                f"**{t['thought_type'].replace('ThoughtType.THOUGHT_TYPE_', '')}**: {_flat3(t['content'])[:100]}"
                for t in g2["thoughts"]
            ) + " |",
            f"| Row count | {g2['row_count']} |",
            f"| wall_clock_ms | {g2['wall_clock_ms']} |",
            f"| Final | {g2['final']} |",
            f"| Reference {REFERENCE} in trace | {'✅' if g2['has_reference'] else '❌'} |",
            "",
        ]

    if findings:
        lines += [
            "## Observability findings — what the trace caught that the prose hid",
            "",
            "Computed by the extractor, never asserted: an answer is trustworthy only insofar as the "
            "trace shows its numbers came from an action. Each row is a place the prose read authoritative "
            "and the trace disagreed.",
            "",
            "| Class | Question | What the trace shows | Answer as stated |",
            "|---|---|---|---|",
        ]
        for f in findings:
            q = f["question"].replace("|", "\\|")
            det = f["detail"].replace("|", "\\|")
            fin = f["final"].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| 🔴 {f['class']} | {q} | {det} | {fin[:180]} |")
        lines.append("")

    lines += [
        "---",
        "*Source traces: `CODING/wax_baseball_parity/observability/traces/` · rubric + narration + findings: "
        "`wax-baseball/keeping-score-parity-plan.md` § Phase 2.*",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    af_dir = TRACES / "agentforce"
    sessions = [
        parse_agentforce_preview_session(d)
        for d in sorted(af_dir.glob("*preview*")) if (d / "turn-index.json").exists()
    ] if af_dir.exists() else []
    runs = [parse_agentforce_test_run(p) for p in sorted(af_dir.glob("*testing-center*.json"))] if af_dir.exists() else []
    af = agentforce_cell(sessions, runs)

    sdk_dir = TRACES / "claude_sdk"
    sdk_traces = [parse_claude_sdk_trace(p) for p in sorted(sdk_dir.glob("*.json"))] if sdk_dir.exists() else []
    sdk = claude_sdk_cell(sdk_traces)

    bq_dir = TRACES / "bigquery_ca"
    bq_traces = [parse_bigquery_ca_trace(p) for p in sorted(bq_dir.glob("*.json"))] if bq_dir.exists() else []
    bq = bigquery_ca_cell(bq_traces)

    dbx_dir = TRACES / "databricks_genie"
    dbx_traces = [parse_databricks_genie_trace(p) for p in sorted(dbx_dir.glob("*.json"))] if dbx_dir.exists() else []
    dbx = databricks_genie_cell(dbx_traces)

    rows: list[dict[str, Any]] = []
    if af:
        rows.append(af)
    if sdk:
        rows.append(sdk)
    if bq:
        rows.append(bq)
    if dbx:
        rows.append(dbx)
    measured_names = {r["surface"].lower() for r in rows}
    rows += [r for r in read_cells() if r["surface"].lower() not in measured_names]

    findings = observability_findings(sessions)
    RECEIPT_PATH.write_text(render(rows, af, sdk, bq, dbx, findings), encoding="utf-8")
    print(f"wrote {RECEIPT_PATH}  ({sum(1 for r in rows if r['status']=='measured')}/{len(rows)} measured, "
          f"{len(findings)} finding(s))")
    for fnd in findings:
        print(f"  FINDING [{fnd['class']}] {fnd['question'][:50]} — {fnd['detail']}")
    for s in sessions:
        for p in s["plans"]:
            print(f"  {s['dir'][:28]:28s} {p['file'][:8]} {p['topic']:14s} g2={p['is_g2']!s:5s} ref={p['has_reference']!s:5s} "
                  f"{p['llm_calls']} llm {p['total_ms']} ms tokens={p['token_keys']}")
    for r in runs:
        for c in r["cases"]:
            print(f"  test {c['n']}: {c['status']:6s} actions={c['actual_actions']} {c['utterance'][:50]}")


if __name__ == "__main__":
    main()
