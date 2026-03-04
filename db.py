"""Read-only SQLite helpers for querying the fitness dashboard database."""

import os
import sqlite3
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", "/app/data/fitness.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def query_one(sql: str, params: tuple = ()) -> dict | None:
    """Execute SQL and return a single row as dict, or None."""
    try:
        conn = _get_conn()
        row = conn.execute(sql, params).fetchone()
        conn.close()
        if row is None:
            return None
        return dict(row)
    except Exception as e:
        logger.warning(f"DB query_one failed: {e}")
        return None


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    """Execute SQL and return all rows as list of dicts."""
    try:
        conn = _get_conn()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"DB query_all failed: {e}")
        return []
