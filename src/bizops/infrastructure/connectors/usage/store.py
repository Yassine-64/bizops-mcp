"""Product usage schema: one row per account per day."""

from __future__ import annotations

DDL = """
CREATE TABLE IF NOT EXISTS usage_daily (
    account_id TEXT NOT NULL, day TEXT NOT NULL, active_users INTEGER NOT NULL, api_calls INTEGER NOT NULL,
    PRIMARY KEY (account_id, day)
);
"""

__all__ = ["DDL"]
