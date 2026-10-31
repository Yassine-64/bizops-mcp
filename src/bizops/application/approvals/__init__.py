"""Approval requests: a single-use nonce per pause, only its hash persisted, resolved atomically by the
journal.

The nonce goes to the human-facing channel (the MCP client's approval prompt, or `bizops approve`), never into
anything the model reads. Issuing a new request for a step supersedes the old one, so at most one nonce per
step is ever valid."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from bizops.application.telemetry import span
from bizops.domain.models.run import ApprovalOutcome, ApprovalRequest, Run, Step
from bizops.domain.ports import Journal


def nonce_hash(nonce: str) -> str:
    return hashlib.sha256(nonce.encode()).hexdigest()


@dataclass(frozen=True)
class IssuedApproval:
    request: ApprovalRequest
    nonce: str  # hand to the human channel only


class Approvals:
    def __init__(
        self, journal: Journal, now: Callable[[], datetime], ttl: timedelta = timedelta(hours=1)
    ) -> None:
        self.journal = journal
        self.now = now
        self.ttl = ttl

    def issue(self, run: Run, step: Step, reason: str) -> IssuedApproval:
        created = self.now()
        req = ApprovalRequest(
            id=f"apr_{secrets.token_hex(6)}",
            run_id=run.id,
            step_id=step.id,
            tenant=run.tenant,
            capability=step.capability,
            reason=reason,
            created_at=created,
            expires_at=created + self.ttl,
        )
        nonce = secrets.token_urlsafe(24)
        with span("bizops.approval.issue", run_id=run.id, step_id=step.id, capability=step.capability):
            self.journal.create_approval(req, nonce_hash(nonce))
        return IssuedApproval(req, nonce)

    def resolve(
        self, nonce: str, *, run_id: str, step_id: str, tenant: str, approve: bool, by: str
    ) -> ApprovalOutcome:
        with span("bizops.approval.resolve", run_id=run_id, step_id=step_id, channel="client") as s:
            outcome = self._resolve(nonce_hash(nonce), run_id, step_id, tenant, approve, by)
            s.set_attribute("bizops.outcome", str(outcome))
            return outcome

    def _resolve(
        self, digest: str | None, run_id: str, step_id: str, tenant: str, approve: bool, by: str
    ) -> ApprovalOutcome:
        return self.journal.resolve_approval(
            nonce_hash=digest,
            run_id=run_id,
            step_id=step_id,
            tenant=tenant,
            approve=approve,
            by=by,
            now=self.now(),
        )

    def resolve_as_operator(
        self, *, run_id: str, step_id: str, tenant: str, approve: bool, by: str
    ) -> ApprovalOutcome:
        """`bizops approve`: local shell access is the credential, so no nonce is needed."""
        with span("bizops.approval.resolve", run_id=run_id, step_id=step_id, channel="operator") as s:
            outcome = self._resolve(None, run_id, step_id, tenant, approve, by)
            s.set_attribute("bizops.outcome", str(outcome))
            return outcome


__all__ = ["Approvals", "IssuedApproval", "nonce_hash"]
