#!/usr/bin/env python3
"""
Export the Keeping Score parity corpus from BigQuery (wax_baseball_dbt marts)
to local Parquet files.

This is a GENERATOR, not a data dump: rerun it any time the upstream dbt
marts change and it will re-export deterministically. Idempotent — each run
overwrites its own output files.

Usage:
    python scripts/export_bigquery.py

Requires:
    google-cloud-bigquery, pandas, pyarrow, db-dtypes
    ADC auth already set up (gcloud auth application-default login)

Add a table by adding one entry to TABLES below. If a mart turns out to be
unfiltered (all of Retrosheet rather than just Wax's attended games), add
its join key to JOIN_KEY_OVERRIDES and it will be inner-joined against
fct_attended_games on that key automatically — see _needs_filtering().
"""

from __future__ import annotations

import pathlib
import sys

import pandas as pd
from google.cloud import bigquery

PROJECT = "augmented-world-262319"
DATASET = "wax_baseball_dbt"
DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"

# Row-count threshold above which a table is assumed to be an unfiltered
# Retrosheet-wide mart rather than Wax's attended-games corpus, and gets
# filtered down via an inner join to fct_attended_games.
UNFILTERED_ROW_THRESHOLD = 100_000

# The table list — extend here as new marts are added (e.g.
# fct_attended_team_games from W1). Each entry is just the mart name;
# it is exported as SELECT * unless it needs filtering (see above).
TABLES: list[str] = [
    "fct_attended_games",
    "fct_plays",
    "fct_game_attendee",
    "dim_attendee",
    "dim_event_code",
    "fct_games",
    "fct_attended_team_games",  # W1: team-game grain (win rate, team as dimension)
    "fct_hof_sightings",        # W1: the four-way join, materialized once
]

# Join key used to filter a table down to Wax's attended games, if the
# table turns out to be unfiltered. Override per-table here if a table's
# join key differs from the default "game_id".
JOIN_KEY_OVERRIDES: dict[str, str] = {}
DEFAULT_JOIN_KEY = "game_id"
FILTER_ANCHOR_TABLE = "fct_attended_games"


def _client() -> bigquery.Client:
    return bigquery.Client(project=PROJECT)


def _row_count(client: bigquery.Client, table: str) -> int:
    query = f"SELECT COUNT(*) AS n FROM `{PROJECT}.{DATASET}.{table}`"
    return int(next(iter(client.query(query).result()))["n"])


def _export_table(client: bigquery.Client, table: str) -> pd.DataFrame:
    """Fetch a table as a DataFrame, filtering to Wax's attended games if
    the raw row count suggests it's unfiltered Retrosheet data."""
    n = _row_count(client, table)
    join_key = JOIN_KEY_OVERRIDES.get(table, DEFAULT_JOIN_KEY)

    if n > UNFILTERED_ROW_THRESHOLD and table != FILTER_ANCHOR_TABLE:
        print(
            f"  {table}: {n:,} rows unfiltered — filtering via inner join "
            f"to {FILTER_ANCHOR_TABLE} on {join_key}"
        )
        query = f"""
            SELECT t.*
            FROM `{PROJECT}.{DATASET}.{table}` AS t
            INNER JOIN `{PROJECT}.{DATASET}.{FILTER_ANCHOR_TABLE}` AS a
                ON t.{join_key} = a.{join_key}
        """
    else:
        print(f"  {table}: {n:,} rows (already scoped, no filtering needed)")
        query = f"SELECT * FROM `{PROJECT}.{DATASET}.{table}`"

    return client.query(query).to_dataframe()


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    client = _client()

    print(f"Exporting {len(TABLES)} tables from {PROJECT}.{DATASET} ...")
    counts: dict[str, int] = {}
    for table in TABLES:
        df = _export_table(client, table)
        out_path = DATA_DIR / f"{table}.parquet"
        df.to_parquet(out_path, index=False)
        counts[table] = len(df)
        print(f"  -> wrote {out_path} ({len(df):,} rows, {len(df.columns)} cols)")

    print("\nExport summary:")
    total = 0
    for table, n in counts.items():
        print(f"  {table:24s} {n:>8,}")
        total += n
    print(f"  {'TOTAL':24s} {total:>8,}")

    if total > UNFILTERED_ROW_THRESHOLD:
        print(
            f"\nWARNING: total row count {total:,} exceeds the expected "
            "tens-of-thousands parity corpus size. Check for an unfiltered mart.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
