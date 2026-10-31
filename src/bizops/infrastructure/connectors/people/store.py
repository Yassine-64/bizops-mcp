"""People schema: employees and departments are the company directory; salaries are payroll data behind
their own scope."""

from __future__ import annotations

DDL = """
CREATE TABLE IF NOT EXISTS people_employees (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, user TEXT, department TEXT NOT NULL, title TEXT NOT NULL,
    manager_id TEXT, started_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS people_salaries (
    employee_id TEXT PRIMARY KEY REFERENCES people_employees(id), base_cents INTEGER NOT NULL,
    currency TEXT NOT NULL
);
"""
DEPARTMENTS = ["Engineering", "Sales", "Support", "Finance", "Marketing", "Product", "People Ops"]

__all__ = ["DDL", "DEPARTMENTS"]
