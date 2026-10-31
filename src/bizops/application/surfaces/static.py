"""The baseline: every capability is its own tool, as a typical MCP server would expose it. Each call is a
one-step run through the same executor, so policy, approvals and the journal still apply."""

from __future__ import annotations

from typing import Any

from bizops.application.catalogue import Registry
from bizops.application.execution.executor import Executor
from bizops.application.surfaces import ExecutorSurface, ToolReply, ToolSpec
from bizops.domain.models import Principal
from bizops.domain.models.capability import Capability, PolicyGates
from bizops.domain.services.signature import compact_signature, qualified_name, tool_name


def tool_description(cap: Capability, gates: PolicyGates) -> str:
    tags = compact_signature(cap, gates).rsplit("  [", 1)[-1].rstrip("]")
    return f"{cap.description} [{tags}]"


class StaticSurface(ExecutorSurface):
    name = "static"

    def __init__(self, registry: Registry, executor: Executor, gates: PolicyGates) -> None:
        super().__init__(executor)
        self.registry = registry
        self.gates = gates

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(tool_name(c.name), tool_description(c, self.gates), c.input_schema())
            for c in self.registry.capabilities()
        ]

    async def call(self, principal: Principal, tool: str, args: dict[str, Any]) -> ToolReply:
        name = qualified_name(tool)
        if self.registry.get(name) is None:
            return ToolReply.error(f"unknown tool {tool}")
        return await self._start(principal, [{"capability": name, "args": args}])


__all__ = ["StaticSurface", "tool_description"]
