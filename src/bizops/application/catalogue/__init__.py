"""The capability catalogue: connectors register handlers with a decorator, the registry derives the
`Capability` (parameters from type hints, description from the docstring) and keeps the handler bound.
Discovery, the static surface and the executor all read from here; nothing else sees handlers."""

from __future__ import annotations

import inspect
import types
import typing
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from bizops.domain.models import Risk
from bizops.domain.models.capability import CallContext, Capability, Parameter

Handler = Callable[..., Awaitable[Any]]

_TYPES: dict[Any, str] = {str: "str", int: "int", float: "float", bool: "bool", list[str]: "list[str]"}


def _param_type(annotation: Any) -> tuple[str, bool]:
    """(type name, optional) for `str`, `int | None`, `Optional[str]`, `list[str]`."""
    origin = typing.get_origin(annotation)
    if origin in (types.UnionType, typing.Union):
        inner = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(inner) == 1:
            return _TYPES[inner[0]], True
    return _TYPES[annotation], False


def _describe(fn: Callable[..., Any]) -> tuple[str, dict[str, str]]:
    """First docstring line is the description; `name: text` lines under Args: describe parameters."""
    doc = inspect.getdoc(fn) or ""
    lines = [ln.strip() for ln in doc.splitlines()]
    description = lines[0] if lines else fn.__name__
    params: dict[str, str] = {}
    for ln in lines[1:]:
        if ":" in ln and not ln.endswith(":"):
            key, _, text = ln.partition(":")
            if key.isidentifier():
                params[key] = text.strip()
    return description, params


@dataclass(frozen=True)
class Spec:
    risk: Risk
    scopes: frozenset[str]
    name: str | None = None
    send: bool = False
    idempotent: bool = False
    amount_field: str | None = None
    output: str = "Result"


def capability(
    risk: Risk,
    scopes: set[str],
    *,
    name: str | None = None,
    send: bool = False,
    idempotent: bool = False,
    amount_field: str | None = None,
    output: str = "Result",
) -> Callable[[Handler], Handler]:
    """Mark a connector method as a capability. The method signature is `(self, ctx, **params)`.
    `name` is the dotted name under the connector prefix (defaults to the method name)."""

    def mark(fn: Handler) -> Handler:
        spec = Spec(risk, frozenset(scopes), name, send, idempotent, amount_field, output)
        fn.__bizops_spec__ = spec  # type: ignore[attr-defined]
        return fn

    return mark


@dataclass
class Bound:
    capability: Capability
    handler: Handler  # already bound to its connector instance: handler(ctx, **args)


class Registry:
    def __init__(self) -> None:
        self._bound: dict[str, Bound] = {}

    def add_connector(self, prefix: str, connector: object) -> None:
        for attr in dir(connector):
            fn = getattr(connector, attr)
            spec: Spec | None = getattr(fn, "__bizops_spec__", None)
            if spec is None:
                continue
            qualified = f"{prefix}.{spec.name or attr}"
            if qualified in self._bound:
                raise ValueError(f"duplicate capability {qualified}")
            self._bound[qualified] = Bound(self._capability(qualified, fn, spec), fn)

    @staticmethod
    def _capability(name: str, fn: Callable[..., Any], spec: Spec) -> Capability:
        description, docs = _describe(fn)
        hints = typing.get_type_hints(fn)
        params: list[Parameter] = []
        for p in list(inspect.signature(fn).parameters.values()):
            if p.name in ("self", "ctx") or p.annotation is CallContext:
                continue
            kind, optional = _param_type(hints[p.name])
            required = p.default is inspect.Parameter.empty and not optional
            default = None if p.default is inspect.Parameter.empty else p.default
            params.append(Parameter(p.name, kind, required, docs.get(p.name, ""), default))
        return Capability(
            name=name,
            description=description,
            parameters=tuple(params),
            output=spec.output,
            risk=spec.risk,
            scopes=spec.scopes,
            send=spec.send,
            idempotent=spec.idempotent,
            amount_field=spec.amount_field,
        )

    def get(self, name: str) -> Bound | None:
        return self._bound.get(name)

    def capabilities(self) -> list[Capability]:
        return [b.capability for b in self._bound.values()]

    def __len__(self) -> int:
        return len(self._bound)


__all__ = ["Bound", "Handler", "Registry", "capability"]
