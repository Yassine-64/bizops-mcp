"""Spans: one tree per run (run -> step -> policy / connector), approvals and retries visible, and nothing a
customer or the model wrote ever stored in an attribute."""

from __future__ import annotations

import json
import sqlite3

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from bench.checkers import last_payment
from bizops.application.execution.executor import Executor
from bizops.infrastructure.container import Container
from tests.conftest import who

pytestmark = pytest.mark.integration
EXPORTER = InMemorySpanExporter()


@pytest.fixture(autouse=True)
def spans() -> InMemorySpanExporter:
    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(EXPORTER))
        trace.set_tracer_provider(provider)
    EXPORTER.clear()
    return EXPORTER


async def test_refund_with_approval_is_one_payload_free_tree(
    seeded: Container, spans: InMemorySpanExporter
) -> None:
    carol = who(seeded, "acme/carol")
    pay = last_payment(sqlite3.connect(seeded.settings.data_dir / "acme.db"), "Vandelay Ltd")
    args = {
        "payment_id": pay["payment_id"],
        "amount_cents": pay["amount_cents"],
        "reason": "duplicate charge xyzzy",
    }
    surface = seeded.surface("discover")
    with trace.get_tracer("test").start_as_current_span("agent.turn"):
        await surface.call(carol, "discover", {"query": "refund a payment"})
        reply = await surface.call(
            carol, "execute", {"steps": [{"capability": "billing.refund_payment", "args": args}]}
        )
        assert reply.approval is not None
        await surface.resolve(carol, reply.approval, True, by="carol")

    got = spans.get_finished_spans()
    names = [s.name for s in got]
    for expected in (
        "bizops.discover",
        "bizops.run",
        "bizops.step",
        "bizops.policy",
        "bizops.approval.issue",
        "bizops.approval.resolve",
        "bizops.connector",
    ):
        assert expected in names, names
    assert len({s.context.trace_id for s in got}) == 1  # everything under the agent's turn

    by_id = {s.context.span_id: s for s in got}

    def ancestors(s: object) -> list[str]:
        out, cur = [], getattr(s, "parent", None)
        while cur is not None and cur.span_id in by_id:
            out.append(by_id[cur.span_id].name)
            cur = by_id[cur.span_id].parent
        return out

    connector = next(s for s in got if s.name == "bizops.connector")
    assert ancestors(connector)[:2] == ["bizops.step", "bizops.run"]
    runs = [s for s in got if s.name == "bizops.run"]
    assert [r.attributes["bizops.entry"] for r in runs] == ["start", "resume"]
    assert runs[0].attributes["bizops.awaiting_approval"] is True

    dumped = json.dumps(
        [dict(s.attributes or {}) for s in got] + [[dict(e.attributes or {}) for e in s.events] for s in got]
    )
    for secret in (pay["payment_id"], str(pay["amount_cents"]), "xyzzy", "refund a payment"):
        assert secret not in dumped, secret


async def test_retries_are_events_on_the_step(seeded: Container, spans: InMemorySpanExporter) -> None:
    async def no_sleep(_: float) -> None:
        return None

    c = seeded.with_chaos("rate_limit_once", "billing.mrr_by_month")
    ex = Executor(c.dispatcher, c.journal, c.approvals, c.wall_clock, sleep=no_sleep)
    await ex.start(who(c, "acme/carol"), [{"capability": "billing.mrr_by_month"}])
    step = next(s for s in spans.get_finished_spans() if s.name == "bizops.step")
    assert [e.name for e in step.events] == ["retry"]
    assert step.events[0].attributes["bizops.error"] == "RateLimited"
    assert step.attributes["bizops.attempts"] == 2
    failed = [s for s in spans.get_finished_spans() if s.name == "bizops.connector" and not s.status.is_ok]
    assert len(failed) == 1  # the 429 is recorded on its connector span
