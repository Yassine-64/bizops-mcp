"""Ports: what the application needs from the outside world, declared where the application can import it.
Only boundaries with more than one implementation (or a test double) get a port."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TenantStores(Protocol):
    """Opens the store of one tenant. Isolation is the adapter's job: a store opened for tenant A
    cannot resolve tenant B's ids."""

    def open(self, tenant: str) -> AbstractContextManager[Any]: ...


__all__ = ["TenantStores"]
