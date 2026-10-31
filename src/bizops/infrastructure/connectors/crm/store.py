"""CRM schema: accounts, contacts, deals. Data access functions are added with the connector."""

from __future__ import annotations

DDL = """
CREATE TABLE IF NOT EXISTS crm_accounts (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, segment TEXT NOT NULL, industry TEXT NOT NULL,
    owner TEXT NOT NULL, arr_cents INTEGER NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
    churned_at TEXT
);
CREATE TABLE IF NOT EXISTS crm_contacts (
    id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES crm_accounts(id),
    name TEXT NOT NULL, email TEXT NOT NULL, title TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS crm_deals (
    id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES crm_accounts(id), name TEXT NOT NULL,
    stage TEXT NOT NULL, amount_cents INTEGER NOT NULL, owner TEXT NOT NULL, updated_at TEXT NOT NULL,
    operation_id TEXT
);
"""
STAGES = ["Discovery", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]

__all__ = ["DDL", "STAGES"]
