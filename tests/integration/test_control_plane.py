"""The executor, approvals and both surfaces against seeded tenants, with no model and no transport."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from bench.checkers import last_payment, refunds_for_payment
from bizops.application.approvals import Approvals
from bizops.application.execution.executor import Executor
from bizops.domain.models.run import ApprovalOutcome, RunStatus, StepStatus
from bizops.infrastructure.di.container import Container
from tests.conftest import who

pytestmark = pytest.mark.integration


def _acme(c: Container) -> sqlite3.Connection:
    return sqlite3.connect(c.settings.data_dir / "acme.db")


def _refund(c: Container, amount: int | None = None) -> dict[str, object]:
    pay = last_payment(_acme(c), "Vandelay Ltd")
    return {
        "capability": "billing.refund_payment",
        "args": {
            "payment_id": pay["payment_id"],
            "amount_cents": amount or pay["amount_cents"],
            "reason": "duplicate charge",
        },
    }


def _refund_count(c: Container) -> int:
    pay = last_payment(_acme(c), "Vandelay Ltd")
    return int(refunds_for_payment(_acme(c), pay["payment_id"])["count"])


async def test_read_run_completes(seeded: Container) -> None:
    view = await seeded.executor.start(who(seeded, "acme/carol"), [{"capability": "billing.mrr_by_month"}])
    assert view.run.status is RunStatus.DONE and view.run.steps[0].status is StepStatus.DONE


async def test_large_refund_pauses_inspect_is_read_only_then_approval_runs_it_once(seeded: Container) -> None:
    carol = who(seeded, "acme/carol")
    surface = seeded.surface("discover")
    reply = await surface.call(carol, "execute", {"steps": [_refund(seeded)]})
    assert reply.approval is not None and reply.payload["status"] == RunStatus.AWAITING_APPROVAL
    assert "nonce" not in str(reply.payload) and reply.approval.nonce not in str(reply.payload)

    before = seeded.journal.db.execute("SELECT COUNT(*) FROM approval_requests").fetchone()[0]
    look = await surface.call(carol, "inspect", {"run_id": reply.run_id})
    after = seeded.journal.db.execute("SELECT COUNT(*) FROM approval_requests").fetchone()[0]
    assert (
        look.payload["status"] == RunStatus.AWAITING_APPROVAL
        and before == after
        and _refund_count(seeded) == 0
    )

    done = await surface.resolve(carol, reply.approval, approve=True, by="carol")
    assert done.payload["status"] == RunStatus.DONE and _refund_count(seeded) == 1


async def test_declined_step_never_runs(seeded: Container) -> None:
    carol = who(seeded, "acme/carol")
    surface = seeded.surface("static")
    reply = await surface.call(carol, "billing__refund_payment", _refund(seeded)["args"])  # type: ignore[arg-type]
    assert reply.approval is not None
    out = await surface.resolve(carol, reply.approval, approve=False, by="carol")
    assert (
        out.payload["status"] == RunStatus.FAILED and out.payload["steps"][0]["status"] == StepStatus.DECLINED
    )
    assert _refund_count(seeded) == 0


async def test_scope_denial_stops_the_run(seeded: Container) -> None:
    view = await seeded.executor.start(who(seeded, "acme/alice"), [_refund(seeded, 100)])
    assert view.run.status is RunStatus.FAILED and view.run.steps[0].status is StepStatus.DENIED
    assert view.approval is None


async def test_same_refund_twice_needs_a_human_the_second_time(seeded: Container) -> None:
    carol = who(seeded, "acme/carol")
    first = await seeded.executor.start(carol, [_refund(seeded, 10_000)])
    assert first.run.status is RunStatus.DONE
    second = await seeded.executor.start(carol, [_refund(seeded, 10_000)])
    assert second.run.status is RunStatus.AWAITING_APPROVAL and second.run.steps[0].rule == "duplicate"
    assert _refund_count(seeded) == 1


async def test_runs_are_private_to_their_principal(seeded: Container) -> None:
    view = await seeded.executor.start(who(seeded, "acme/carol"), [_refund(seeded)])
    surface = seeded.surface("discover")
    for intruder in ("acme/dana", "globex/carol"):
        r = await surface.call(who(seeded, intruder), "execute", {"run_id": view.run.id})
        assert r.is_error and "no run" in r.payload["error"]


async def test_operator_approval_then_execute_continues(seeded: Container) -> None:
    carol = who(seeded, "acme/carol")
    view = await seeded.executor.start(carol, [_refund(seeded)])
    step = view.run.steps[0]
    outcome = seeded.approvals.resolve_as_operator(
        run_id=view.run.id, step_id=step.id, tenant="acme", approve=True, by="ops"
    )
    assert outcome is ApprovalOutcome.APPROVED
    reply = await seeded.surface("discover").call(carol, "execute", {"run_id": view.run.id})
    assert reply.payload["status"] == RunStatus.DONE and _refund_count(seeded) == 1


# ---- the seven approval cases ---------------------------------------------------------------------


async def _paused(c: Container, approvals: Approvals | None = None) -> tuple[Executor, str, str, str]:
    ex = c.executor if approvals is None else Executor(c.dispatcher, c.journal, approvals, c.wall_clock)
    view = await ex.start(who(c, "acme/carol"), [_refund(c)])
    assert view.approval is not None
    return ex, view.run.id, view.run.steps[0].id, view.approval.nonce


async def test_approval_wrong_run_wrong_step_wrong_tenant(seeded: Container) -> None:
    ex, run_id, step_id, nonce = await _paused(seeded)
    _, other_run, other_step, _ = await _paused(seeded)
    a = seeded.approvals
    assert a.resolve(nonce, run_id=other_run, step_id=step_id, tenant="acme", approve=True, by="x") is (
        ApprovalOutcome.WRONG_BINDING
    )
    assert a.resolve(nonce, run_id=run_id, step_id=other_step, tenant="acme", approve=True, by="x") is (
        ApprovalOutcome.WRONG_BINDING
    )
    assert a.resolve(nonce, run_id=run_id, step_id=step_id, tenant="globex", approve=True, by="x") is (
        ApprovalOutcome.WRONG_BINDING
    )
    assert _refund_count(seeded) == 0


async def test_approval_tampered_replayed_and_valid_once(seeded: Container) -> None:
    _, run_id, step_id, nonce = await _paused(seeded)
    a = seeded.approvals
    kw = {"run_id": run_id, "step_id": step_id, "tenant": "acme", "approve": True, "by": "carol"}
    assert a.resolve(nonce + "x", **kw) is ApprovalOutcome.NOT_FOUND  # type: ignore[arg-type]
    assert a.resolve(nonce, **kw) is ApprovalOutcome.APPROVED  # type: ignore[arg-type]
    assert a.resolve(nonce, **kw) is ApprovalOutcome.ALREADY_USED  # type: ignore[arg-type]


async def test_approval_expired(seeded: Container) -> None:
    clock = [datetime(2026, 10, 31, 9, 0, tzinfo=UTC)]
    approvals = Approvals(seeded.journal, lambda: clock[0], ttl=timedelta(minutes=10))
    _, run_id, step_id, nonce = await _paused(seeded, approvals)
    clock[0] += timedelta(minutes=11)
    kw = {"run_id": run_id, "step_id": step_id, "tenant": "acme", "approve": True, "by": "carol"}
    assert approvals.resolve(nonce, **kw) is ApprovalOutcome.EXPIRED  # type: ignore[arg-type]
    assert approvals.resolve(nonce, **kw) is ApprovalOutcome.ALREADY_USED  # type: ignore[arg-type]
    assert _refund_count(seeded) == 0


async def test_reissued_approval_supersedes_the_old_nonce(seeded: Container) -> None:
    ex, run_id, step_id, old = await _paused(seeded)
    again = await ex.resume(who(seeded, "acme/carol"), run_id)  # still paused: a fresh request is issued
    assert again.approval is not None and again.approval.nonce != old
    kw = {"run_id": run_id, "step_id": step_id, "tenant": "acme", "approve": True, "by": "carol"}
    assert seeded.approvals.resolve(old, **kw) is ApprovalOutcome.ALREADY_USED  # type: ignore[arg-type]
    assert seeded.approvals.resolve(again.approval.nonce, **kw) is ApprovalOutcome.APPROVED  # type: ignore[arg-type]
