"""Support schema: tickets and replies. Ticket bodies are untrusted text from customers."""

from __future__ import annotations

DDL = """
CREATE TABLE IF NOT EXISTS support_tickets (
    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
    priority TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, resolved_at TEXT, csat INTEGER
);
CREATE TABLE IF NOT EXISTS support_replies (
    id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL REFERENCES support_tickets(id), body TEXT NOT NULL,
    author TEXT NOT NULL, operation_id TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL
);
"""

__all__ = ["DDL"]
