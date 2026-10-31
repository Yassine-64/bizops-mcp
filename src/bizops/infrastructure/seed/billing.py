"""Billing fixture: a subscription per account, monthly invoices with realistic payment delays, and the
storylines: the at-risk account leaves its last two invoices overdue, the downgraded account halves its
MRR after the outage, and one account's wire payment never reconciled (invoice open, payment present)."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from bizops.infrastructure.connectors.billing.store import PLANS
from bizops.infrastructure.seed.world import MONTHS, World


def _next_month(d: date) -> date:
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


def seed(conn: sqlite3.Connection, w: World) -> None:
    rng = w.rng
    inv_n = pay_n = 0
    for a in w.accounts:
        cust = f"cus_{a.id[4:]}"
        domain = a.name.split()[0].lower().replace(" ", "")
        conn.execute(
            "INSERT INTO billing_customers VALUES (?,?,?)", (cust, a.id, f"billing@{domain}.example")
        )
        mrr = a.arr_cents // 12 // 100 * 100
        prev_mrr, changed = None, None
        if a.downgraded:
            prev_mrr, changed = mrr, a.downgraded.isoformat()
            mrr = mrr // 2 // 100 * 100
        conn.execute(
            "INSERT INTO billing_subscriptions VALUES (?,?,?,?,?,?,?,?,?)",
            (
                f"sub_{a.id[4:]}",
                cust,
                PLANS[a.segment],
                mrr,
                "canceled" if a.churned else "active",
                a.created.isoformat(),
                a.churned.isoformat() if a.churned else None,
                prev_mrr,
                changed,
            ),
        )
        first = max(a.created, w.month_start(MONTHS - 1))
        month = date(first.year, first.month, 1)
        while month <= w.now and (a.churned is None or month <= a.churned):
            inv_n += 1
            inv = f"in_{inv_n:04d}"
            amount = (prev_mrr or mrr) if (a.downgraded and month < a.downgraded) else mrr
            due = month + timedelta(days=30)
            paid_at: date | None = month + timedelta(
                days=rng.randrange(1, 28) + rng.choice([0, 0, 0, 0, 2, 5, 12])
            )
            status = "paid"
            if paid_at and paid_at > w.now:
                paid_at, status = None, "open"
            if a.at_risk and month >= w.month_start(3):  # three unpaid months: two overdue, one still open
                paid_at, status = None, "overdue" if due <= w.now else "open"
            wire = a.paid_by_wire_mismatch and month == w.month_start(2)
            if wire:
                paid_at, status = None, "open"
            conn.execute(
                "INSERT INTO billing_invoices VALUES (?,?,?,?,?,?,?)",
                (
                    inv,
                    cust,
                    amount,
                    month.isoformat(),
                    due.isoformat(),
                    status,
                    paid_at.isoformat() if paid_at else None,
                ),
            )
            if paid_at or wire:
                pay_n += 1
                when = paid_at or (month + timedelta(days=9))
                conn.execute(
                    "INSERT INTO billing_payments VALUES (?,?,?,?,?)",
                    (f"py_{pay_n:04d}", inv, amount, "wire" if wire else "card", when.isoformat()),
                )
            month = _next_month(month)


__all__ = ["seed"]
