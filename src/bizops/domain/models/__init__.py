"""Pure value types shared by every layer. No I/O, no framework types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Risk(StrEnum):
    READ = "read"
    WRITE = "write"
    FINANCIAL = "financial"
    DESTRUCTIVE = "destructive"
    ADMIN = "admin"


@dataclass(frozen=True)
class Principal:
    """Who is acting. Built server-side from a credential, never from anything the model says."""

    tenant: str
    user: str
    roles: frozenset[str] = field(default_factory=frozenset)
    scopes: frozenset[str] = field(default_factory=frozenset)

    @property
    def id(self) -> str:
        return f"{self.tenant}/{self.user}"


__all__ = ["Principal", "Risk"]
