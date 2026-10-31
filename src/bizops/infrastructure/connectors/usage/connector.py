"""Product usage capabilities."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from bizops.application.catalogue import capability
from bizops.domain.models import Risk
from bizops.domain.models.capability import CallContext
from bizops.infrastructure.connectors._base import conn, limit, rows

READ = {"usage.read"}


def _avg(ctx: CallContext, account_id: str, start_days_ago: int, end_days_ago: int) -> float:
    now = ctx.today
    value = (
        conn(ctx)
        .execute(
            "SELECT AVG(active_users) FROM usage_daily WHERE account_id = ? AND day > ? AND day <= ?",
            (
                account_id,
                (now - timedelta(days=start_days_ago)).isoformat(),
                (now - timedelta(days=end_days_ago)).isoformat(),
            ),
        )
        .fetchone()[0]
    )
    return float(value or 0.0)


class UsageConnector:
    @capability(Risk.READ, READ, output="list[WeeklyUsage]")
    async def trend(self, ctx: CallContext, account_id: str, weeks: int = 12) -> list[dict[str, Any]]:
        """Weekly average active users and API calls for one account, oldest week first.

        account_id: CRM account id
        weeks: how many weeks, up to 16
        """
        weeks = max(1, min(weeks, 16))
        start = ctx.today - timedelta(days=7 * weeks)
        return rows(
            ctx,
            "SELECT MIN(day) AS week_of, ROUND(AVG(active_users), 1) AS active_users, "
            "ROUND(AVG(api_calls)) AS api_calls FROM usage_daily WHERE account_id = ? AND day > ? "
            "GROUP BY strftime('%Y-%W', day) ORDER BY week_of",
            (account_id, start.isoformat()),
        )

    @capability(Risk.READ, READ, output="list[UsageChange]")
    async def declining_accounts(
        self, ctx: CallContext, min_drop_pct: float = 30.0, max_rows: int = 20
    ) -> Any:
        """Active accounts whose last 4 weeks of active users fell versus the 4 weeks ending 8 weeks ago.

        min_drop_pct: smallest decline to report, in percent
        max_rows: maximum rows to return, up to 50
        """
        out = []
        ids = (
            conn(ctx).execute("SELECT id, name, segment FROM crm_accounts WHERE status = 'active'").fetchall()
        )
        for account_id, name, segment in ids:
            base, recent = _avg(ctx, account_id, 84, 56), _avg(ctx, account_id, 28, 0)
            if base <= 0:
                continue
            change = round(100.0 * (recent - base) / base, 1)
            if change <= -min_drop_pct:
                out.append(
                    {
                        "account_id": account_id,
                        "account": name,
                        "segment": segment,
                        "usage_change_pct": change,
                    }
                )
        out.sort(key=lambda r: r["usage_change_pct"])
        return out[: limit(max_rows)]


__all__ = ["UsageConnector"]
