"""The agent under test: Claude in a plain manual tool loop over one surface. Every arm uses this loop, the
same model, the same parameters and the same system prompt apart from one surface-specific line.

The surface is presented in-process through the Anthropic SDK (not over MCP) because the tool-search arm
relies on the Claude API's `defer_loading`, which only exists on the client side of a Messages request.
The human channel is simulated: when a reply carries an approval, the scenario's `human` decides."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from anthropic import AsyncAnthropic

from bizops.application.surfaces import Surface
from bizops.domain.models import Principal

Arm = Literal["static", "tool_search", "discover"]

SYSTEM = (
    "You are an operations analyst at a B2B SaaS company with access to its business systems through tools. "
    "Answer from the systems, never from guesses. Work efficiently. When you are done, reply with a concise "
    "final answer that names the specific accounts, ids, amounts and dates you found."
)
SURFACE_LINE = {
    "static": "",
    "tool_search": " Your tools are loaded on demand: search for them with the tool search tool.",
    "discover": " Find capabilities with discover, then run them with execute.",
}
TOOL_SEARCH = {"type": "tool_search_tool_bm25_20251119", "name": "tool_search_tool_bm25"}


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def add(self, u: Any) -> None:
        self.input_tokens += u.input_tokens or 0
        self.output_tokens += u.output_tokens or 0
        self.cache_read_tokens += getattr(u, "cache_read_input_tokens", 0) or 0
        self.cache_write_tokens += getattr(u, "cache_creation_input_tokens", 0) or 0


@dataclass
class Transcript:
    final_answer: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    approvals: list[dict[str, Any]] = field(default_factory=list)
    run_ids: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    turns: int = 0
    stop_reason: str | None = None
    latency_ms: float = 0.0
    error: str | None = None


def api_tools(surface: Surface, arm: Arm) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = [
        {"name": s.name, "description": s.description, "input_schema": s.input_schema}
        for s in surface.tools()
    ]
    if arm == "tool_search":
        tools = [TOOL_SEARCH, *({**t, "defer_loading": True} for t in tools)]
    return tools


async def run_agent(
    client: AsyncAnthropic,
    *,
    model: str,
    surface: Surface,
    arm: Arm,
    principal: Principal,
    task: str,
    human: Literal["approve", "decline"],
    max_turns: int = 15,
    effort: str = "medium",
) -> Transcript:
    tools = api_tools(surface, arm)
    system = SYSTEM + SURFACE_LINE[arm]
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
    out = Transcript()
    started = time.perf_counter()
    try:
        while out.turns < max_turns:
            out.turns += 1
            resp = await client.messages.create(
                model=model,
                max_tokens=8000,
                system=system,
                tools=tools,  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
                output_config={"effort": effort},  # type: ignore[typeddict-item]
                cache_control={"type": "ephemeral"},
            )
            out.usage.add(resp.usage)
            out.stop_reason = resp.stop_reason
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason != "tool_use":
                out.final_answer = "\n".join(b.text for b in resp.content if b.type == "text").strip()
                break
            results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                results.append(await _call(surface, principal, block, human, out))
            messages.append({"role": "user", "content": results})
    except Exception as e:  # an API or harness failure is a result, not a crash of the whole bench
        out.error = f"{type(e).__name__}: {e}"
    out.latency_ms = (time.perf_counter() - started) * 1000
    return out


async def _call(
    surface: Surface, principal: Principal, block: Any, human: str, out: Transcript
) -> dict[str, Any]:
    args = dict(block.input) if isinstance(block.input, dict) else {}
    reply = await surface.call(principal, block.name, args)
    while reply.approval is not None:  # the human channel: same for every arm
        decision = human == "approve"
        out.approvals.append(
            {
                "capability": reply.approval.request.capability,
                "reason": reply.approval.request.reason,
                "approved": decision,
            }
        )
        reply = await surface.resolve(
            principal, reply.approval, decision, by=f"{principal.user} (simulated human)"
        )
    if reply.run_id and reply.run_id not in out.run_ids:
        out.run_ids.append(reply.run_id)
    out.tool_calls.append({"tool": block.name, "args": args, "is_error": reply.is_error})
    return {
        "type": "tool_result",
        "tool_use_id": block.id,
        "content": json.dumps(reply.payload, ensure_ascii=False, default=str),
        "is_error": reply.is_error,
    }


__all__ = ["SYSTEM", "Arm", "Transcript", "Usage", "api_tools", "run_agent"]
