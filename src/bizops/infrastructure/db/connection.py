"""One SQLite file per tenant. Isolation is physical: a tenant's connection cannot see another tenant's rows,
so a cross-tenant id does not resolve rather than being filtered out."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(data_dir: Path, tenant: str) -> sqlite3.Connection:
    path = data_dir / f"{tenant}.db"
    conn: sqlite3.Connection = sqlite3.connect(
        path, isolation_level=None
    )  # autocommit; writers use explicit BEGIN
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def rows(conn: sqlite3.Connection, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def one(conn: sqlite3.Connection, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None


__all__ = ["connect", "one", "rows"]
