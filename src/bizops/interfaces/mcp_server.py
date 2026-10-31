"""The MCP server: a thin transport over a `Surface`, with the human approval channel.

Approvals, current protocol (2026-07-28): a paused run is returned as an `InputRequiredResult` whose embedded
elicitation asks the human; the client retries the call carrying the answer and the opaque `request_state`
(`run_id.step_id.nonce`). The server keeps no state between the two calls; the journal holds it all.
Handshake-era clients get the same question as a form elicitation on the back-channel. A client that can do
neither gets the paused run back, and a human approves it with `bizops approve`.

The model never sees the nonce: `request_state` is consumed by the client's input-required driver, and tool
results are rendered from `ToolReply.payload`, which carries none."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import mcp_types as t
from mcp.server import Server
from mcp.shared.exceptions import MCPError, NoBackChannelError

from bizops.application.surfaces import Surface, ToolReply
from bizops.domain.models import Principal

APPROVAL_KEY = "bizops_approval"
APPROVAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"approve": {"type": "boolean", "title": "Approve this exact call?"}},
    "required": ["approve"],
}


def _accepted(answer: Any) -> bool:
    return getattr(answer, "action", None) == "accept" and bool(
        (getattr(answer, "content", None) or {}).get("approve")
    )


def _state(reply: ToolReply) -> str:
    assert reply.approval is not None
    req = reply.approval.request
    return f"{req.run_id}.{req.step_id}.{reply.approval.nonce}"


def _parse_state(state: str) -> tuple[str, str, str] | None:
    parts = state.split(".", 2)
    return (parts[0], parts[1], parts[2]) if len(parts) == 3 and all(parts) else None


def _result(reply: ToolReply) -> t.CallToolResult:
    text = json.dumps(reply.payload, ensure_ascii=False, default=str)
    return t.CallToolResult(content=[t.TextContent(type="text", text=text)], is_error=reply.is_error)


def principal_from_request(ctx: Any) -> Principal:
    """HTTP: the principal the bearer middleware resolved for this request. The model cannot set it."""
    principal: Principal = ctx.request.state.bizops_principal
    return principal


def http_app(server: Server, authenticate: Callable[[str], Principal | None]) -> Any:
    """Streamable HTTP with bearer principals. Authentication happens before MCP: a missing or unknown token
    is a 401 and never reaches a handler. JSON responses, stateless: approvals use the input-required retry.
    The SDK's DNS-rebinding protection stays on, so clients must send Host with its port."""
    from starlette.responses import JSONResponse

    inner = server.streamable_http_app(json_response=True, stateless_http=True)

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await inner(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        scheme, _, token = headers.get("authorization", "").partition(" ")
        principal = authenticate(token.strip()) if scheme.lower() == "bearer" and token else None
        if principal is None:
            response = JSONResponse(
                {"error": "a valid bearer token is required"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        scope.setdefault("state", {})["bizops_principal"] = principal
        await inner(scope, receive, send)

    # the session manager's lifespan lives on the inner Starlette router; expose it to the ASGI server
    app.router = inner.router  # type: ignore[attr-defined]
    return app


def build_server(surface: Surface, principal: Callable[[Any], Principal], name: str = "bizops") -> Server:
    """`principal(ctx)` resolves the caller from the transport (env for stdio, bearer token for HTTP)."""

    async def on_list_tools(ctx: Any, params: Any) -> t.ListToolsResult:
        return t.ListToolsResult(
            tools=[
                t.Tool(name=s.name, description=s.description, input_schema=s.input_schema)
                for s in surface.tools()
            ]
        )

    async def on_call_tool(ctx: Any, p: t.CallToolRequestParams) -> t.CallToolResult | t.InputRequiredResult:
        who = principal(ctx)
        responses = p.input_responses or {}
        if APPROVAL_KEY in responses and p.request_state:
            parsed = _parse_state(p.request_state)
            if parsed is None:
                return _result(ToolReply.error("approval state is malformed"))
            run_id, step_id, nonce = parsed
            reply = await surface.resolve_state(
                who, run_id, step_id, nonce, _accepted(responses[APPROVAL_KEY]), by=f"{who.user} (mcp client)"
            )
        else:
            reply = await surface.call(who, p.name, dict(p.arguments or {}))

        while reply.approval is not None:
            prompt = reply.approval_prompt or "Approve this call?"
            try:
                answer = await ctx.session.elicit_form(prompt, APPROVAL_SCHEMA)
            except NoBackChannelError:
                return t.InputRequiredResult(
                    input_requests={
                        APPROVAL_KEY: t.ElicitRequest(
                            params=t.ElicitRequestFormParams(message=prompt, requested_schema=APPROVAL_SCHEMA)
                        )
                    },
                    request_state=_state(reply),
                )
            except MCPError:
                break  # no human reachable through this client: the run stays paused for `bizops approve`
            reply = await surface.resolve(
                who, reply.approval, _accepted(answer), by=f"{who.user} (mcp client)"
            )
        return _result(reply)

    return Server(name, on_list_tools=on_list_tools, on_call_tool=on_call_tool)


__all__ = ["APPROVAL_KEY", "build_server", "http_app", "principal_from_request"]
