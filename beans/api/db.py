"""Small DuckDB helpers for the API layer.

DuckDB's pandas path (`fetchdf`) turns LIST columns into numpy arrays, which break `isinstance(x, list)`
checks and JSON serialisation. Everything here goes through `fetchall()` so routes get plain Python types.
"""
import datetime
import decimal
import hashlib
import json
import threading
from contextlib import contextmanager
from typing import Any, Iterable, Optional

from beans.store.duck import DuckStore

JSON_COLUMNS = {"payload", "shap_top_features", "engine_scores", "evidence", "details", "recommended_action", "destinations",
                "io", "annex", "timestamp_token", "forecast"}

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


_audit_lock = threading.Lock()
AUDIT_GENESIS = "0" * 64


def _audit_hash(prev: str, row_id: int, created_at: str, action: str, investigator: str, entity_type: str,
                entity_id: str, details: str) -> str:
    """SHA-256 over the previous row's hash and this row's fields: editing or deleting any row breaks the chain."""
    msg = json.dumps([prev, row_id, created_at, action, investigator, entity_type, entity_id, details],
                     separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(msg.encode()).hexdigest()


def audit(action: str, entity_type: str, entity_id: str, details: Optional[dict] = None,
          investigator: Optional[str] = None) -> None:
    if investigator is None:   # the logged-in user ("local" in single-user mode)
        from beans.api.auth import current_user
        investigator = current_user()["username"]
    details_json = json.dumps(details or {}, sort_keys=True, default=str)
    created = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)
    with _audit_lock, connection() as conn:
        last = conn.execute("SELECT id, row_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        row_id = (last[0] if last else 0) + 1
        prev = (last[1] if last and last[1] else AUDIT_GENESIS)
        h = _audit_hash(prev, row_id, created.isoformat(sep=" "), action, investigator, entity_type,
                        str(entity_id), details_json)
        conn.execute("INSERT INTO audit_log (id, action, investigator, entity_type, entity_id, details, created_at, "
                     "prev_hash, row_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     [row_id, action, investigator, entity_type, str(entity_id), details_json, created, prev, h])


def verify_audit_chain() -> dict:
    """Recomputes every row's hash. Rows written before the chain existed (no row_hash) are counted, not checked."""
    rows = query("SELECT id, created_at, action, investigator, entity_type, entity_id, CAST(details AS VARCHAR) AS d, "
                 "prev_hash, row_hash FROM audit_log ORDER BY id")
    prev, checked, legacy = None, 0, 0
    for r in rows:
        if not r["row_hash"]:
            legacy += 1
            continue
        expected_prev = prev if prev is not None else r["prev_hash"]   # the first chained row links to what came before
        h = _audit_hash(r["prev_hash"], r["id"], r["created_at"], r["action"], r["investigator"], r["entity_type"],
                        r["entity_id"], r["d"])
        if r["prev_hash"] != expected_prev or h != r["row_hash"]:
            return {"intact": False, "rows": len(rows), "checked": checked, "legacy_unchained": legacy,
                    "first_bad_id": r["id"], "reason": "row edited" if h != r["row_hash"] else "row missing before this one"}
        prev, checked = r["row_hash"], checked + 1
    return {"intact": True, "rows": len(rows), "checked": checked, "legacy_unchained": legacy, "head": prev}
