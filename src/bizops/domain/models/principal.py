"""Who is acting."""

from __future__ import annotations

from dataclasses import dataclass, field


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


__all__ = ["Principal"]
