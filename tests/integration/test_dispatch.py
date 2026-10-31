"""Policy and connectors together, against freshly seeded tenants."""

from __future__ import annotations

import sqlite3

import pytest

from bench.checkers import last_payment, refunds_for_payment
from bizops.domain.exceptions import NotFound
from bizops.domain.models.capability import Effect
from bizops.infrastructure.connectors._base import MAX_LIMIT
from bizops.infrastructure.di.container import Container
from tests.conftest import who

pytestmark = pytest.mark.integration


def _acme(c: Container) -> sqlite3.Connection:
    return sqlite3.connect(c.settings.data_dir / "acme.db")


async def test_read_runs_for_a_scoped_user(seeded: Container) -> None:
    r = await seeded.dispatcher.run(who(seeded, "acme/carol"), "billing.mrr_by_month", {"months": 3})
    assert r.executed and r.decision.effect is Effect.ALLOW
    assert [m["month"] for m in r.output] == ["2026-08", "2026-09", "2026-10"]


async def test_refund_by_sales_is_denied_before_it_runs(seeded: Container) -> None:
    pay = last_payment(_acme(seeded), "Vandelay Ltd")
    r = await seeded.dispatcher.run(
        who(seeded, "acme/alice"),
        "billing.refund_payment",
        {"payment_id": pay["payment_id"], "amount_cents": 100, "reason": "goodwill"},
        operation_id="op-1",
    )
    assert not r.executed and r.decision.effect is Effect.DENY and r.decision.rule == "scope"
    assert refunds_for_payment(_acme(seeded), pay["payment_id"])["count"] == 0


async def test_large_refund_pauses_and_small_one_runs_once_per_operation(seeded: Container) -> None:
    carol = who(seeded, "acme/carol")
    pay = last_payment(_acme(seeded), "Vandelay Ltd")
    big = {"payment_id": pay["payment_id"], "amount_cents": pay["amount_cents"], "reason": "duplicate"}
    r = await seeded.dispatcher.run(carol, "billing.refund_payment", big, operation_id="op-big")
    assert r.decision.effect is Effect.APPROVE and not r.executed

    small = {**big, "amount_cents": 10_000}
    first = await seeded.dispatcher.run(carol, "billing.refund_payment", small, operation_id="op-small")
    again = await seeded.dispatcher.run(carol, "billing.refund_payment", small, operation_id="op-small")
    assert first.output["replayed"] is False and again.output["replayed"] is True
    assert first.output["id"] == again.output["id"]
    assert refunds_for_payment(_acme(seeded), pay["payment_id"]) == {"count": 1, "total_cents": 10_000}


async def test_tenants_are_physically_isolated(seeded: Container) -> None:
    alice_acme = who(seeded, "acme/alice")
    alice_globex = who(seeded, "globex/alice")
    acme = await seeded.dispatcher.run(alice_acme, "crm.account.get", {"account_id": "acc_010"})
    globex = await seeded.dispatcher.run(alice_globex, "crm.account.get", {"account_id": "acc_010"})
    assert acme.output["name"] != globex.output["name"]  # same id, different company: no shared rows
    with pytest.raises(NotFound):
        await seeded.dispatcher.run(alice_acme, "billing.invoice.get", {"invoice_id": "in_9999"})


async def test_result_size_is_capped(seeded: Container) -> None:
    r = await seeded.dispatcher.run(who(seeded, "acme/alice"), "crm.accounts.search", {"max_rows": 10_000})
    assert len(r.output) == MAX_LIMIT


async def test_unknown_capability_is_denied(seeded: Container) -> None:
    r = await seeded.dispatcher.run(who(seeded, "acme/dana"), "crm.export_all", {})
    assert r.decision.effect is Effect.DENY and r.decision.rule == "unknown"


def test_every_capability_is_described_and_classified(seeded: Container) -> None:
    caps = seeded.registry.capabilities()
    assert len(caps) >= 25
    for cap in caps:
        assert cap.description and cap.scopes, cap.name
        assert all(p.description for p in cap.parameters), f"{cap.name} has an undocumented parameter"
        if cap.send:
            assert not cap.idempotent, f"{cap.name}: a send can never be adopted after a lost response"
