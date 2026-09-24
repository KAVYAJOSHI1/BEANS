"""DuckDB access. SHARED FILE.

DuckDB allows one read-write process per file. Don't run `beans ingest/score` while `beans serve`
holds the DB. Stop the server, or trigger the pipeline through the API (it runs in-process).
"""
from pathlib import Path

import duckdb

from beans import config

DDL_PATH = Path(__file__).with_name("ddl.sql")


def connect(path: str | Path | None = None, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    path = str(path or config.DB_PATH)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(path, read_only=read_only)
    if not read_only:
        con.execute(DDL_PATH.read_text())
    return con


def reset(con: duckdb.DuckDBPyConnection, tables: list[str]) -> None:
    for t in tables:
        con.execute(f"DELETE FROM {t}")


DATA_TABLES = ["ingest_log", "quarantine", "net_obs", "tx", "tx_input", "tx_output", "wallet", "ip",
               "tx_first_spy", "wallet_ip", "flow_edge", "seeds", "labels_address", "labels_tx"]
SCORE_TABLES = ["cluster", "cluster_suggest", "tx_scores", "wallet_scores", "alert", "model_card"]
