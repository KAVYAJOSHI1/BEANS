"""Small DuckDB helpers for the API layer.

DuckDB's pandas path (`fetchdf`) turns LIST columns into numpy arrays, which break `isinstance(x, list)`
checks and JSON serialisation. Everything here goes through `fetchall()` so routes get plain Python types.
"""
import datetime
import decimal
import json
from contextlib import contextmanager
from typing import Any, Iterable, Optional

from beans.store.duck import DuckStore

JSON_COLUMNS = {"shap_top_features", "engine_scores", "evidence", "details", "recommended_action", "destinations",
                "io", "annex", "timestamp_token"}

_API_DDL = """
CREATE TABLE IF NOT EXISTS ingest_log (
    file VARCHAR, sha256 VARCHAR, size_bytes BIGINT, records BIGINT, source VARCHAR,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""
_ddl_done: set = set()   # database paths that already have the API tables


def _clean(v: Any) -> Any:
    if isinstance(v, datetime.datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, (datetime.date, datetime.time)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    return v


@contextmanager
def connection():
    store = DuckStore()
    conn = store.get_connection()
    try:
        if store.db_path not in _ddl_done:
            conn.execute(_API_DDL)
            _ddl_done.add(store.db_path)
        yield conn
    finally:
        conn.close()


def query(sql: str, params: Optional[Iterable] = None) -> list[dict]:
    with connection() as conn:
        cur = conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        rows = []
        for raw in cur.fetchall():
            row = {}
            for col, val in zip(cols, raw):
                if col in JSON_COLUMNS and isinstance(val, str):
                    try:
                        val = json.loads(val)
                    except ValueError:
                        pass
                row[col] = _clean(val)
            rows.append(row)
        return rows


def one(sql: str, params: Optional[Iterable] = None) -> Optional[dict]:
    rows = query(sql, params)
    return rows[0] if rows else None


def scalar(sql: str, params: Optional[Iterable] = None) -> Any:
    with connection() as conn:
        row = conn.execute(sql, list(params or [])).fetchone()
        return _clean(row[0]) if row else None


def execute(sql: str, params: Optional[Iterable] = None) -> None:
    with connection() as conn:
        conn.execute(sql, list(params or []))


def table_exists(name: str) -> bool:
    return bool(scalar("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [name]))


def audit(action: str, entity_type: str, entity_id: str, details: Optional[dict] = None,
          investigator: Optional[str] = None) -> None:
    if investigator is None:   # the logged-in user ("local" in single-user mode)
        from beans.api.auth import current_user
        investigator = current_user()["username"]
    execute(
        "INSERT INTO audit_log (id, action, investigator, entity_type, entity_id, details) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM audit_log), ?, ?, ?, ?, ?)",
        [action, investigator, entity_type, entity_id, json.dumps(details or {})],
    )
