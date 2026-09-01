#!/usr/bin/env python3
"""
Loads the Keeping Score parity corpus (local Parquet, written by
export_bigquery.py) into Databricks via a Unity Catalog Volume + CTAS.

Idempotent — CREATE OR REPLACE TABLE per file, and the volume upload
overwrites, so re-runs are safe.

Target resolution (see plan): try catalog `wax_baseball`, schema `parity`
first. If catalog creation fails (storage/permissions), fall back to
schema `wax_baseball` inside the existing `lahman_baseball` catalog and
report which target was used.

Usage:
    python scripts/load_databricks.py

Requires:
    databricks-sql-connector, databricks-sdk
    ~/.databrickscfg profile 'wax_baseball' (host + token; never hardcoded
    here — see _dbx_conn.py)
"""

from __future__ import annotations

import pathlib
import sys

from _dbx_conn import get_connection

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"

# Same table list as export_bigquery.py — extend here too when a new mart
# (e.g. fct_attended_team_games) is added.
TABLES: list[str] = [
    "fct_attended_games",
    "fct_plays",
    "fct_game_attendee",
    "dim_attendee",
    "dim_event_code",
    "fct_games",
]

PREFERRED_CATALOG = "wax_baseball"
PREFERRED_SCHEMA = "parity"
FALLBACK_CATALOG = "lahman_baseball"
FALLBACK_SCHEMA = "wax_baseball"
VOLUME_NAME = "parity_files"


def _exec(cursor, sql: str, quiet: bool = False) -> None:
    if not quiet:
        print(f"    SQL> {sql.strip().splitlines()[0][:100]}")
    cursor.execute(sql)


def _resolve_target(cursor) -> tuple[str, str]:
    """Try to create/use the preferred catalog.schema; fall back on failure."""
    try:
        _exec(cursor, f"CREATE CATALOG IF NOT EXISTS {PREFERRED_CATALOG}")
        _exec(
            cursor,
            f"CREATE SCHEMA IF NOT EXISTS {PREFERRED_CATALOG}.{PREFERRED_SCHEMA}",
        )
        return PREFERRED_CATALOG, PREFERRED_SCHEMA
    except Exception as exc:  # noqa: BLE001 - report and fall back
        print(f"  Preferred catalog '{PREFERRED_CATALOG}' unavailable: {exc}")
        print(f"  Falling back to {FALLBACK_CATALOG}.{FALLBACK_SCHEMA}")
        _exec(
            cursor,
            f"CREATE SCHEMA IF NOT EXISTS {FALLBACK_CATALOG}.{FALLBACK_SCHEMA}",
        )
        return FALLBACK_CATALOG, FALLBACK_SCHEMA


def main() -> None:
    parquets = sorted(DATA_DIR.glob("*.parquet"))
    if not parquets:
        print(f"No parquet files found in {DATA_DIR}. Run export_bigquery.py first.", file=sys.stderr)
        sys.exit(1)

    conn = get_connection()
    cursor = conn.cursor()

    print("==> 1. Resolve target catalog.schema")
    catalog, schema = _resolve_target(cursor)
    print(f"  Using target: {catalog}.{schema}")

    volume_path = f"/Volumes/{catalog}/{schema}/{VOLUME_NAME}"
    print(f"\n==> 2. Create volume {catalog}.{schema}.{VOLUME_NAME}")
    _exec(cursor, f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.{VOLUME_NAME}")

    print(f"\n==> 3. Upload {len(parquets)} Parquet files to {volume_path}")
    for pq in parquets:
        dest = f"{volume_path}/{pq.name}"
        print(f"    PUT {pq.name} -> {dest}")
        # Idempotent re-run: remove any existing file at this path first,
        # since PUT has no OVERWRITE keyword in Databricks SQL.
        try:
            _exec(cursor, f"REMOVE '{dest}'", quiet=True)
        except Exception:
            pass  # file didn't exist yet - fine
        # NOTE: local path MUST use forward slashes. The server-side SQL
        # parser treats backslashes as string escapes, so a Windows path
        # like C:\Users\... arrives mangled (backslashes silently dropped)
        # and fails the staging_allowed_local_path check. pq.as_posix()
        # sidesteps this entirely.
        _exec(cursor, f"PUT '{pq.as_posix()}' INTO '{dest}'", quiet=True)

    print("\n==> 4. CREATE OR REPLACE TABLE ... AS SELECT per Parquet file")
    counts: dict[str, int] = {}
    for pq in parquets:
        table = pq.stem
        src = f"{volume_path}/{pq.name}"
        fq_table = f"{catalog}.{schema}.{table}"
        print(f"    {fq_table}")
        _exec(
            cursor,
            f"""
            CREATE OR REPLACE TABLE {fq_table}
            AS SELECT * FROM parquet.`{src}`
            """,
        )
        cursor.execute(f"SELECT COUNT(*) FROM {fq_table}")
        n = cursor.fetchone()[0]
        counts[table] = n
        print(f"      -> {n:,} rows")

    print(f"\n==> Done. Target used: {catalog}.{schema}")
    print("\nRow count verification:")
    for table, n in counts.items():
        print(f"  {table:24s} {n:>8,}")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
