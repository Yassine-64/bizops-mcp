"""Roles decide scopes. This mapping is the only place a scope is granted; the model never sees it."""

from __future__ import annotations

from bizops.domain.models import Principal

ROLE_SCOPES: dict[str, frozenset[str]] = {
    "sales": frozenset(
        {"crm.read", "crm.write", "billing.read", "support.read", "usage.read", "people.read"}
    ),
    "engineering": frozenset(
        {"engineering.read", "engineering.write", "support.read", "usage.read", "people.read"}
    ),
    "finance": frozenset(
        {
            "billing.read",
            "billing.refund",
            "billing.void",
            "crm.read",
            "usage.read",
            "support.read",
            "people.read",
            "hr.payroll.read",
        }
    ),
    "support": frozenset(
        {"support.read", "support.reply", "crm.read", "billing.read", "usage.read", "people.read"}
    ),
    "admin": frozenset({"*"}),
}


def principal_for(tenant: str, user: str, roles: set[str]) -> Principal:
    scopes: set[str] = set()
    for role in roles:
        scopes |= ROLE_SCOPES.get(role, frozenset())
    return Principal(tenant=tenant, user=user, roles=frozenset(roles), scopes=frozenset(scopes))


def has_scope(principal: Principal, scope: str) -> bool:
    return "*" in principal.scopes or scope in principal.scopes


__all__ = ["ROLE_SCOPES", "has_scope", "principal_for"]
