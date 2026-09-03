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
           findings: list[dict[str, Any]]) -> str:
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

    rows: list[dict[str, Any]] = []
    if af:
        rows.append(af)
    measured_names = {r["surface"].lower() for r in rows}
    rows += [r for r in read_cells() if r["surface"].lower() not in measured_names]

    findings = observability_findings(sessions)
    RECEIPT_PATH.write_text(render(rows, af, findings), encoding="utf-8")
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
