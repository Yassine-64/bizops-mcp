"""Tenant databases and authentication. A credential resolves to a principal; the principal's tenant picks
the SQLite file. Nothing the model sends can change either."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from bizops.domain.models import Principal
from bizops.domain.services.roles import principal_for
from bizops.infrastructure.db import connection as db


class TenantDatabases:
    """`TenantStores` over one SQLite file per tenant, plus bearer-token authentication."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def exists(self, tenant: str) -> bool:
        return (self.data_dir / f"{tenant}.db").exists()

    def connect(self, tenant: str) -> sqlite3.Connection:
        if not self.exists(tenant):
            raise LookupError(f"no such tenant: {tenant}")
        return db.connect(self.data_dir, tenant)

    @contextmanager
    def open(self, tenant: str) -> Iterator[sqlite3.Connection]:
        conn = self.connect(tenant)
        try:
            yield conn
        finally:
            conn.close()

    def authenticate(self, tenant: str, token: str) -> Principal | None:
        """Bearer token -> principal, from the tenant's principals table. Roles and scopes come from here."""
        if not self.exists(tenant):
            return None
        conn = self.connect(tenant)
        try:
            row = db.one(conn, "SELECT user, roles FROM principals WHERE token_hash = ?", (_digest(token),))
        finally:
            conn.close()
        if row is None:
            return None
        return principal_for(tenant, str(row["user"]), set(str(row["roles"]).split(",")))

    def tenants(self) -> list[str]:
        return sorted(p.stem for p in self.data_dir.glob("*.db") if p.stem != "journal")

    def authenticate_token(self, token: str) -> Principal | None:
        """Bearer token -> principal, whichever tenant issued it. Tokens are unique across tenants."""
        for tenant in self.tenants():
            principal = self.authenticate(tenant, token)
            if principal is not None:
                return principal
        return None

    def issue_token(self, tenant: str, user: str) -> str:
        """A new random token for one principal. Only its SHA-256 is stored, and issuing again revokes the old
        one. The plaintext is returned once and never written anywhere by bizops."""
        token = f"bo_{secrets.token_urlsafe(32)}"
        self._set_token(tenant, user, _digest(token))
        return token

    def revoke_token(self, tenant: str, user: str) -> None:
        self._set_token(tenant, user, None)

    def _set_token(self, tenant: str, user: str, digest: str | None) -> None:
        from datetime import UTC, datetime

        conn = self.connect(tenant)
        try:
            changed = conn.execute(
                "UPDATE principals SET token_hash = ?, token_issued_at = ? WHERE user = ?",
                (digest, datetime.now(UTC).isoformat() if digest else None, user),
            ).rowcount
        finally:
            conn.close()
        if changed != 1:
            raise LookupError(f"no principal {tenant}/{user}")

    def principal(self, tenant: str, user: str) -> Principal | None:
        """Dev convenience for stdio: name the principal instead of presenting a token."""
        conn = self.connect(tenant)
        try:
            row = db.one(conn, "SELECT roles FROM principals WHERE user = ?", (user,))
        finally:
            conn.close()
        return principal_for(tenant, user, set(str(row["roles"]).split(","))) if row else None


def _digest(token: str) -> str:
    # ponytail: plain SHA-256 is enough for 256-bit random tokens (no dictionary to attack); a slow KDF only
    # matters for human-chosen secrets
    return hashlib.sha256(token.encode()).hexdigest()


__all__ = ["TenantDatabases"]
