"""Agent-facing surfaces: the interface under test in Table A. Each surface turns tool calls into executor
runs; the executor, policy, approvals and connectors behind them are identical, so only the interface varies.

Transports (the MCP server, the bench harness) consume `Surface` and own the human channel: when a reply
carries an approval, they get a decision from a human and call `resolve`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from bizops.application.approvals import IssuedApproval
from bizops.application.execution.executor import Executor, InvalidPlan, RunNotFound, RunView
from bizops.domain.models import Principal
from bizops.domain.models.run import ApprovalOutcome


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class ToolReply:
    payload: dict[str, Any]  # what the model reads
    is_error: bool = False
    approval: IssuedApproval | None = None  # for the human channel only; never shown to the model
    run_id: str | None = None
    approval_prompt: str | None = None  # what the human is asked: the exact call and the reason

    @classmethod
    def error(cls, message: str) -> ToolReply:
        return cls({"error": message}, is_error=True)

    @classmethod
    def of(cls, view: RunView) -> ToolReply:
        prompt = None
        if view.approval:
            step = next(s for s in view.run.steps if s.id == view.approval.request.step_id)
            shown = json.dumps(step.args, ensure_ascii=False, default=str)
            prompt = (
                f"Approve {step.capability}({shown})?\nWhy this needs a human: {view.approval.request.reason}"
            )
        return cls(view.to_model(), approval=view.approval, run_id=view.run.id, approval_prompt=prompt)


class Surface(Protocol):
    name: str

    def tools(self) -> list[ToolSpec]: ...
    async def call(self, principal: Principal, tool: str, args: dict[str, Any]) -> ToolReply: ...
    async def resolve(
        self, principal: Principal, approval: IssuedApproval, approve: bool, by: str
    ) -> ToolReply: ...
    async def resolve_state(
        self, principal: Principal, run_id: str, step_id: str, nonce: str, approve: bool, by: str
    ) -> ToolReply: ...


class ExecutorSurface:
    """Shared behaviour: resolving an approval and continuing the run, identically for every surface."""

    name = "base"

    def __init__(self, executor: Executor) -> None:
        self.executor = executor

    async def resolve(
        self, principal: Principal, approval: IssuedApproval, approve: bool, by: str
    ) -> ToolReply:
        req = approval.request
        return await self.resolve_state(principal, req.run_id, req.step_id, approval.nonce, approve, by)

    async def resolve_state(
        self, principal: Principal, run_id: str, step_id: str, nonce: str, approve: bool, by: str
    ) -> ToolReply:
        """Apply a human decision carried back by a transport, then continue the run from that step."""
        outcome = self.executor.approvals.resolve(
            nonce, run_id=run_id, step_id=step_id, tenant=principal.tenant, approve=approve, by=by
        )
        if not outcome.resolved:
            return ToolReply.error(f"approval not applied: {outcome}")
        try:
            view = await self.executor.resume(principal, run_id)
        except RunNotFound as e:
            return ToolReply.error(str(e))
        reply = ToolReply.of(view)
        if outcome is ApprovalOutcome.DECLINED:
            reply.payload["note"] = "a human declined this step; it was not executed"
        return reply

    async def _start(self, principal: Principal, steps: list[dict[str, Any]]) -> ToolReply:
        try:
            return ToolReply.of(await self.executor.start(principal, steps))
        except InvalidPlan as e:
            return ToolReply.error(str(e))


__all__ = ["ExecutorSurface", "Surface", "ToolReply", "ToolSpec"]
