"""Replay reproduces a recorded run's decisions and results, and reports policy drift or tampering."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from bench.checkers import last_payment
from bizops.application.replay import Replayer
from bizops.domain.models.capability import PolicyGates
from bizops.infrastructure.container import Container
from bizops.infrastructure.journal import SqliteJournal
from tests.conftest import who

pytestmark = pytest.mark.integration


def _replayer(c: Container, tmp: Path, gates: PolicyGates | None = None) -> Replayer:
    n = [0]

    def scratch() -> SqliteJournal:
        n[0] += 1
        return SqliteJournal(tmp / f"replay-{n[0]}.db")

    return Replayer(
        c.journal, c.registry, gates or c.gates, c.tenants.principal, scratch, c.clock, c.wall_clock
    )


async def _approved_refund_run(c: Container) -> str:
    carol = who(c, "acme/carol")
    pay = last_payment(sqlite3.connect(c.settings.data_dir / "acme.db"), "Vandelay Ltd")
    steps = [
        {"capability": "billing.mrr_by_month", "args": {"months": 2}},
        {
            "capability": "billing.refund_payment",
            "args": {"payment_id": pay["payment_id"], "amount_cents": pay["amount_cents"], "reason": "dup"},
        },
    ]
    surface = c.surface("discover")
    reply = await surface.call(carol, "execute", {"steps": steps})
    assert reply.approval is not None
    done = await surface.resolve(carol, reply.approval, True, by="carol")
    assert done.payload["status"] == "done"
    return str(reply.run_id)


async def test_recorded_run_replays_with_zero_divergence(seeded: Container, tmp_path: Path) -> None:
    run_id = await _approved_refund_run(seeded)
    report = await _replayer(seeded, tmp_path).replay(run_id)
    assert report.clean, report.divergences
    assert report.steps == 2


async def test_policy_drift_is_reported(seeded: Container, tmp_path: Path) -> None:
    run_id = await _approved_refund_run(seeded)
    looser = PolicyGates(approvals=True, financial_threshold_cents=10**12)  # the refund would no longer pause
    report = await _replayer(seeded, tmp_path, looser).replay(run_id)
    fields = {(d.step, d.field) for d in report.divergences}
    assert (2, "decision") in fields and (2, "rule") not in fields  # same gate fired, different effect


async def test_tampered_recording_is_reported(seeded: Container, tmp_path: Path) -> None:
    run_id = await _approved_refund_run(seeded)
    seeded.journal.db.execute(
        "UPDATE steps SET decision = 'allow' WHERE run_id = ? AND seq = 2", (run_id,)
    )  # someone rewrites history: "this refund never needed a human"
    report = await _replayer(seeded, tmp_path).replay(run_id)
    assert [(d.step, d.field, d.recorded, d.replayed) for d in report.divergences] == [
        (2, "decision", "allow", "approve")
    ]


async def test_replay_cannot_see_an_edited_result_by_design(seeded: Container, tmp_path: Path) -> None:
    run_id = await _approved_refund_run(seeded)
    row = seeded.journal.db.execute(
        "SELECT id, result FROM steps WHERE run_id = ? AND seq = 2", (run_id,)
    ).fetchone()
    result = json.loads(row[1])
    result["amount_cents"] += 1
    seeded.journal.db.execute("UPDATE steps SET result = ? WHERE id = ?", (json.dumps(result), row[0]))
    report = await _replayer(seeded, tmp_path).replay(run_id)
    assert report.clean  # replay returns what was recorded, so an edited result replays as itself...
    # ...which is why results are compared against the store, not the journal, by the bench grader.
