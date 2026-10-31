from __future__ import annotations

import pytest

from bizops.domain.models import Risk
from bizops.domain.models.capability import Capability, Effect, Parameter, PolicyGates
from bizops.domain.services import policy
from bizops.domain.services.roles import principal_for

REFUND = Capability(
    name="billing.refund_payment",
    description="refund",
    parameters=(Parameter("payment_id", "str", True), Parameter("amount_cents", "int", True)),
    output="Refund",
    risk=Risk.FINANCIAL,
    scopes=frozenset({"billing.read", "billing.refund"}),
    idempotent=True,
    amount_field="amount_cents",
)
REPLY = Capability(
    "support.ticket.reply", "reply", (), "Reply", Risk.WRITE, frozenset({"support.reply"}), send=True
)
READ = Capability("crm.account.get", "get", (), "Account", Risk.READ, frozenset({"crm.read"}))
GATES = PolicyGates(approvals=True, financial_threshold_cents=500_000)

carol = principal_for("acme", "carol", {"finance"})
alice = principal_for("acme", "alice", {"sales"})
eve = principal_for("acme", "eve", {"support"})
dana = principal_for("acme", "dana", {"admin"})


def test_scope_is_checked_before_risk() -> None:
    d = policy.decide(alice, REFUND, {"amount_cents": 100}, GATES)
    assert d.effect is Effect.DENY and d.rule == "scope"


@pytest.mark.parametrize(
    ("amount", "effect"), [(100, Effect.ALLOW), (500_000, Effect.ALLOW), (500_001, Effect.APPROVE)]
)
def test_financial_threshold(amount: int, effect: Effect) -> None:
    assert policy.decide(carol, REFUND, {"amount_cents": amount}, GATES).effect is effect


def test_financial_without_checkable_amount_needs_approval() -> None:
    assert policy.decide(carol, REFUND, {"amount_cents": "lots"}, GATES).effect is Effect.APPROVE


def test_send_always_needs_approval_even_for_admin() -> None:
    assert policy.decide(eve, REPLY, {}, GATES).effect is Effect.APPROVE
    assert policy.decide(dana, REPLY, {}, GATES).effect is Effect.APPROVE


def test_admin_wildcard_scope() -> None:
    assert policy.decide(dana, READ, {}, GATES).effect is Effect.ALLOW


def test_approvals_off_is_scopes_only() -> None:
    gates = PolicyGates(approvals=False)
    assert policy.decide(carol, REFUND, {"amount_cents": 10**9}, gates).effect is Effect.ALLOW
    assert policy.decide(alice, REFUND, {"amount_cents": 1}, gates).effect is Effect.DENY  # scopes still hold


def test_unknown_capability_is_denied() -> None:
    assert policy.unknown("billing.export_all").effect is Effect.DENY
