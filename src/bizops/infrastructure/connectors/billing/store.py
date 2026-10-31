"""Billing schema, Stripe-shaped: customers, subscriptions, invoices, payments, refunds.
Refunds carry a unique operation_id: the connector's idempotency anchor."""

from __future__ import annotations

DDL = """
CREATE TABLE IF NOT EXISTS billing_customers (
    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, email TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS billing_subscriptions (
    id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES billing_customers(id), plan TEXT NOT NULL,
    mrr_cents INTEGER NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL, canceled_at TEXT,
    previous_mrr_cents INTEGER, changed_at TEXT
);
CREATE TABLE IF NOT EXISTS billing_invoices (
    id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES billing_customers(id),
    amount_cents INTEGER NOT NULL, issued_at TEXT NOT NULL, due_at TEXT NOT NULL, status TEXT NOT NULL,
    paid_at TEXT
);
CREATE TABLE IF NOT EXISTS billing_payments (
    id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL REFERENCES billing_invoices(id),
    amount_cents INTEGER NOT NULL, method TEXT NOT NULL, paid_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS billing_refunds (
    id TEXT PRIMARY KEY, payment_id TEXT NOT NULL REFERENCES billing_payments(id),
    amount_cents INTEGER NOT NULL, reason TEXT NOT NULL, operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
"""
PLANS = {"enterprise": "scale", "mid": "growth", "smb": "starter"}

__all__ = ["DDL", "PLANS"]
