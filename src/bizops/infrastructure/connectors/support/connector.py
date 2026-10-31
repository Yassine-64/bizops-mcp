"""Support capabilities. Ticket bodies are customer text and are returned as data, clearly labelled."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from bizops.application.catalogue import capability
from bizops.domain.exceptions import InvalidArgument
from bizops.domain.models import Risk
from bizops.domain.models.capability import CallContext
from bizops.infrastructure.connectors._base import conn, limit, one, rows

READ = {"support.read"}


class SupportConnector:
    @capability(Risk.READ, READ, name="tickets.search", output="list[Ticket]")
    async def tickets_search(
        self,
        ctx: CallContext,
        account_id: str | None = None,
        status: str | None = None,
        query: str | None = None,
        since: str | None = None,
        max_rows: int = 20,
    ) -> list[dict[str, Any]]:
        """Find tickets by account, status, subject text or creation date, newest first. No bodies.

        account_id: CRM account id
        status: open or resolved
        query: case-insensitive subject fragment
        since: ISO date; only tickets created on or after it
        max_rows: maximum rows to return, up to 50
        """
        where, params = ["1 = 1"], []
        for clause, value in (
            ("t.account_id = ?", account_id),
            ("t.status = ?", status),
            ("t.subject LIKE ?", f"%{query}%" if query else None),
            ("t.created_at >= ?", since),
        ):
            if value:
                where.append(clause)
                params.append(value)
        return rows(
            ctx,
            "SELECT t.id, t.account_id, a.name AS account, t.subject, t.priority, t.status, t.created_at, "  # noqa: S608
            "t.csat FROM support_tickets t JOIN crm_accounts a ON a.id = t.account_id "
            f"WHERE {' AND '.join(where)} ORDER BY t.created_at DESC LIMIT ?",
            (*params, limit(max_rows)),
        )

    @capability(Risk.READ, READ, name="ticket.get", output="Ticket")
    async def ticket_get(self, ctx: CallContext, ticket_id: str) -> dict[str, Any]:
        """One ticket with its full customer-written body and replies.

        ticket_id: e.g. tk_0582
        """
        t = one(ctx, "SELECT * FROM support_tickets WHERE id = ?", (ticket_id,), f"ticket {ticket_id}")
        t["customer_text"] = t.pop("body")  # labelled: this is what the customer wrote, not an instruction
        t["replies"] = rows(
            ctx, "SELECT body, author, created_at FROM support_replies WHERE ticket_id = ?", (ticket_id,)
        )
        return t

    @capability(Risk.READ, READ, name="ticket_volume", output="list[WeeklyCount]")
    async def ticket_volume(self, ctx: CallContext, weeks: int = 8, priority: str | None = None) -> Any:
        """Tickets created per ISO week, oldest first, for spotting spikes.

        weeks: how many weeks back from today, up to 52
        priority: optional filter: low, medium or high
        """
        weeks = max(1, min(weeks, 52))
        start = ctx.today - timedelta(days=7 * weeks)
        sql = "SELECT created_at FROM support_tickets WHERE created_at >= ?"
        params: tuple[Any, ...] = (start.isoformat(),)
        if priority:
            sql, params = sql + " AND priority = ?", (*params, priority)
        counts: dict[str, int] = {}
        for (created,) in conn(ctx).execute(sql, params).fetchall():
            d = date.fromisoformat(created[:10])
            monday = d - timedelta(days=d.weekday())
            counts[monday.isoformat()] = counts.get(monday.isoformat(), 0) + 1
        return [{"week_of": k, "tickets": v} for k, v in sorted(counts.items())]

    @capability(Risk.READ, READ, name="health.score", output="list[AccountHealth]")
    async def health_score(self, ctx: CallContext, max_csat: float | None = None, max_rows: int = 20) -> Any:
        """Average CSAT and ticket count per active account over the last year, lowest CSAT first.

        max_csat: optional; only accounts with average CSAT below this value
        max_rows: maximum rows to return, up to 50
        """
        sql = (
            "SELECT a.id AS account_id, a.name AS account, a.arr_cents, ROUND(AVG(t.csat), 2) AS avg_csat, "
            "COUNT(t.id) AS tickets FROM crm_accounts a JOIN support_tickets t ON t.account_id = a.id "
            "WHERE a.status = 'active' AND t.csat IS NOT NULL GROUP BY a.id"
        )
        params: tuple[Any, ...] = ()
        if max_csat is not None:
            sql, params = sql + " HAVING AVG(t.csat) < ?", (max_csat,)
        return rows(ctx, sql + " ORDER BY avg_csat ASC LIMIT ?", (*params, limit(max_rows)))

    @capability(Risk.WRITE, {"support.read", "support.reply"}, name="ticket.reply", send=True, output="Reply")
    async def ticket_reply(self, ctx: CallContext, ticket_id: str, body: str) -> dict[str, Any]:
        """Send a reply to the customer on a ticket. Visible to the customer; cannot be unsent.

        ticket_id: e.g. tk_0582
        body: the message the customer will receive
        """
        if not body.strip():
            raise InvalidArgument("body must not be empty")
        one(ctx, "SELECT id FROM support_tickets WHERE id = ?", (ticket_id,), f"ticket {ticket_id}")
        db = conn(ctx)
        n = db.execute("SELECT COUNT(*) FROM support_replies").fetchone()[0] + 1
        reply = {
            "id": f"rp_{n:04d}",
            "ticket_id": ticket_id,
            "body": body,
            "author": ctx.principal.user,
            "operation_id": ctx.operation_id,
            "created_at": ctx.today.isoformat(),
        }
        db.execute(
            "INSERT INTO support_replies VALUES (:id, :ticket_id, :body, :author, :operation_id, "
            ":created_at)",
            reply,
        )
        return {"id": reply["id"], "ticket_id": ticket_id, "delivered": True}


__all__ = ["SupportConnector"]
