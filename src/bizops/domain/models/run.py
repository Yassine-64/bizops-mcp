"""Durable runs: an ordered list of steps, each a capability call with a journaled lifecycle.

Step lifecycle:
    pending ─▶ running ─▶ done
       │          ├────▶ failed | delivery_uncertain
       │          └────▶ (crash) running, resumed by the next execute
       ├─▶ awaiting_approval ─▶ approved ─▶ running …
       │                    └─▶ declined
       └─▶ denied
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    DONE = "done"
    FAILED = "failed"
    DENIED = "denied"
    DECLINED = "declined"
    DELIVERY_UNCERTAIN = "delivery_uncertain"  # a send whose outcome cannot be proven; never re-sent

    @property
    def terminal(self) -> bool:
        return self in TERMINAL


TERMINAL = {
    StepStatus.DONE,
    StepStatus.FAILED,
    StepStatus.DENIED,
    StepStatus.DECLINED,
    StepStatus.DELIVERY_UNCERTAIN,
}


class RunStatus(StrEnum):
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Step:
    id: str
    run_id: str
    seq: int
    capability: str
    args: dict[str, Any]
    status: StepStatus = StepStatus.PENDING
    operation_id: str | None = (
        None  # minted by the server at first dispatch of a write; reused by every retry
    )
    decision: str | None = None  # allow | approve | deny
    reason: str | None = None
    rule: str | None = None
    attempts: int = 0
    result: Any = None
    error: str | None = None
    ms: float = 0.0
    identity: str = ""  # the effect key: same capability + same identity = same effect (duplicate guard)


@dataclass
class Run:
    id: str
    tenant: str
    user: str
    status: RunStatus
    created_at: datetime
    steps: list[Step] = field(default_factory=list)

    def owned_by(self, tenant: str, user: str) -> bool:
        return self.tenant == tenant and self.user == user

    def next_step(self) -> Step | None:
        return next((s for s in self.steps if not s.status.terminal), None)


class ApprovalOutcome(StrEnum):
    APPROVED = "approved"
    DECLINED = "declined"
    NOT_FOUND = "not_found"  # no pending request matches this nonce
    WRONG_BINDING = "wrong_binding"  # nonce belongs to another run, step or tenant
    EXPIRED = "expired"
    ALREADY_USED = "already_used"

    @property
    def resolved(self) -> bool:
        return self in (ApprovalOutcome.APPROVED, ApprovalOutcome.DECLINED)


@dataclass(frozen=True)
class ApprovalRequest:
    id: str
    run_id: str
    step_id: str
    tenant: str
    capability: str
    reason: str
    created_at: datetime
    expires_at: datetime


__all__ = ["TERMINAL", "ApprovalOutcome", "ApprovalRequest", "Run", "RunStatus", "Step", "StepStatus"]
