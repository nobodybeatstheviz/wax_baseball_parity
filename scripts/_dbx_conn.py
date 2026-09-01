"""Shared Databricks SQL connection helper.

Reads host/token from ~/.databrickscfg profile 'wax_baseball' via the
Databricks SDK's config resolution — never hardcode credentials here.
"""

from __future__ import annotations

import pathlib

from databricks.sdk.core import Config
from databricks import sql as dbsql

HTTP_PATH = "/sql/1.0/warehouses/873a5fb5d84620c1"
PROFILE = "wax_baseball"

# Parquet files live under wax_baseball_parity/data — must be declared here
# for PUT (volume staging) to be allowed to read from it.
DATA_DIR = str(pathlib.Path(__file__).resolve().parent.parent / "data")


def get_connection():
    cfg = Config(profile=PROFILE)
    return dbsql.connect(
        server_hostname=cfg.host.replace("https://", "").rstrip("/"),
        http_path=HTTP_PATH,
        credentials_provider=lambda: cfg.authenticate,
        staging_allowed_local_path=[DATA_DIR],
    )
