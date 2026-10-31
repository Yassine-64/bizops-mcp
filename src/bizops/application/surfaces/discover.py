"""The thesis surface: three tools whatever the catalogue size.

discover  read-only; returns exact signatures of the capabilities that match a query
execute   the only tool with side effects; starts a run of one or more steps, or continues one
inspect   read-only; the state of a run
"""

from __future__ import annotations

from typing import Any

from bizops.application.catalogue import Registry
from bizops.application.discovery import CapabilityIndex
from bizops.application.execution.executor import Executor, RunNotFound
from bizops.application.surfaces import ExecutorSurface, ToolReply, ToolSpec
from bizops.application.telemetry import span
from bizops.domain.models import Principal
from bizops.domain.models.capability import PolicyGates
from bizops.domain.services.signature import discover_entry

DISCOVER = ToolSpec(
    "discover",
    "Search the business capabilities available to you (billing, CRM, support, product usage, engineering). "
    "Returns exact signatures: name(param: type, optional?: type) -> Output [risk; approval; scopes]. "
    "Read-only. Call it before execute whenever you are not sure which capability or arguments to use.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "what you need, in plain words"},
            "limit": {"type": "integer", "description": "maximum capabilities to return, default 8"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
)
EXECUTE = ToolSpec(
    "execute",
    "Run capabilities found with discover. Pass `steps` (an ordered list of {capability, args}) to start a "
    "run, or only `run_id` to continue a run after a human approved its paused step. Steps run in order and "
    "stop at the first failure, denial or approval pause. This is the only tool with side effects.",
    {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "capability": {
                            "type": "string",
                            "description": "qualified name, e.g. crm.account.get",
                        },
                        "args": {"type": "object", "description": "arguments matching its signature"},
                    },
                    "required": ["capability", "args"],
                },
                "description": "steps to run, at most 10",
            },
            "run_id": {"type": "string", "description": "continue this run instead of starting one"},
        },
        "additionalProperties": False,
    },
)
INSPECT = ToolSpec(
    "inspect",
    "Read the state of a run: status, each step's result or error, and any pending approval. Read-only; "
    "it never continues or approves anything.",
    {
        "type": "object",
        "properties": {"run_id": {"type": "string"}},
        "required": ["run_id"],
        "additionalProperties": False,
    },
)


class DiscoverSurface(ExecutorSurface):
    name = "discover"

    def __init__(self, registry: Registry, executor: Executor, gates: PolicyGates, limit: int = 8) -> None:
        super().__init__(executor)
        self.index = CapabilityIndex(registry.capabilities())
        self.gates = gates
        self.limit = limit

    def tools(self) -> list[ToolSpec]:
        return [DISCOVER, EXECUTE, INSPECT]

    async def call(self, principal: Principal, tool: str, args: dict[str, Any]) -> ToolReply:
        if tool == "discover":
            query = str(args.get("query") or "")
            limit = max(1, min(int(args.get("limit") or self.limit), 20))
            with span("bizops.discover", limit=limit, catalogue=len(self.index.caps)) as s:
                hits = self.index.search(query, limit)
                s.set_attributes({"bizops.hits": len(hits), "bizops.top": hits[0][0].name if hits else ""})
            if not hits:
                return ToolReply({"query": query, "capabilities": [], "hint": "rephrase with business terms"})
            return ToolReply(
                {"query": query, "capabilities": [discover_entry(c, self.gates) for c, _ in hits]}
            )
        if tool == "execute":
            if args.get("steps"):
                return await self._start(principal, list(args["steps"]))
            if args.get("run_id"):
                try:
                    return ToolReply.of(await self.executor.resume(principal, str(args["run_id"])))
                except RunNotFound as e:
                    return ToolReply.error(str(e))
            return ToolReply.error("pass steps to start a run, or run_id to continue one")
        if tool == "inspect":
            try:
                return ToolReply(self.executor.inspect(principal, str(args.get("run_id"))).to_model())
            except RunNotFound as e:
                return ToolReply.error(str(e))
        return ToolReply.error(f"unknown tool {tool}")


__all__ = ["DiscoverSurface"]
