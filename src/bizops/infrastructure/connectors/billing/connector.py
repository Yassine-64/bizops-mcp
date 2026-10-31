"""Billing capabilities over the Stripe-shaped store."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from bizops.application.catalogue import capability
from bizops.domain.exceptions import InvalidArgument
from bizops.domain.models import Risk
from bizops.domain.models.capability import CallContext
from bizops.infrastructure.connectors._base import conn, limit, one, rows

READ = {"billing.read"}


def _month_end(year: int, month: int) -> date:
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return nxt - timedelta(days=1)


class BillingConnector:
    @capability(Risk.READ, READ, output="list[MonthlyMRR]")
    async def mrr_by_month(self, ctx: CallContext, months: int = 6) -> list[dict[str, Any]]:
        """Monthly recurring revenue at each month end, oldest first, with the change from the month before.

        months: how many month ends to return, up to 24
        """
        months = max(1, min(months, 24))
        now = ctx.today
        out: list[dict[str, Any]] = []
        y, m = now.year, now.month
        ends: list[date] = []
        for _ in range(months):
            ends.append(_month_end(y, m))
            y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        for end in reversed(ends):
            d = end.isoformat()
            mrr = (
                conn(ctx)
                .execute(
                    "SELECT COALESCE(SUM(CASE WHEN changed_at IS NOT NULL AND changed_at > ? "
                    "THEN previous_mrr_cents ELSE mrr_cents END), 0) FROM billing_subscriptions "
                    "WHERE started_at <= ? AND (canceled_at IS NULL OR canceled_at > ?)",
                    (d, d, d),
                )
                .fetchone()[0]
            )
            prev = out[-1]["mrr_cents"] if out else None
            out.append(
                {
                    "month": end.strftime("%Y-%m"),
                    "mrr_cents": int(mrr),
                    "change_cents": None if prev is None else int(mrr) - prev,
                }
            )
        return out

    @capability(Risk.READ, READ, output="list[SubscriptionChange]")
    async def mrr_changes(self, ctx: CallContext, month: str) -> list[dict[str, Any]]:
        """Subscriptions that were canceled or changed price in one month, with the MRR effect of each.

        month: YYYY-MM
        """
        try:
            y, m = (int(x) for x in month.split("-"))
            start, end = date(y, m, 1).isoformat(), _month_end(y, m).isoformat()
        except ValueError as e:
            raise InvalidArgument("month must be YYYY-MM") from e
        return rows(
            ctx,
            "SELECT a.id AS account_id, a.name AS account, s.id AS subscription_id, "
            "CASE WHEN s.canceled_at BETWEEN ? AND ? THEN 'canceled' ELSE 'changed' END AS kind, "
            "COALESCE(s.canceled_at, s.changed_at) AS at, "
            "CASE WHEN s.canceled_at BETWEEN ? AND ? THEN -COALESCE(s.mrr_cents, 0) "
            "ELSE s.mrr_cents - s.previous_mrr_cents END AS mrr_effect_cents "
            "FROM billing_subscriptions s JOIN billing_customers c ON c.id = s.customer_id "
            "JOIN crm_accounts a ON a.id = c.account_id "
            "WHERE s.canceled_at BETWEEN ? AND ? OR s.changed_at BETWEEN ? AND ? ORDER BY at",
            (start, end, start, end, start, end, start, end),
        )

    @capability(Risk.READ, READ, name="subscription.get", output="Subscription")
    async def subscription_get(self, ctx: CallContext, account_id: str) -> dict[str, Any]:
        """The subscription of one account: plan, MRR, status, start and cancel dates.

        account_id: CRM account id, e.g. acc_012
        """
        return one(
            ctx,
            "SELECT s.* FROM billing_subscriptions s JOIN billing_customers c ON c.id = s.customer_id "
            "WHERE c.account_id = ?",
            (account_id,),
            f"subscription for {account_id}",
        )

    @capability(Risk.READ, READ, output="list[Invoice]")
    async def overdue_invoices(self, ctx: CallContext, segment: str | None = None, max_rows: int = 20) -> Any:
        """Invoices past their due date and unpaid, oldest due date first.

        segment: optional account segment filter: enterprise, mid or smb
        max_rows: maximum rows to return, up to 50
        """
        sql = (
            "SELECT i.id, i.amount_cents, i.issued_at, i.due_at, a.id AS account_id, a.name AS account, "
            "a.segment FROM billing_invoices i JOIN billing_customers c ON c.id = i.customer_id "
            "JOIN crm_accounts a ON a.id = c.account_id WHERE i.status = 'overdue'"
        )
        params: tuple[Any, ...] = ()
        if segment:
            sql, params = sql + " AND a.segment = ?", (segment,)
        return rows(ctx, sql + " ORDER BY i.due_at LIMIT ?", (*params, limit(max_rows)))

    @capability(Risk.READ, READ, name="invoices.list", output="list[Invoice]")
    async def invoices_list(
        self, ctx: CallContext, account_id: str, status: str | None = None, max_rows: int = 12
    ) -> list[dict[str, Any]]:
        """Invoices of one account, newest first.

        account_id: CRM account id
        status: optional filter: paid, open or overdue
        max_rows: maximum rows to return, up to 50
        """
        sql = (
            "SELECT i.* FROM billing_invoices i JOIN billing_customers c ON c.id = i.customer_id "
            "WHERE c.account_id = ?"
        )
        params: tuple[Any, ...] = (account_id,)
        if status:
            sql, params = sql + " AND i.status = ?", (*params, status)
        return rows(ctx, sql + " ORDER BY i.issued_at DESC LIMIT ?", (*params, limit(max_rows)))

    @capability(Risk.READ, READ, name="invoice.get", output="Invoice")
    async def invoice_get(self, ctx: CallContext, invoice_id: str) -> dict[str, Any]:
        """One invoice with its payments.

        invoice_id: e.g. in_0420
        """
        inv = one(ctx, "SELECT * FROM billing_invoices WHERE id = ?", (invoice_id,), f"invoice {invoice_id}")
        inv["payments"] = rows(ctx, "SELECT * FROM billing_payments WHERE invoice_id = ?", (invoice_id,))
        return inv

    @capability(Risk.READ, READ, name="payments.list", output="list[Payment]")
    async def payments_list(
        self, ctx: CallContext, account_id: str, max_rows: int = 12
    ) -> list[dict[str, Any]]:
        """Payments received from one account, newest first, with the invoice each one paid.

        account_id: CRM account id
        max_rows: maximum rows to return, up to 50
        """
        return rows(
            ctx,
            "SELECT p.*, i.status AS invoice_status FROM billing_payments p "
            "JOIN billing_invoices i ON i.id = p.invoice_id JOIN billing_customers c ON c.id = i.customer_id "
            "WHERE c.account_id = ? ORDER BY p.paid_at DESC LIMIT ?",
            (account_id, limit(max_rows)),
        )

    @capability(
        Risk.FINANCIAL,
        {"billing.read", "billing.refund"},
        idempotent=True,
        amount_field="amount_cents",
        output="Refund",
        identity=("payment_id", "amount_cents"),
    )
    async def refund_payment(
        self, ctx: CallContext, payment_id: str, amount_cents: int, reason: str
    ) -> dict[str, Any]:
        """Refund all or part of a payment. Idempotent on the server-minted operation id.

        payment_id: e.g. py_0228
        amount_cents: amount to refund in cents, at most the payment amount minus earlier refunds
        reason: short reason recorded on the refund
        """
        assert ctx.operation_id, "writes always carry an operation id"
        db = conn(ctx)
        existing = db.execute(
            "SELECT * FROM billing_refunds WHERE operation_id = ?", (ctx.operation_id,)
        ).fetchone()
        if existing:
            return {**dict(existing), "replayed": True}
        pay = one(ctx, "SELECT * FROM billing_payments WHERE id = ?", (payment_id,), f"payment {payment_id}")
        refunded = db.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM billing_refunds WHERE payment_id = ?", (payment_id,)
        ).fetchone()[0]
        if amount_cents <= 0 or amount_cents > pay["amount_cents"] - refunded:
            raise InvalidArgument(f"amount must be between 1 and {pay['amount_cents'] - refunded} cents")
        n = db.execute("SELECT COUNT(*) FROM billing_refunds").fetchone()[0] + 1
        refund = {
            "id": f"re_{n:04d}",
            "payment_id": payment_id,
            "amount_cents": amount_cents,
            "reason": reason,
            "operation_id": ctx.operation_id,
            "created_at": ctx.today.isoformat(),
        }
        db.execute(
            "INSERT INTO billing_refunds VALUES (:id, :payment_id, :amount_cents, :reason, "
            ":operation_id, :created_at)",
            refund,
        )
        return {**refund, "replayed": False}


__all__ = ["BillingConnector"]
