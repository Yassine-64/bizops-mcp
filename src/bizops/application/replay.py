"""Replay a recorded run through the real executor and policy, against the connector results it recorded.

It answers "would today's control plane make the same decisions on this exact trajectory?": policy drift, a
changed risk gate, a state-machine regression or a tampered journal all show up as divergences. It does not
replay the model (the model's choices are the recorded steps) and never touches tenant data: connectors are
replaced by the recorded outputs, and approvals are re-applied as the recorded human decisions."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from bizops.application.approvals import Approvals
from bizops.application.catalogue import Registry
from bizops.application.execution.dispatch import Dispatcher
from bizops.application.execution.executor import Executor, RetryPolicy
from bizops.domain.exceptions import ConnectorError, Timeout
from bizops.domain.models import Principal
from bizops.domain.models.capability import PolicyGates
from bizops.domain.models.run import Run, Step, StepStatus
from bizops.domain.ports import Journal


@dataclass(frozen=True)
class Divergence:
    step: int
    field: str
    recorded: Any
    replayed: Any


@dataclass
class ReplayReport:
    run_id: str
    steps: int
    divergences: list[Divergence] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.divergences


_NO_RETRY_WAIT = RetryPolicy(backoff_s=0.0)


class _NoStores:
    """Replay never opens tenant data: handlers return recorded outputs."""

    @contextmanager
    def open(self, tenant: str) -> Iterator[None]:
        yield None


class _History:
    """The replay journal, plus the principal's steps from runs recorded before this one, so history-dependent
    rules (the duplicate guard) see what they saw the first time."""

    def __init__(self, inner: Journal, source: Journal, run: Run) -> None:
        self.inner, self.source, self.run = inner, source, run

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def completed_like(self, tenant: str, user: str, capability: str, canonical_args: str) -> list[Step]:
        earlier = []
        for s in self.source.completed_like(tenant, user, capability, canonical_args):
            prior = self.source.get_run(s.run_id)
            if s.run_id != self.run.id and prior is not None and prior.created_at < self.run.created_at:
                earlier.append(s)
        return earlier + self.inner.completed_like(tenant, user, capability, canonical_args)


def _recorded_handlers(registry: Registry, run: Run) -> Registry:
    """Each capability answers with the outputs (or failures) it produced in the recorded run, in order."""
    queues: dict[str, deque[Step]] = defaultdict(deque)
    for s in run.steps:
        if s.status in (StepStatus.DONE, StepStatus.FAILED, StepStatus.DELIVERY_UNCERTAIN):
            queues[s.capability].append(s)
    replayed = registry.copy()
    for capability, queue in queues.items():

        async def handler(ctx: Any, _q: deque[Step] = queue, **args: Any) -> Any:
            step = _q.popleft()
            if step.status is StepStatus.DONE:
                return step.result
            if step.status is StepStatus.DELIVERY_UNCERTAIN or "unknown" in (step.error or ""):
                raise Timeout("recorded: no response")
            raise ConnectorError(f"recorded: {step.error}")

        replayed = replayed.with_handler(capability, handler)
    return replayed


class Replayer:
    def __init__(
        self,
        source: Journal,
        registry: Registry,
        gates: PolicyGates,
        principal_of: Callable[[str, str], Principal | None],
        scratch_journal: Callable[[], Journal],
        clock: Callable[[], date],
        now: Callable[[], datetime],
    ) -> None:
        self.source, self.registry, self.gates = source, registry, gates
        self.principal_of, self.scratch_journal, self.clock, self.now = (
            principal_of,
            scratch_journal,
            clock,
            now,
        )

    async def replay(self, run_id: str) -> ReplayReport:
        run = self.source.get_run(run_id)
        if run is None:
            raise LookupError(f"no run {run_id}")
        principal = self.principal_of(run.tenant, run.user)
        if principal is None:
            raise LookupError(f"no principal {run.tenant}/{run.user}")
        journal = _History(self.scratch_journal(), self.source, run)
        dispatcher = Dispatcher(_recorded_handlers(self.registry, run), _NoStores(), self.gates, self.clock)
        approvals = Approvals(journal, self.now)
        executor = Executor(dispatcher, journal, approvals, self.now, retry=_NO_RETRY_WAIT, sleep=_instant)

        view = await executor.start(
            principal, [{"capability": s.capability, "args": s.args} for s in run.steps]
        )
        while view.approval is not None:
            req = view.approval.request
            seq = next(s.seq for s in view.run.steps if s.id == req.step_id)
            recorded = run.steps[seq - 1]
            if recorded.status in (StepStatus.AWAITING_APPROVAL, StepStatus.PENDING):
                break  # the recorded run was still waiting here
            approve = recorded.status is not StepStatus.DECLINED
            approvals.resolve_as_operator(
                run_id=req.run_id, step_id=req.step_id, tenant=run.tenant, approve=approve, by="replay"
            )
            view = await executor.resume(principal, view.run.id)
        return ReplayReport(run_id, len(run.steps), _compare(run.steps, view.run.steps))


def _compare(recorded: list[Step], replayed: list[Step]) -> list[Divergence]:
    out = []
    for a, b in zip(recorded, replayed, strict=True):
        for name in ("status", "decision", "rule"):
            if getattr(a, name) != getattr(b, name):
                out.append(Divergence(a.seq, name, getattr(a, name), getattr(b, name)))
        if a.status is StepStatus.DONE and _canon(a.result) != _canon(b.result):
            out.append(Divergence(a.seq, "result", a.result, b.result))
    return out


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


async def _instant(_: float) -> None:
    return None


__all__ = ["Divergence", "ReplayReport", "Replayer"]
