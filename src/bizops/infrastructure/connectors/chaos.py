"""Failure injection at the connector boundary: four named profiles, each firing once on one capability.

    rate_limit_once     429 before the call
    timeout_once        no response, and nothing committed
    credential_expired  401 before the call; the next attempt succeeds
    commit_then_drop    the write commits, then the response is lost (the client sees a timeout)

The last one is the case operation identity exists for: the caller cannot tell it apart from timeout_once."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from bizops.application.catalogue import Registry
from bizops.domain.exceptions import CredentialExpired, RateLimited, Timeout

Profile = Literal["rate_limit_once", "timeout_once", "credential_expired", "commit_then_drop"]
PROFILES: tuple[Profile, ...] = ("rate_limit_once", "timeout_once", "credential_expired", "commit_then_drop")


def _wrap(handler: Callable[..., Awaitable[Any]], profile: str, name: str) -> Callable[..., Awaitable[Any]]:
    fired = False

    async def chaotic(ctx: Any, **args: Any) -> Any:
        nonlocal fired
        if fired:
            return await handler(ctx, **args)
        fired = True
        if profile == "rate_limit_once":
            raise RateLimited(0.01, connector=name)
        if profile == "timeout_once":
            raise Timeout("no response from upstream", connector=name)
        if profile == "credential_expired":
            raise CredentialExpired("token expired", connector=name)
        await handler(ctx, **args)  # commit_then_drop: the effect happens, the answer never arrives
        raise Timeout("no response from upstream", connector=name)

    return chaotic


def with_chaos(registry: Registry, profile: Profile, capability: str) -> Registry:
    """A copy of the registry in which one capability fails once in the given way."""
    bound = registry.get(capability)
    if bound is None:
        raise KeyError(capability)
    return registry.with_handler(capability, _wrap(bound.handler, profile, capability))


__all__ = ["PROFILES", "Profile", "with_chaos"]
