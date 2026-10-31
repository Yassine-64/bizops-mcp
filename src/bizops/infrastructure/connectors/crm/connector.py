"""CRM capabilities: accounts, contacts, deals."""

from __future__ import annotations

from typing import Any

from bizops.application.catalogue import capability
from bizops.domain.exceptions import InvalidArgument
from bizops.domain.models import Risk
from bizops.domain.models.capability import CallContext
from bizops.infrastructure.connectors._base import conn, limit, one, rows
from bizops.infrastructure.connectors.crm.store import STAGES

READ = {"crm.read"}


class CrmConnector:
    @capability(Risk.READ, READ, name="accounts.search", output="list[Account]")
    async def accounts_search(
        self,
        ctx: CallContext,
        query: str | None = None,
        segment: str | None = None,
        status: str | None = None,
        max_rows: int = 20,
    ) -> list[dict[str, Any]]:
        """Find accounts by name fragment, segment or status, largest ARR first.

        query: case-insensitive name fragment
        segment: enterprise, mid or smb
        status: active or churned
        max_rows: maximum rows to return, up to 50
        """
        where, params = ["1 = 1"], []
        if query:
            where.append("name LIKE ?")
            params.append(f"%{query}%")
        if segment:
            where.append("segment = ?")
            params.append(segment)
        if status:
            where.append("status = ?")
            params.append(status)
        return rows(
            ctx,
            f"SELECT id, name, segment, industry, owner, arr_cents, status FROM crm_accounts "  # noqa: S608
            f"WHERE {' AND '.join(where)} ORDER BY arr_cents DESC LIMIT ?",
            (*params, limit(max_rows)),
        )

    @capability(Risk.READ, READ, name="account.get", output="Account")
    async def account_get(self, ctx: CallContext, account_id: str) -> dict[str, Any]:
        """One account with its owner, ARR, status and open deals.

        account_id: e.g. acc_012
        """
        acc = one(ctx, "SELECT * FROM crm_accounts WHERE id = ?", (account_id,), f"account {account_id}")
        acc["deals"] = rows(
            ctx, "SELECT id, name, stage, amount_cents FROM crm_deals WHERE account_id = ?", (account_id,)
        )
        return acc

    @capability(Risk.READ, READ, name="contacts.list", output="list[Contact]")
    async def contacts_list(self, ctx: CallContext, account_id: str) -> list[dict[str, Any]]:
        """Contacts at one account: name, title, email.

        account_id: CRM account id
        """
        return rows(ctx, "SELECT * FROM crm_contacts WHERE account_id = ? ORDER BY name", (account_id,))

    @capability(Risk.READ, READ, name="deals.list", output="list[Deal]")
    async def deals_list(
        self, ctx: CallContext, stage: str | None = None, owner: str | None = None, max_rows: int = 20
    ) -> list[dict[str, Any]]:
        """Open and closed deals, most recently updated first.

        stage: Discovery, Proposal, Negotiation, Closed Won or Closed Lost
        owner: sales owner user name
        max_rows: maximum rows to return, up to 50
        """
        where, params = ["1 = 1"], []
        if stage:
            where.append("d.stage = ?")
            params.append(stage)
        if owner:
            where.append("d.owner = ?")
            params.append(owner)
        return rows(
            ctx,
            "SELECT d.*, a.name AS account FROM crm_deals d JOIN crm_accounts a ON a.id = d.account_id "  # noqa: S608
            f"WHERE {' AND '.join(where)} ORDER BY d.updated_at DESC LIMIT ?",
            (*params, limit(max_rows)),
        )

    @capability(
        Risk.WRITE, {"crm.read", "crm.write"}, name="deal.update_stage", idempotent=True, output="Deal"
    )
    async def deal_update_stage(self, ctx: CallContext, deal_id: str, stage: str) -> dict[str, Any]:
        """Move a deal to another pipeline stage.

        deal_id: e.g. deal_006
        stage: Discovery, Proposal, Negotiation, Closed Won or Closed Lost
        """
        if stage not in STAGES:
            raise InvalidArgument(f"stage must be one of {', '.join(STAGES)}")
        one(ctx, "SELECT id FROM crm_deals WHERE id = ?", (deal_id,), f"deal {deal_id}")
        conn(ctx).execute(
            "UPDATE crm_deals SET stage = ?, updated_at = ?, operation_id = ? WHERE id = ?",
            (stage, ctx.today.isoformat(), ctx.operation_id, deal_id),
        )
        return one(ctx, "SELECT * FROM crm_deals WHERE id = ?", (deal_id,), f"deal {deal_id}")


__all__ = ["CrmConnector"]
