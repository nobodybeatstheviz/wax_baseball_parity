#!/usr/bin/env python3
"""
Applies the Keeping Score parity metric views to Databricks Unity Catalog.

Creates schema wax_baseball.semantics (kept separate from wax_baseball.parity,
which holds the ported corpus and is never modified), then runs each
CREATE OR REPLACE VIEW ... WITH METRICS statement in databricks/metric_views/.

Idempotent: reruns safely any time a .sql file here changes.

Usage:
    python databricks/apply_metric_views.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
from _dbx_conn import get_connection  # noqa: E402

VIEWS_DIR = pathlib.Path(__file__).resolve().parent / "metric_views"

# Applied in a fixed order (one file per fact family; no cross-view dependencies).
VIEW_FILES = [
    "mv_attended_games.sql",
    "mv_plays.sql",
    "mv_attended_team_games.sql",
    "mv_game_attendee.sql",
    "mv_hof_sightings.sql",
]


def main() -> None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("CREATE SCHEMA IF NOT EXISTS wax_baseball.semantics")
    print("Ensured schema wax_baseball.semantics")

    for fname in VIEW_FILES:
        path = VIEWS_DIR / fname
        sql = path.read_text(encoding="utf-8")
        cursor.execute(sql)
        print(f"Applied {fname}")

    cursor.close()
    conn.close()
    print(f"\nApplied {len(VIEW_FILES)} metric views to wax_baseball.semantics")


if __name__ == "__main__":
    main()
