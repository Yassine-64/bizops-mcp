"""Shared helpers for connectors: query shortcuts on the tenant store and the result-size cap.

Connectors are adapters: each wraps one system, speaks its schema, and raises the typed errors from
`bizops.domain.exceptions`. They never decide policy; the dispatcher has already done that."""

from __future__ import annotations

import sqlite3
from typing import Any

from bizops.domain.exceptions import InvalidArgument, NotFound
from bizops.domain.models.capability import CallContext

MAX_LIMIT = 50  # no capability returns more rows than this; there is no export_all


def conn(ctx: CallContext) -> sqlite3.Connection:
    store: sqlite3.Connection = ctx.store
    return store


def rows(ctx: CallContext, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn(ctx).execute(sql, params).fetchall()]


def one(ctx: CallContext, sql: str, params: tuple[Any, ...], what: str) -> dict[str, Any]:
    row = conn(ctx).execute(sql, params).fetchone()
    if row is None:
        raise NotFound(f"{what} not found")
    return dict(row)


def limit(n: int) -> int:
    if n < 1:
        raise InvalidArgument("limit must be at least 1")
    return min(n, MAX_LIMIT)


__all__ = ["MAX_LIMIT", "conn", "limit", "one", "rows"]
