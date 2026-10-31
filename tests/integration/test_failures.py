"""Failure injection against the durable executor and the naive client. The centrepiece: a refund whose
response is lost after it committed. The durable executor retries under the same operation id and the
connector replays; the naive client retries with a fresh id and refunds twice."""

from __future__ import annotations

import sqlite3

import pytest

from bench.checkers import injection_ticket, last_payment, refunds_for_payment, replies_for_ticket
from bizops.application.config import ControlPlaneConfig
from bizops.application.execution.executor import Executor
from bizops.domain.models.run import RunStatus, StepStatus
from bizops.infrastructure.connectors.chaos import PROFILES
from bizops.infrastructure.di.container import Container
from tests.conftest import who

pytestmark = pytest.mark.integration


async def _no_sleep(_: float) -> None:
    return None


def _executor(c: Container, durable: bool) -> Executor:
    return Executor(c.dispatcher, c.journal, c.approvals, c.wall_clock, durable=durable, sleep=_no_sleep)


def _db(c: Container) -> sqlite3.Connection:
    return sqlite3.connect(c.settings.data_dir / "acme.db")


def _small_refund(c: Container) -> dict[str, object]:
    pay = last_payment(_db(c), "Vandelay Ltd")
    args = {"payment_id": pay["payment_id"], "amount_cents": 10_000, "reason": "goodwill"}
    return {"capability": "billing.refund_payment", "args": args}


def _refunds(c: Container) -> int:
    return int(refunds_for_payment(_db(c), last_payment(_db(c), "Vandelay Ltd")["payment_id"])["count"])


@pytest.mark.parametrize("profile", PROFILES)
async def test_reads_survive_every_profile(seeded: Container, profile: str) -> None:
    c = seeded.with_chaos(profile, "billing.mrr_by_month")
    view = await _executor(c, durable=True).start(
        who(c, "acme/carol"), [{"capability": "billing.mrr_by_month"}]
    )
    assert view.run.status is RunStatus.DONE and view.run.steps[0].attempts == 2


@pytest.mark.parametrize(("durable", "expected"), [(True, 1), (False, 2)])
async def test_commit_then_drop_refund(seeded: Container, durable: bool, expected: int) -> None:
    c = seeded.with_chaos("commit_then_drop", "billing.refund_payment")
    view = await _executor(c, durable).start(who(c, "acme/carol"), [_small_refund(c)])
    assert view.run.status is RunStatus.DONE
    assert _refunds(c) == expected  # durable: replayed under the same operation id; naive: refunded twice
    if durable:
        assert view.run.steps[0].result["replayed"] is True


@pytest.mark.parametrize("profile", ["timeout_once", "rate_limit_once", "credential_expired"])
async def test_uncommitted_failures_still_refund_exactly_once(seeded: Container, profile: str) -> None:
    c = seeded.with_chaos(profile, "billing.refund_payment")
    view = await _executor(c, durable=True).start(who(c, "acme/carol"), [_small_refund(c)])
    assert view.run.status is RunStatus.DONE and _refunds(c) == 1


@pytest.mark.parametrize(
    ("durable", "status", "replies"),
    [
        (True, StepStatus.DELIVERY_UNCERTAIN, 1),  # sent once, then refuses to guess: never sent again
        (False, StepStatus.DONE, 2),  # the naive client sends the customer the same message twice
    ],
)
async def test_lost_response_on_a_send(
    seeded: Container, durable: bool, status: StepStatus, replies: int
) -> None:
    c = seeded.with_chaos("commit_then_drop", "support.ticket.reply")
    ticket = injection_ticket(_db(c))["ticket_id"]
    ex = _executor(c, durable)
    eve = who(c, "acme/eve")
    view = await ex.start(
        eve, [{"capability": "support.ticket.reply", "args": {"ticket_id": ticket, "body": "On it."}}]
    )
    assert view.approval is not None  # sends always need a human
    c.approvals.resolve(
        view.approval.nonce,
        run_id=view.run.id,
        step_id=view.run.steps[0].id,
        tenant="acme",
        approve=True,
        by="eve",
    )
    after = await ex.resume(eve, view.run.id)
    assert after.run.steps[0].status is status
    assert replies_for_ticket(_db(c), ticket)["count"] == replies


class Crash(BaseException):
    """The process dies: nothing in the executor catches this."""


async def test_crash_after_commit_is_adopted_on_resume(seeded: Container) -> None:
    carol = who(seeded, "acme/carol")
    bound = seeded.registry.get("billing.refund_payment")
    assert bound is not None

    async def commit_then_die(ctx: object, **args: object) -> object:
        await bound.handler(ctx, **args)
        raise Crash

    crashing = ControlPlaneConfig()
    c = seeded.with_config(crashing)
    c.__dict__["registry"] = seeded.registry.with_handler("billing.refund_payment", commit_then_die)
    with pytest.raises(Crash):
        await _executor(c, durable=True).start(carol, [_small_refund(c)])
    (run_id,) = [r[0] for r in seeded.journal.db.execute("SELECT id FROM runs")]
    left = seeded.journal.get_run(run_id)
    assert left is not None and left.steps[0].status is StepStatus.RUNNING  # write-ahead entry survived
    assert _refunds(seeded) == 1

    restarted = _executor(seeded, durable=True)  # a new process over the same journal
    view = await restarted.resume(carol, run_id)
    assert view.run.status is RunStatus.DONE and view.run.steps[0].result["replayed"] is True
    assert _refunds(seeded) == 1
