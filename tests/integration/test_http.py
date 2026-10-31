"""Streamable HTTP with bearer principals: the token decides the tenant and the roles, never the model."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import httpx2
import mcp_types as t
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from bench.checkers import last_payment, refunds_for_payment
from bizops.infrastructure.container import Container
from bizops.interfaces.mcp_server import build_server, http_app, principal_from_request

pytestmark = pytest.mark.integration
BASE = "http://127.0.0.1:8765"  # a port in Host: the SDK rejects bare hosts (DNS-rebinding protection)


def _token(c: Container, tenant: str, user: str) -> str:
    return c.tenants.issue_token(tenant, user)


def _payload(r: t.CallToolResult) -> dict[str, Any]:
    return dict(json.loads("".join(c.text for c in r.content if isinstance(c, t.TextContent))))


async def _call(
    app: Any, token: str | None, tool: str, args: dict[str, Any], human: bool | None = None
) -> Any:
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def on_elicit(ctx: Any, params: Any) -> t.ElicitResult:
        return t.ElicitResult(action="accept", content={"approve": bool(human)})

    async with (
        httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=BASE, headers=headers) as http,
        Client(
            streamable_http_client(f"{BASE}/mcp", http_client=http), elicitation_callback=on_elicit
        ) as client,
    ):
        return await client.call_tool(tool, args)


@pytest.fixture
def app(seeded: Container) -> Any:
    server = build_server(seeded.surface("discover"), principal_from_request)
    return http_app(server, seeded.tenants.authenticate_token)


def running(app: Any) -> Any:
    """The session manager runs once per app, inside the test's own task."""
    return app.router.lifespan_context(app)


async def test_missing_or_unknown_token_is_401(app: Any) -> None:
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=BASE) as http:
        assert (await http.post("/mcp", json={})).status_code == 401
        bad = await http.post("/mcp", json={}, headers={"Authorization": "Bearer bo_forged"})
        assert bad.status_code == 401 and bad.headers["www-authenticate"] == "Bearer"


async def test_the_token_picks_the_tenant(seeded: Container, app: Any) -> None:
    step = {"steps": [{"capability": "crm.account.get", "args": {"account_id": "acc_010"}}]}
    async with running(app):
        acme = _payload(await _call(app, _token(seeded, "acme", "alice"), "execute", step))
        globex = _payload(await _call(app, _token(seeded, "globex", "alice"), "execute", step))
    assert acme["steps"][0]["result"]["name"] != globex["steps"][0]["result"]["name"]


async def test_roles_come_from_the_token_and_approvals_work_over_http(seeded: Container, app: Any) -> None:
    pay = last_payment(sqlite3.connect(seeded.settings.data_dir / "acme.db"), "Vandelay Ltd")
    refund = {
        "steps": [
            {
                "capability": "billing.refund_payment",
                "args": {
                    "payment_id": pay["payment_id"],
                    "amount_cents": pay["amount_cents"],
                    "reason": "dup",
                },
            }
        ]
    }
    async with running(app):
        as_sales = _payload(await _call(app, _token(seeded, "acme", "alice"), "execute", refund, human=True))
        as_finance = _payload(
            await _call(app, _token(seeded, "acme", "carol"), "execute", refund, human=True)
        )
    assert as_sales["steps"][0]["status"] == "denied"
    assert as_finance["status"] == "done"
    conn = sqlite3.connect(seeded.settings.data_dir / "acme.db")
    assert refunds_for_payment(conn, pay["payment_id"])["count"] == 1


async def test_tokens_are_random_hashed_rotated_and_revocable(seeded: Container, app: Any) -> None:
    first = seeded.tenants.issue_token("acme", "carol")
    stored = (
        sqlite3.connect(seeded.settings.data_dir / "acme.db")
        .execute("SELECT token_hash FROM principals WHERE user = 'carol'")
        .fetchone()[0]
    )
    assert first not in stored and len(first) > 40  # only a digest is stored; the token has ~256 bits
    assert seeded.tenants.authenticate_token(first) is not None
    second = seeded.tenants.issue_token("acme", "carol")  # rotation
    assert second != first
    assert seeded.tenants.authenticate_token(first) is None
    assert seeded.tenants.authenticate_token(second) is not None
    seeded.tenants.revoke_token("acme", "carol")
    assert seeded.tenants.authenticate_token(second) is None
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=BASE) as http:
        r = await http.post("/mcp", json={}, headers={"Authorization": f"Bearer {second}"})
        assert r.status_code == 401


def test_a_fresh_seed_has_no_credentials(seeded: Container) -> None:
    conn = sqlite3.connect(seeded.settings.data_dir / "acme.db")
    assert conn.execute("SELECT COUNT(*) FROM principals WHERE token_hash IS NOT NULL").fetchone()[0] == 0
