"""`bizops seed`: build a tenant's SQLite file from one RNG. Same tenant and seed, same rows.

Schemas come from the stores (data-access concern); rows come from the fixtures in this package
(experiment concern). The fixtures import nothing from the stores beyond the DDL constant."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from bizops.infrastructure.connectors.billing import store as billing_store
from bizops.infrastructure.connectors.crm import store as crm_store
from bizops.infrastructure.connectors.engineering import store as engineering_store
from bizops.infrastructure.connectors.support import store as support_store
from bizops.infrastructure.connectors.usage import store as usage_store
from bizops.infrastructure.db import sqlite as _sqlite
from bizops.infrastructure.seed import billing, crm, engineering, support, usage
from bizops.infrastructure.seed.world import USERS, World, build_world

PRINCIPALS_DDL = """
CREATE TABLE IF NOT EXISTS principals (
    user TEXT PRIMARY KEY, roles TEXT NOT NULL, token TEXT NOT NULL UNIQUE
);
"""
SCHEMAS = [
    PRINCIPALS_DDL,
    crm_store.DDL,
    billing_store.DDL,
    support_store.DDL,
    usage_store.DDL,
    engineering_store.DDL,
]
FIXTURES = [crm.seed, billing.seed, support.seed, usage.seed, engineering.seed]  # dependency order


def seed_tenant(data_dir: Path, tenant: str, seed: int = 42) -> World:
    for suffix in ("", "-wal", "-shm"):
        (data_dir / f"{tenant}.db{suffix}").unlink(missing_ok=True)
    w = build_world(tenant, seed)
    conn = _sqlite.connect(data_dir, tenant)
    try:
        for ddl in SCHEMAS:
            conn.executescript(ddl)
        conn.execute("BEGIN")
        for user, roles in USERS.items():
            token = hashlib.sha256(f"{tenant}:{user}:{seed}".encode()).hexdigest()[:24]
            conn.execute(
                "INSERT INTO principals VALUES (?,?,?)", (user, ",".join(sorted(roles)), f"bo_{token}")
            )
        for fixture in FIXTURES:
            fixture(conn, w)
        conn.execute("COMMIT")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    return w


def content_hash(data_dir: Path, tenant: str) -> str:
    """Hash of every row in every table, independent of file layout, so determinism is testable."""
    conn = sqlite3.connect(data_dir / f"{tenant}.db")
    try:
        h = hashlib.sha256()
        names = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        for (table,) in names.fetchall():
            h.update(table.encode())
            for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2"):  # noqa: S608
                h.update(repr(row).encode())
        return h.hexdigest()
    finally:
        conn.close()


__all__ = ["World", "content_hash", "seed_tenant"]
