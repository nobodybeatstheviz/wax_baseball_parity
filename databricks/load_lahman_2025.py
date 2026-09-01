#!/usr/bin/env python3
"""
Refreshes the Databricks `lahman_baseball.baseball_data` catalog/schema
in place from the pinned SABR 2025 Lahman CSV vintage.

Ruling (Wax, 2026-08-31): SABR 2025 is canonical for Keeping Score parity.
BigQuery and Snowflake already carry this vintage; Databricks held an older
cut (e.g. people 24,023 vs canonical 24,270) and this script brings it
current.

Source: wax-system/wax-baseball/lahman-2025/lahman_1871-2025_csv/ (27 CSVs),
content-pinned by the sibling MANIFEST.sha256 — verify separately with
`sha256sum -c` before running this (wax-system is read-only to this script;
it only reads the CSVs, never writes there).

Target: lahman_baseball.baseball_data — the 27 tables already there use
lowercase CSV-stem names (People.csv -> people, HallOfFame.csv ->
halloffame, ...). This script matches those names exactly; if a CSV shows
up with no existing counterpart it still loads, under the same
lowercase-stem convention, and is called out in the summary.

Idempotent: REMOVE + PUT per file (no OVERWRITE keyword on PUT), then
CREATE OR REPLACE TABLE ... AS SELECT per CSV. Safe to rerun any time the
pinned CSVs change.

Usage:
    python databricks/load_lahman_2025.py

Requires:
    databricks-sql-connector, databricks-sdk
    ~/.databrickscfg profile 'wax_baseball' (host + token; never hardcoded
    here — see scripts/_dbx_conn.py)
"""

from __future__ import annotations

import pathlib
import sys

from databricks.sdk.core import Config
from databricks import sql as dbsql

# Reuse the same profile/warehouse as the shared helper (scripts/_dbx_conn.py)
# without editing it — that helper's staging_allowed_local_path is scoped to
# wax_baseball_parity/data, and this loader needs to PUT from wax-system's
# Lahman CSV directory instead.
HTTP_PATH = "/sql/1.0/warehouses/873a5fb5d84620c1"
PROFILE = "wax_baseball"

SOURCE_DIR = pathlib.Path(
    r"C:\Users\georg\wax-system\wax-baseball\lahman-2025\lahman_1871-2025_csv"
)

CATALOG = "lahman_baseball"
SCHEMA = "baseball_data"
VOLUME_NAME = "lahman_files"

# Config list of CSVs -> target table name. table = lowercase CSV stem,
# matching the existing table names in lahman_baseball.baseball_data
# (verified via SHOW TABLES before writing this list — all 27 already existed
# under exactly this naming convention; none needed a new name).
CSVS: list[str] = [
    "AllstarFull.csv",
    "Appearances.csv",
    "AwardsManagers.csv",
    "AwardsPlayers.csv",
    "AwardsShareManagers.csv",
    "AwardsSharePlayers.csv",
    "Batting.csv",
    "BattingPost.csv",
    "CollegePlaying.csv",
    "Fielding.csv",
    "FieldingOF.csv",
    "FieldingOFsplit.csv",
    "FieldingPost.csv",
    "HallOfFame.csv",
    "HomeGames.csv",
    "Managers.csv",
    "ManagersHalf.csv",
    "Parks.csv",
    "People.csv",
    "Pitching.csv",
    "PitchingPost.csv",
    "Salaries.csv",
    "Schools.csv",
    "SeriesPost.csv",
    "Teams.csv",
    "TeamsFranchises.csv",
    "TeamsHalf.csv",
]

# Canonical cross-checks (Snowflake/BigQuery), per the ruling.
CANONICAL_COUNTS = {
    "people": 24_270,
    "batting": 128_598,
    "pitching": 57_630,
}


def get_connection():
    """Same profile/warehouse as scripts/_dbx_conn.py, but with staging
    access extended to the wax-system Lahman CSV directory (source of truth
    for this refresh) instead of wax_baseball_parity/data."""
    cfg = Config(profile=PROFILE)
    return dbsql.connect(
        server_hostname=cfg.host.replace("https://", "").rstrip("/"),
        http_path=HTTP_PATH,
        credentials_provider=lambda: cfg.authenticate,
        staging_allowed_local_path=[str(SOURCE_DIR)],
    )


def _exec(cursor, sql: str, quiet: bool = False) -> None:
    if not quiet:
        print(f"    SQL> {sql.strip().splitlines()[0][:100]}")
    cursor.execute(sql)


def main() -> None:
    if not SOURCE_DIR.is_dir():
        print(f"Source dir not found: {SOURCE_DIR}", file=sys.stderr)
        sys.exit(1)

    missing = [c for c in CSVS if not (SOURCE_DIR / c).is_file()]
    if missing:
        print(f"Missing CSVs in {SOURCE_DIR}: {missing}", file=sys.stderr)
        sys.exit(1)

    conn = get_connection()
    cursor = conn.cursor()

    print(f"==> 1. Ensure target schema {CATALOG}.{SCHEMA} exists")
    _exec(cursor, f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

    print("\n==> 2. Snapshot existing tables (for new-vs-existing report)")
    cursor.execute(f"SHOW TABLES IN {CATALOG}.{SCHEMA}")
    existing_tables = {row[1] for row in cursor.fetchall()}
    print(f"  {len(existing_tables)} existing tables found")

    volume_path = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME_NAME}"
    print(f"\n==> 3. Create volume {CATALOG}.{SCHEMA}.{VOLUME_NAME}")
    _exec(cursor, f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.{VOLUME_NAME}")

    print(f"\n==> 4. Upload {len(CSVS)} CSVs to {volume_path}")
    for csv_name in CSVS:
        local_path = SOURCE_DIR / csv_name
        dest = f"{volume_path}/{csv_name}"
        print(f"    PUT {csv_name} -> {dest}")
        # Idempotent re-run: PUT has no OVERWRITE keyword in Databricks SQL,
        # so remove any existing file at this path first.
        try:
            _exec(cursor, f"REMOVE '{dest}'", quiet=True)
        except Exception:
            pass  # file didn't exist yet - fine
        # NOTE: local path MUST use forward slashes (pathlib.as_posix()) -
        # the server-side SQL parser treats backslashes as string escapes,
        # so a Windows path like C:\Users\... arrives mangled and fails the
        # staging_allowed_local_path check.
        _exec(cursor, f"PUT '{local_path.as_posix()}' INTO '{dest}'", quiet=True)

    print("\n==> 5. CREATE OR REPLACE TABLE ... AS SELECT per CSV (read_files)")
    counts: dict[str, int] = {}
    new_tables: list[str] = []
    for csv_name in CSVS:
        table = pathlib.Path(csv_name).stem.lower()
        src = f"{volume_path}/{csv_name}"
        fq_table = f"{CATALOG}.{SCHEMA}.{table}"
        if table not in existing_tables:
            new_tables.append(table)
        print(f"    {fq_table}{'  [NEW]' if table not in existing_tables else ''}")
        _exec(
            cursor,
            f"""
            CREATE OR REPLACE TABLE {fq_table}
            AS SELECT * FROM read_files(
                '{src}',
                format => 'csv',
                header => true
            )
            """,
        )
        cursor.execute(f"SELECT COUNT(*) FROM {fq_table}")
        n = cursor.fetchone()[0]
        counts[table] = n
        print(f"      -> {n:,} rows")

    print(f"\n==> Done. Refreshed {len(CSVS)} tables in {CATALOG}.{SCHEMA}")
    if new_tables:
        print(f"  New tables (no prior counterpart): {new_tables}")
    else:
        print("  No new tables - every CSV matched an existing table name.")

    print("\nFull row-count table:")
    for table in sorted(counts):
        print(f"  {table:24s} {counts[table]:>10,}")

    print("\nCanonical cross-checks (Snowflake/BigQuery):")
    all_match = True
    for table, expected in CANONICAL_COUNTS.items():
        actual = counts.get(table)
        status = "OK" if actual == expected else "MISMATCH"
        if actual != expected:
            all_match = False
        print(f"  {table:10s} expected {expected:>10,}  actual {actual:>10,}  [{status}]")

    if not all_match:
        print("\nWARNING: one or more canonical cross-checks did not match.", file=sys.stderr)

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
