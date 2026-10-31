"""Server-side authorization for one capability call. Pure, deterministic, and the only place an action is
allowed, paused for a human, or refused. Order matters: scope before risk, so a user without the scope is
denied outright instead of being offered an approval they could never get."""

from __future__ import annotations

from typing import Any

from bizops.domain.models import Principal, Risk
from bizops.domain.models.capability import Capability, Decision, Effect, PolicyGates
from bizops.domain.services.roles import has_scope


def decide(principal: Principal, cap: Capability, args: dict[str, Any], gates: PolicyGates) -> Decision:
    for scope in sorted(cap.scopes):
        if not has_scope(principal, scope):
            return Decision(Effect.DENY, f"{principal.id} lacks scope {scope}", "scope")
    if not gates.approvals:
        return Decision(Effect.ALLOW, "scopes satisfied; approvals disabled", "scopes-only")
    if cap.send:
        return Decision(Effect.APPROVE, "externally visible message", "send")
    if cap.risk in (Risk.DESTRUCTIVE, Risk.ADMIN):
        return Decision(Effect.APPROVE, f"{cap.risk} action", f"risk:{cap.risk}")
    if cap.risk is Risk.FINANCIAL:
        amount = args.get(cap.amount_field or "amount_cents")
        if not isinstance(amount, int | float):
            return Decision(Effect.APPROVE, "financial action with no checkable amount", "risk:financial")
        if amount > gates.financial_threshold_cents:
            return Decision(
                Effect.APPROVE,
                f"{amount / 100:,.2f} exceeds the {gates.financial_threshold_cents / 100:,.0f} threshold",
                "risk:financial",
            )
        return Decision(Effect.ALLOW, "financial action under threshold", "risk:financial")
    return Decision(Effect.ALLOW, "scopes satisfied", f"risk:{cap.risk}")


def unknown(name: str) -> Decision:
    return Decision(Effect.DENY, f"no capability named {name}", "unknown")


__all__ = ["decide", "unknown"]
