#!/usr/bin/env python3
"""
BigQuery Conversational Analytics API capture — the O3 leg of the O7 trio.

Unlike Agentforce (an existing DX project) and the Claude SDK (an existing
query-agent script), there is no standing "console agent" app for this surface
in the build — the API call itself is the whole exercise, so the capture lives
here rather than a separate CODING project. Streams `DataChatServiceClient.chat()`
against a BigQuery table, wall-clock-timestamps every message at receipt (the
API embeds no per-step execution time of its own, same gap as the Claude SDK),
and — since the response carries a `big_query_job` job id — looks that job up
afterward for its actual `total_bytes_processed`/`total_bytes_billed`, so cost
is measured, not estimated.

Auth: Application Default Credentials (`gcloud auth application-default login`).
Requires `google-cloud-geminidataanalytics` (pip) and the
`geminidataanalytics.googleapis.com` API enabled on the project.

    py observability/capture_bigquery_ca.py --trace-out traces/bigquery_ca/<date>-g2.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import time
from typing import Any

import google.cloud.geminidataanalytics as gda
from google.cloud import bigquery
from google.protobuf.json_format import MessageToDict

DEFAULT_QUESTION = (
    "How many home runs were hit in games Wax attended? "
    "Home runs are event_code 23 in this table."
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--project", default="augmented-world-262319")
    parser.add_argument("--location", default="global")
    parser.add_argument("--dataset", default="wax_baseball_dbt")
    parser.add_argument("--table", default="fct_plays")
    parser.add_argument("--trace-out", required=True)
    args = parser.parse_args()

    client = gda.DataChatServiceClient()
    ds = gda.DatasourceReferences(
        bq=gda.BigQueryTableReferences(
            table_references=[
                gda.BigQueryTableReference(
                    project_id=args.project, dataset_id=args.dataset, table_id=args.table
                )
            ]
        )
    )
    req = gda.ChatRequest(
        parent=f"projects/{args.project}/locations/{args.location}",
        messages=[gda.Message(user_message=gda.UserMessage(text=args.question))],
        inline_context=gda.Context(datasource_references=ds),
    )

    print(f"=== BigQuery Conversational Analytics · {args.dataset}.{args.table} ===")
    print(f"Q: {args.question}\n")

    t0 = time.time()
    events: list[dict[str, Any]] = []
    bq_job_ref: dict[str, str] | None = None
    error_text: str | None = None
    try:
        for msg in client.chat(request=req):
            at_ms = round((time.time() - t0) * 1000)
            d = MessageToDict(msg._pb, preserving_proto_field_name=True)
            events.append({"at_ms": at_ms, "message": d})
            sm = d.get("system_message", {})
            if "text" in sm:
                tt = sm["text"].get("text_type", "")
                parts = " | ".join(sm["text"].get("parts", []))
                print(f"[{at_ms}ms] {tt}: {parts[:200]}")
            elif "data" in sm:
                dm = sm["data"]
                if "generated_sql" in dm:
                    print(f"[{at_ms}ms] DATA generated_sql: {dm['generated_sql'][:200]}")
                elif "big_query_job" in dm:
                    j = dm["big_query_job"]
                    bq_job_ref = {"project_id": j["project_id"], "job_id": j["job_id"], "location": j.get("location", "US")}
                    print(f"[{at_ms}ms] DATA big_query_job: {j['job_id']}")
                elif "result" in dm:
                    print(f"[{at_ms}ms] DATA result: {json.dumps(dm['result'])[:200]}")
                else:
                    print(f"[{at_ms}ms] DATA (query datasources)")
    except Exception as exc:  # noqa: BLE001
        error_text = str(exc)
        print(f"\n=== ENDED WITH ERROR: {exc} ===")

    wall_clock_ms = round((time.time() - t0) * 1000)
    print(f"\n=== DONE · {len(events)} message(s) · {wall_clock_ms} ms ===")

    # Cost is MEASURED, not estimated: look up the actual BQ job's bytes billed.
    job_stats = None
    if bq_job_ref:
        try:
            bq = bigquery.Client(project=bq_job_ref["project_id"])
            job = bq.get_job(bq_job_ref["job_id"], location=bq_job_ref["location"])
            bytes_billed = job.total_bytes_billed or 0
            job_stats = {
                "job_id": bq_job_ref["job_id"],
                "total_bytes_processed": job.total_bytes_processed,
                "total_bytes_billed": bytes_billed,
                "cache_hit": job.cache_hit,
                "slot_millis": job.slot_millis,
                # On-demand BigQuery pricing: $6.25 / TiB, measured against the
                # 1 TiB free tier per month — see the printed line below for the
                # caveat this doesn't capture (Conversational Analytics API's own
                # per-call/token fee, which is separate and still undocumented).
                "estimated_bq_scan_cost_usd": round(bytes_billed / (1024**4) * 6.25, 8) if bytes_billed else 0.0,
            }
            print(f"[bq job] {bq_job_ref['job_id']}: "
                  f"{job.total_bytes_processed} bytes processed, "
                  f"{bytes_billed} bytes billed, cache_hit={job.cache_hit}, "
                  f"~${job_stats['estimated_bq_scan_cost_usd']:.8f} BQ scan cost "
                  f"(the Conversational Analytics API's OWN per-call fee is separate and undocumented)")
        except Exception as exc:  # noqa: BLE001
            print(f"[bq job] lookup failed: {exc}")

    trace = {
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "surface": "bigquery_conversational_analytics",
        "question": args.question,
        "project": args.project,
        "dataset": args.dataset,
        "table": args.table,
        "wall_clock_ms": wall_clock_ms,
        "events": events,
        "bq_job": job_stats,
        "error": error_text,
    }
    out_path = pathlib.Path(args.trace_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")
    print(f"\n[trace] wrote {out_path}")


if __name__ == "__main__":
    main()
