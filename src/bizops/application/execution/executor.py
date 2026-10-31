"""The durable executor: the only component that starts or continues side effects.

A run is a journaled list of steps. Each step is decided by the policy, paused for a human when the policy
says so, and dispatched with a write-ahead journal entry carrying a server-minted operation id. The model
never sees operation ids, nonces or connector errors beyond a short structured message.

`durable=False` is the ablation's naive client: same policy and approvals, but every retry of a write mints
a fresh operation id and earlier effects are not remembered. That is how real agents double-refund."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from bizops.application.approvals import Approvals, IssuedApproval
from bizops.application.execution.dispatch import Dispatcher
from bizops.application.telemetry import annotate, event, span
from bizops.domain.exceptions import ConnectorError, CredentialExpired
from bizops.domain.models import Principal, Risk
from bizops.domain.models.capability import Capability, Decision, Effect
from bizops.domain.models.run import Run, RunStatus, Step, StepStatus
from bizops.domain.ports import Journal
from bizops.domain.services.canonical import canonical_args

MAX_STEPS = 10
DUPLICATE_GUARDED = (Risk.FINANCIAL, Risk.DESTRUCTIVE)


class RunNotFound(LookupError):
    """Unknown run, or a run of another principal: the two are indistinguishable on purpose."""


class InvalidPlan(ValueError):
    pass


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    backoff_s: float = 0.2
    max_backoff_s: float = 2.0


@dataclass
class RunView:
    """What a surface renders. `approval` carries the nonce for the human channel; `to_model()` drops it."""

    run: Run
    approval: IssuedApproval | None = None

    def to_model(self, max_result_chars: int = 6_000) -> dict[str, Any]:
        steps = []
        for s in self.run.steps:
            entry: dict[str, Any] = {"step": s.seq, "capability": s.capability, "status": s.status}
            if s.status is StepStatus.DONE:
                entry["result"] = _clip(s.result, max_result_chars)
            elif s.error or s.reason:
                entry["detail"] = s.error or s.reason
            steps.append(entry)
        out: dict[str, Any] = {"run_id": self.run.id, "status": self.run.status, "steps": steps}
        if self.approval:
            out["awaiting_approval"] = {
                "step": next(s.seq for s in self.run.steps if s.id == self.approval.request.step_id),
                "capability": self.approval.request.capability,
                "reason": self.approval.request.reason,
                "next": "a human has been asked; once they decide, call execute(run_id) to continue",
            }
        return out


def _clip(value: Any, limit: int) -> Any:
    import json

    text = json.dumps(value, default=str)
    if len(text) <= limit:
        return value
    return {"truncated": True, "preview": text[:limit], "hint": "narrow the query or lower max_rows"}


@dataclass
class Executor:
    dispatcher: Dispatcher
    journal: Journal
    approvals: Approvals
    now: Callable[[], datetime]
    durable: bool = True
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    # ---- entry points --------------------------------------------------------------------------

    async def start(self, principal: Principal, steps: list[dict[str, Any]]) -> RunView:
        if not steps:
            raise InvalidPlan("steps must not be empty")
        if len(steps) > MAX_STEPS:
            raise InvalidPlan(f"at most {MAX_STEPS} steps per run")
        run_id = f"run_{secrets.token_hex(6)}"
        run = Run(run_id, principal.tenant, principal.user, RunStatus.RUNNING, self.now())
        for i, raw in enumerate(steps, start=1):
            if not isinstance(raw, dict) or not isinstance(raw.get("capability"), str):
                raise InvalidPlan(f"step {i} needs a capability name")
            args = raw.get("args") or {}
            if not isinstance(args, dict):
                raise InvalidPlan(f"step {i}: args must be an object")
            step = Step(f"{run_id}_s{i}", run_id, i, raw["capability"], args)
            bound = self.dispatcher.registry.get(step.capability)
            step.identity = bound.capability.effect_key(args) if bound else canonical_args(args)
            run.steps.append(step)
        self.journal.create_run(run)
        with span(
            "bizops.run", run_id=run_id, tenant=run.tenant, user=run.user, steps=len(run.steps), entry="start"
        ):
            return await self._traced_advance(principal, run)

    async def resume(self, principal: Principal, run_id: str) -> RunView:
        run = self._owned(principal, run_id)
        with span(
            "bizops.run",
            run_id=run_id,
            tenant=run.tenant,
            user=run.user,
            steps=len(run.steps),
            entry="resume",
        ):
            return await self._traced_advance(principal, run)

    async def _traced_advance(self, principal: Principal, run: Run) -> RunView:
        view = await self._advance(principal, run)
        annotate(status=str(view.run.status), awaiting_approval=view.approval is not None)
        return view

    def inspect(self, principal: Principal, run_id: str) -> RunView:
        """Read-only: never dispatches, never issues or resolves approvals."""
        return RunView(self._owned(principal, run_id))

    def _owned(self, principal: Principal, run_id: str) -> Run:
        run = self.journal.get_run(run_id)
        if run is None or not run.owned_by(principal.tenant, principal.user):
            raise RunNotFound(f"no run {run_id}")
        return run

    # ---- the state machine ---------------------------------------------------------------------

    async def _advance(self, principal: Principal, run: Run) -> RunView:
        for step in run.steps:
            if step.status is StepStatus.DONE:
                continue
            if step.status.terminal:  # declined, denied, failed, uncertain: nothing after it may run
                return self._finish(run, RunStatus.FAILED)
            with span("bizops.step", run_id=run.id, seq=step.seq, capability=step.capability) as s:
                stopped = await self._advance_step(principal, run, step)
                s.set_attributes(
                    {
                        "bizops.status": str(step.status),
                        "bizops.decision": step.decision or "",
                        "bizops.rule": step.rule or "",
                        "bizops.attempts": step.attempts,
                    }
                )
            if stopped is not None:
                return stopped
        return self._finish(run, RunStatus.DONE)

    async def _advance_step(self, principal: Principal, run: Run, step: Step) -> RunView | None:
        """Decide, pause or dispatch one step. Returns a view when the run stops here, None to continue."""
        if step.status is StepStatus.AWAITING_APPROVAL:
            return self._pause(run, step)
        if step.status is StepStatus.PENDING:
            decision = self._decide(principal, step)
            step.decision, step.reason, step.rule = decision.effect, decision.reason, decision.rule
            if decision.effect is Effect.DENY:
                return self._stop(run, step, StepStatus.DENIED)
            if decision.effect is Effect.APPROVE:
                step.status = StepStatus.AWAITING_APPROVAL
                self.journal.save_step(step)
                return self._pause(run, step)
        if not await self._dispatch(principal, run, step):
            return self._finish(run, RunStatus.FAILED)
        return None

    def _decide(self, principal: Principal, step: Step) -> Decision:
        decision = self.dispatcher.decide(principal, step.capability, step.args)
        bound = self.dispatcher.registry.get(step.capability)
        if decision.effect is not Effect.ALLOW or bound is None or not self.durable:
            return decision
        if bound.capability.risk in DUPLICATE_GUARDED:
            earlier = [
                s
                for s in self.journal.completed_like(
                    principal.tenant,
                    principal.user,
                    step.capability,
                    step.identity or canonical_args(step.args),
                )
                if s.id != step.id
            ]
            if earlier:
                return Decision(
                    Effect.APPROVE,
                    f"the same {step.capability} with the same arguments already ran in {earlier[0].run_id}; "
                    "a human must confirm the repeat is intended",
                    "duplicate",
                )
        return decision

    async def _dispatch(self, principal: Principal, run: Run, step: Step) -> bool:
        bound = self.dispatcher.registry.get(step.capability)
        assert bound is not None
        cap = bound.capability
        recovering = step.status is StepStatus.RUNNING  # a crash or lost response left it in flight
        if recovering and not self._may_redispatch(cap):
            return self._uncertain(step, cap)
        decision = Decision(Effect(step.decision or Effect.ALLOW), step.reason or "", step.rule or "")
        refreshed = False
        while True:
            if cap.is_write and (step.operation_id is None or not self.durable):
                step.operation_id = f"op_{secrets.token_hex(8)}"  # naive client: a new id per attempt
            step.status, step.attempts = StepStatus.RUNNING, step.attempts + 1
            self.journal.save_step(step)  # write-ahead: in flight, with its operation id, before the call
            try:
                result = await self.dispatcher.execute_allowed(
                    principal, step.capability, step.args, step.operation_id, decision
                )
            except CredentialExpired as e:
                event("credential_refresh", attempt=step.attempts, final=refreshed)
                if refreshed:
                    return self._fail(step, e)
                refreshed = True  # ponytail: the connector refreshes on its next call; no token store here
                continue
            except ConnectorError as e:
                if not e.retryable or step.attempts >= self.retry.attempts:
                    if cap.is_write and e.retryable:
                        return self._uncertain(step, cap, e) if self.durable else self._fail(step, e)
                    return self._fail(step, e)
                if cap.is_write and self.durable and not self._may_redispatch(cap):
                    return self._uncertain(step, cap, e)
                delay = min(self.retry.backoff_s * 2 ** (step.attempts - 1), self.retry.max_backoff_s)
                event("retry", error=type(e).__name__, attempt=step.attempts, delay_s=delay)
                await self.sleep(delay)
                continue
            step.status, step.result, step.ms, step.error = StepStatus.DONE, result.output, result.ms, None
            self.journal.save_step(step)
            return True

    def _may_redispatch(self, cap: Capability) -> bool:
        """After an unknown outcome only reads and idempotent writes run again (naive clients always do)."""
        return not cap.is_write or not self.durable or (cap.idempotent and not cap.send)

    def _uncertain(self, step: Step, cap: Capability, e: Exception | None = None) -> bool:
        why = f" ({type(e).__name__}: {e})" if e else ""
        if cap.send:
            step.status = StepStatus.DELIVERY_UNCERTAIN
            step.error = f"the message may or may not have been delivered{why}; it will not be sent again"
        else:
            step.status = StepStatus.FAILED
            step.error = f"the outcome of this write is unknown{why}; check its effect before retrying"
        self.journal.save_step(step)
        return False

    def _fail(self, step: Step, e: Exception) -> bool:
        step.status, step.error = StepStatus.FAILED, f"{type(e).__name__}: {e}"
        self.journal.save_step(step)
        return False

    def _pause(self, run: Run, step: Step) -> RunView:
        self.journal.set_run_status(run.id, RunStatus.AWAITING_APPROVAL)
        run.status = RunStatus.AWAITING_APPROVAL
        return RunView(run, self.approvals.issue(run, step, step.reason or "approval required"))

    def _stop(self, run: Run, step: Step, status: StepStatus) -> RunView:
        step.status = status
        self.journal.save_step(step)
        return self._finish(run, RunStatus.FAILED)

    def _finish(self, run: Run, status: RunStatus) -> RunView:
        self.journal.set_run_status(run.id, status)
        run.status = status
        return RunView(run)


__all__ = ["Executor", "InvalidPlan", "RetryPolicy", "RunNotFound", "RunView"]
