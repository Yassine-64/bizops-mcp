"""Ports: what the application needs from the outside world, declared where the application can import it.
A boundary gets a port when an inner layer must call an outer one (the dependency rule) or when it has more
than one implementation."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from bizops.domain.models.run import ApprovalOutcome, ApprovalRequest, Run, RunStatus, Step


@runtime_checkable
class TenantStores(Protocol):
    """Opens the store of one tenant. Isolation is the adapter's job: a store opened for tenant A
    cannot resolve tenant B's ids."""

    def open(self, tenant: str) -> AbstractContextManager[Any]: ...


class Journal(Protocol):
    """Durable run state. Every method commits before returning; `resolve_approval` is one transaction."""

    def create_run(self, run: Run) -> None: ...
    def get_run(self, run_id: str) -> Run | None: ...
    def save_step(self, step: Step) -> None: ...
    def set_run_status(self, run_id: str, status: RunStatus) -> None: ...

    def completed_like(self, tenant: str, user: str, capability: str, canonical_args: str) -> list[Step]:
        """Earlier steps of this principal, same capability and arguments, that may have taken effect."""
        ...

    def create_approval(self, request: ApprovalRequest, nonce_hash: str) -> None: ...
    def pending_approval(self, run_id: str, step_id: str) -> ApprovalRequest | None: ...

    def resolve_approval(
        self,
        *,
        nonce_hash: str | None,
        run_id: str,
        step_id: str,
        tenant: str,
        approve: bool,
        by: str,
        now: datetime,
    ) -> ApprovalOutcome:
        """Atomically: find the request, check nonce, binding, tenant and expiry, mark it consumed, and move
        the step to approved or declined. `nonce_hash=None` is the operator path (`bizops approve`)."""
        ...


__all__ = ["Journal", "TenantStores"]
