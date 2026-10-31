"""One capability call, policy-checked and executed against the principal's tenant store.

This is the unit the durable executor journals. On its own (no journal) it is the "scopes only" or
"approvals but no journal" control plane the ablation measures."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from bizops.application.catalogue import Registry
from bizops.application.telemetry import span
from bizops.domain.models import Principal
from bizops.domain.models.capability import CallContext, Decision, Effect, PolicyGates
from bizops.domain.ports import TenantStores
from bizops.domain.services import policy

MAX_RESULT_CHARS = 12_000  # ponytail: a flat cap on serialized output; pagination is the real limit


@dataclass
class CallResult:
    capability: str
    decision: Decision
    output: Any = None
    error: str | None = None
    ms: float = 0.0
    executed: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


class Dispatcher:
    def __init__(
        self, registry: Registry, stores: TenantStores, gates: PolicyGates, clock: Callable[[], date]
    ) -> None:
        self.registry = registry
        self.stores = stores
        self.gates = gates
        self.clock = clock

    def decide(self, principal: Principal, name: str, args: dict[str, Any]) -> Decision:
        bound = self.registry.get(name)
        d = (
            policy.unknown(name)
            if bound is None
            else policy.decide(principal, bound.capability, args, self.gates)
        )
        with span(
            "bizops.policy",
            capability=name,
            risk=str(bound.capability.risk) if bound else None,
            effect=str(d.effect),
            rule=d.rule,
        ):
            return d

    async def run(
        self, principal: Principal, name: str, args: dict[str, Any], operation_id: str | None = None
    ) -> CallResult:
        """Execute only when the policy allows. An `approve` decision is returned, not executed: the caller
        (the durable executor) owns the pause. Connector errors propagate typed; see domain.exceptions."""
        decision = self.decide(principal, name, args)
        if decision.effect is not Effect.ALLOW:
            return CallResult(name, decision)
        return await self.execute_allowed(principal, name, args, operation_id, decision)

    async def execute_allowed(
        self,
        principal: Principal,
        name: str,
        args: dict[str, Any],
        operation_id: str | None,
        decision: Decision,
    ) -> CallResult:
        bound = self.registry.get(name)
        assert bound is not None
        started = time.perf_counter()
        with (
            span(
                "bizops.connector",
                connector=bound.capability.connector,
                capability=name,
                write=bound.capability.is_write,
            ),
            self.stores.open(principal.tenant) as store,
        ):
            ctx = CallContext(principal=principal, store=store, today=self.clock(), operation_id=operation_id)
            output = await bound.handler(ctx, **args)
        return CallResult(
            name, decision, output=output, ms=(time.perf_counter() - started) * 1000, executed=True
        )


__all__ = ["MAX_RESULT_CHARS", "CallResult", "Dispatcher"]
