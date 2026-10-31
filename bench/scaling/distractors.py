"""Register catalogue-only distractors next to the real capabilities, for the large-catalogue arm of Table A.

A distractor carries no scope (so policy never gives it away with a denial) and, if called, answers like a
connected system with nothing for this tenant: a recoverable error that costs the agent a call and tokens,
which is exactly the price of picking the wrong tool."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from bench.scaling.catalogue import synthetic_catalogue
from bizops.application.catalogue import Registry
from bizops.domain.exceptions import NotFound


def with_distractors(registry: Registry, size: int) -> Registry:
    """A copy of `registry` padded to `size` capabilities, in a fixed order shared by every arm."""
    extra = max(0, size - len(registry))
    if not extra:
        return registry
    padded = registry.copy()
    for cap in synthetic_catalogue()[:extra]:
        system = cap.connector

        async def nothing(ctx: Any, _system: str = system, **args: Any) -> Any:
            raise NotFound(f"{_system} has no records for this tenant")

        padded.add(replace(cap, scopes=frozenset()), nothing)
    return padded


__all__ = ["with_distractors"]
