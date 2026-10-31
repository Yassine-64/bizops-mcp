"""End to end through MCP: a real client, the bizops server, the executor, the connectors. Both protocol eras:
'auto' is the 2026-07-28 input-required retry, 'legacy' is the handshake-era elicitation back-channel."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import mcp_types as t
import pytest
from mcp import Client

from bench.checkers import last_payment, refunds_for_payment
from bizops.infrastructure.container import Container
from bizops.interfaces.mcp_server import build_server
from tests.conftest import who

pytestmark = pytest.mark.integration
MODES = ["auto", "legacy"]


def human(approve: bool, asked: list[str]) -> Any:
    async def on_elicit(ctx: Any, params: Any) -> t.ElicitResult:
        asked.append(params.message)
        return t.ElicitResult(action="accept", content={"approve": approve})

    return on_elicit


def payload(r: t.CallToolResult) -> dict[str, Any]:
    text = "".join(c.text for c in r.content if isinstance(c, t.TextContent))
    return dict(json.loads(text))


def _refunds(c: Container) -> int:
    conn = sqlite3.connect(c.settings.data_dir / "acme.db")
    return int(refunds_for_payment(conn, last_payment(conn, "Vandelay Ltd")["payment_id"])["count"])


@pytest.mark.parametrize("surface", ["discover", "static"])
async def test_tool_lists(seeded: Container, surface: str) -> None:
    server = build_server(seeded.surface(surface), lambda _: who(seeded, "acme/carol"))  # type: ignore[arg-type]
    async with Client(server) as client:
        names = [x.name for x in (await client.list_tools()).tools]
    if surface == "discover":
        assert names == ["discover", "execute", "inspect"]
    else:
        assert len(names) == len(seeded.registry) and "billing__refund_payment" in names


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("approve", [True, False])
async def test_refund_through_discover_with_a_human(seeded: Container, mode: str, approve: bool) -> None:
    carol = who(seeded, "acme/carol")
    server = build_server(seeded.surface("discover"), lambda _: carol)
    asked: list[str] = []
    pay = last_payment(sqlite3.connect(seeded.settings.data_dir / "acme.db"), "Vandelay Ltd")
    async with Client(server, mode=mode, elicitation_callback=human(approve, asked)) as client:
        found = payload(await client.call_tool("discover", {"query": "refund a payment"}))
        assert found["capabilities"][0].startswith(
            "billing.refund_payment(payment_id: str, amount_cents: int"
        )
        step = {
            "capability": "billing.refund_payment",
            "args": {
                "payment_id": pay["payment_id"],
                "amount_cents": pay["amount_cents"],
                "reason": "duplicate",
            },
        }
        out = payload(await client.call_tool("execute", {"steps": [step]}))
    assert len(asked) == 1 and "billing.refund_payment" in asked[0] and pay["payment_id"] in asked[0]
    assert out["status"] == ("done" if approve else "failed")
    assert _refunds(seeded) == (1 if approve else 0)
    assert "nonce" not in json.dumps(out) and "request_state" not in json.dumps(out)


@pytest.mark.parametrize("mode", MODES)
async def test_read_needs_no_human(seeded: Container, mode: str) -> None:
    server = build_server(seeded.surface("static"), lambda _: who(seeded, "acme/carol"))
    asked: list[str] = []
    async with Client(server, mode=mode, elicitation_callback=human(True, asked)) as client:
        out = payload(await client.call_tool("billing__mrr_by_month", {"months": 2}))
    assert out["status"] == "done" and asked == []


async def test_forged_request_state_is_refused(seeded: Container) -> None:
    carol = who(seeded, "acme/carol")
    server = build_server(seeded.surface("discover"), lambda _: carol)
    pay = last_payment(sqlite3.connect(seeded.settings.data_dir / "acme.db"), "Vandelay Ltd")
    step = {
        "capability": "billing.refund_payment",
        "args": {"payment_id": pay["payment_id"], "amount_cents": pay["amount_cents"], "reason": "x"},
    }
    async with Client(server, mode="auto") as client:
        first = await client.session.call_tool("execute", {"steps": [step]}, allow_input_required=True)
        assert isinstance(first, t.InputRequiredResult) and first.request_state
        run_id, step_id, _nonce = first.request_state.split(".", 2)
        forged = await client.session.call_tool(
            "execute",
            {"steps": [step]},
            input_responses={"bizops_approval": t.ElicitResult(action="accept", content={"approve": True})},
            request_state=f"{run_id}.{step_id}.forged",
            allow_input_required=True,
        )
    assert isinstance(forged, t.CallToolResult) and forged.is_error
    assert "not_found" in payload(forged)["error"] and _refunds(seeded) == 0
