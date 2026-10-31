"""Engineering schema, Linear-shaped: projects, issues, incidents."""

from __future__ import annotations

DDL = """
CREATE TABLE IF NOT EXISTS eng_projects (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, owner TEXT NOT NULL, due_at TEXT NOT NULL, status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eng_issues (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES eng_projects(id), title TEXT NOT NULL,
    priority TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, closed_at TEXT, operation_id TEXT
);
CREATE TABLE IF NOT EXISTS eng_incidents (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, severity TEXT NOT NULL, started_at TEXT NOT NULL,
    resolved_at TEXT NOT NULL, affected TEXT NOT NULL, root_cause TEXT NOT NULL
);
"""

__all__ = ["DDL"]
