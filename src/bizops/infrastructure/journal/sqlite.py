"""The run journal in one SQLite file next to the tenant stores. Control-plane state only: no tenant data
beyond what a step returned. Every write commits immediately; `resolve_approval` is a single IMMEDIATE
transaction, so a nonce can never be consumed without its step moving, or move a step twice."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from bizops.domain.models.run import (
    ApprovalOutcome,
    ApprovalRequest,
    Run,
    RunStatus,
    Step,
    StepStatus,
)
from bizops.domain.services.canonical import canonical_args

DDL = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, user TEXT NOT NULL, status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS steps (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), seq INTEGER NOT NULL,
    capability TEXT NOT NULL, args TEXT NOT NULL, canonical TEXT NOT NULL, status TEXT NOT NULL,
    operation_id TEXT, decision TEXT, reason TEXT, rule TEXT, attempts INTEGER NOT NULL DEFAULT 0,
    result TEXT, error TEXT, ms REAL NOT NULL DEFAULT 0, UNIQUE (run_id, seq)
);
CREATE INDEX IF NOT EXISTS steps_identity ON steps (capability, canonical);
CREATE TABLE IF NOT EXISTS approval_requests (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
    step_id TEXT NOT NULL REFERENCES steps(id), tenant TEXT NOT NULL, capability TEXT NOT NULL,
    reason TEXT NOT NULL, nonce_hash TEXT NOT NULL UNIQUE, status TEXT NOT NULL, created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL, consumed_at TEXT, approved_by TEXT
);
"""
# statuses after which a write may have taken effect
_MAY_HAVE_EFFECT = (StepStatus.DONE, StepStatus.RUNNING, StepStatus.DELIVERY_UNCERTAIN)


class SqliteJournal:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(DDL)

    # ---- runs and steps ------------------------------------------------------------------------

    def create_run(self, run: Run) -> None:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?)",
                (run.id, run.tenant, run.user, run.status, run.created_at.isoformat()),
            )
            for step in run.steps:
                self._insert_step(step)
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _insert_step(self, s: Step) -> None:
        self.db.execute(
            "INSERT INTO steps (id, run_id, seq, capability, args, canonical, status) VALUES (?,?,?,?,?,?,?)",
            (s.id, s.run_id, s.seq, s.capability, json.dumps(s.args), canonical_args(s.args), s.status),
        )

    def get_run(self, run_id: str) -> Run | None:
        row = self.db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        steps = self.db.execute("SELECT * FROM steps WHERE run_id = ? ORDER BY seq", (run_id,)).fetchall()
        return Run(
            id=row["id"],
            tenant=row["tenant"],
            user=row["user"],
            status=RunStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            steps=[self._step(r) for r in steps],
        )

    @staticmethod
    def _step(r: sqlite3.Row) -> Step:
        return Step(
            id=r["id"],
            run_id=r["run_id"],
            seq=r["seq"],
            capability=r["capability"],
            args=json.loads(r["args"]),
            status=StepStatus(r["status"]),
            operation_id=r["operation_id"],
            decision=r["decision"],
            reason=r["reason"],
            rule=r["rule"],
            attempts=r["attempts"],
            result=json.loads(r["result"]) if r["result"] is not None else None,
            error=r["error"],
            ms=r["ms"],
        )

    def save_step(self, s: Step) -> None:
        self.db.execute(
            "UPDATE steps SET status = ?, operation_id = ?, decision = ?, reason = ?, rule = ?, "
            "attempts = ?, result = ?, error = ?, ms = ? WHERE id = ?",
            (
                s.status,
                s.operation_id,
                s.decision,
                s.reason,
                s.rule,
                s.attempts,
                json.dumps(s.result, default=str) if s.result is not None else None,
                s.error,
                s.ms,
                s.id,
            ),
        )

    def set_run_status(self, run_id: str, status: RunStatus) -> None:
        self.db.execute("UPDATE runs SET status = ? WHERE id = ?", (status, run_id))

    def completed_like(self, tenant: str, user: str, capability: str, canonical: str) -> list[Step]:
        marks = ",".join("?" * len(_MAY_HAVE_EFFECT))
        rows = self.db.execute(
            "SELECT s.* FROM steps s JOIN runs r ON r.id = s.run_id WHERE r.tenant = ? AND r.user = ? "
            f"AND s.capability = ? AND s.canonical = ? AND s.status IN ({marks})",
            (tenant, user, capability, canonical, *_MAY_HAVE_EFFECT),
        ).fetchall()
        return [self._step(r) for r in rows]

    # ---- approvals -----------------------------------------------------------------------------

    def create_approval(self, req: ApprovalRequest, nonce_hash: str) -> None:
        """Supersede any pending request for the step, then insert the new one: one valid nonce per step."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "UPDATE approval_requests SET status = 'superseded' WHERE step_id = ? AND status = 'pending'",
                (req.step_id,),
            )
            self._insert_approval(req, nonce_hash)
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _insert_approval(self, req: ApprovalRequest, nonce_hash: str) -> None:
        self.db.execute(
            "INSERT INTO approval_requests (id, run_id, step_id, tenant, capability, reason, nonce_hash, "
            "status, created_at, expires_at) VALUES (?,?,?,?,?,?,?,'pending',?,?)",
            (
                req.id,
                req.run_id,
                req.step_id,
                req.tenant,
                req.capability,
                req.reason,
                nonce_hash,
                req.created_at.isoformat(),
                req.expires_at.isoformat(),
            ),
        )

    def pending_approval(self, run_id: str, step_id: str) -> ApprovalRequest | None:
        r = self.db.execute(
            "SELECT * FROM approval_requests WHERE run_id = ? AND step_id = ? AND status = 'pending' "
            "ORDER BY created_at DESC",
            (run_id, step_id),
        ).fetchone()
        return self._approval(r) if r else None

    @staticmethod
    def _approval(r: sqlite3.Row) -> ApprovalRequest:
        return ApprovalRequest(
            id=r["id"],
            run_id=r["run_id"],
            step_id=r["step_id"],
            tenant=r["tenant"],
            capability=r["capability"],
            reason=r["reason"],
            created_at=datetime.fromisoformat(r["created_at"]),
            expires_at=datetime.fromisoformat(r["expires_at"]),
        )

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
        self.db.execute("BEGIN IMMEDIATE")
        try:
            outcome = self._resolve(nonce_hash, run_id, step_id, tenant, approve, by, now)
            self.db.execute("COMMIT")
            return outcome
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _resolve(
        self,
        nonce_hash: str | None,
        run_id: str,
        step_id: str,
        tenant: str,
        approve: bool,
        by: str,
        now: datetime,
    ) -> ApprovalOutcome:
        if nonce_hash is not None:
            r: Any = self.db.execute(
                "SELECT * FROM approval_requests WHERE nonce_hash = ?", (nonce_hash,)
            ).fetchone()
            if r is None:
                return ApprovalOutcome.NOT_FOUND
        else:  # operator path: the newest request for this step
            r = self.db.execute(
                "SELECT * FROM approval_requests WHERE run_id = ? AND step_id = ? ORDER BY created_at DESC",
                (run_id, step_id),
            ).fetchone()
            if r is None:
                return ApprovalOutcome.NOT_FOUND
        if (r["run_id"], r["step_id"], r["tenant"]) != (run_id, step_id, tenant):
            return ApprovalOutcome.WRONG_BINDING
        if r["status"] != "pending":
            return ApprovalOutcome.ALREADY_USED
        if now >= datetime.fromisoformat(r["expires_at"]):
            self.db.execute("UPDATE approval_requests SET status = 'expired' WHERE id = ?", (r["id"],))
            return ApprovalOutcome.EXPIRED
        status = "approved" if approve else "declined"
        self.db.execute(
            "UPDATE approval_requests SET status = ?, consumed_at = ?, approved_by = ? WHERE id = ?",
            (status, now.isoformat(), by, r["id"]),
        )
        step_status = StepStatus.APPROVED if approve else StepStatus.DECLINED
        moved = self.db.execute(
            "UPDATE steps SET status = ? WHERE id = ? AND status = ?",
            (step_status, step_id, StepStatus.AWAITING_APPROVAL),
        ).rowcount
        if moved != 1:  # the step is not waiting any more: refuse rather than approve something else
            raise RuntimeError(f"step {step_id} was not awaiting approval")
        return ApprovalOutcome.APPROVED if approve else ApprovalOutcome.DECLINED


__all__ = ["SqliteJournal"]
