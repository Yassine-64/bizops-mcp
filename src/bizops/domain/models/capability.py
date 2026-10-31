"""What the agent can do, and what the policy said about one attempt to do it."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any

from bizops.domain.models.principal import Principal


class Risk(StrEnum):
    READ = "read"
    WRITE = "write"
    FINANCIAL = "financial"
    DESTRUCTIVE = "destructive"
    ADMIN = "admin"


@dataclass(frozen=True)
class Parameter:
    name: str
    type: str  # "str" | "int" | "float" | "bool" | "list[str]"
    required: bool
    description: str = ""
    default: Any = None


@dataclass(frozen=True)
class Capability:
    """A registered, policy-classified operation. The model sees its signature, never its implementation."""

    name: str  # qualified: "billing.refund_payment"
    description: str
    parameters: tuple[Parameter, ...]
    output: str  # type name shown in the signature, e.g. "Refund" or "list[Invoice]"
    risk: Risk
    scopes: frozenset[str]
    send: bool = False  # externally visible message: always needs approval, never adoptable on resume
    idempotent: bool = False  # a write the connector can look up by operation_id
    amount_field: str | None = None  # for financial risk: which argument carries cents

    @property
    def connector(self) -> str:
        return self.name.split(".", 1)[0]

    @property
    def is_write(self) -> bool:
        return self.risk is not Risk.READ

    def input_schema(self) -> dict[str, Any]:
        props: dict[str, dict[str, Any]] = {}
        for p in self.parameters:
            props[p.name] = {"type": _JSON[p.type], "description": p.description}
            if p.type == "list[str]":
                props[p.name]["items"] = {"type": "string"}
        return {
            "type": "object",
            "properties": props,
            "required": [p.name for p in self.parameters if p.required],
            "additionalProperties": False,
        }


_JSON = {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "list[str]": "array"}


class Effect(StrEnum):
    ALLOW = "allow"
    APPROVE = "approve"
    DENY = "deny"


@dataclass(frozen=True)
class Decision:
    effect: Effect
    reason: str
    rule: str  # the gate that decided: "scope", "risk:financial", "unknown", ...


@dataclass(frozen=True)
class PolicyGates:
    """The control-plane knobs the policy needs; a value object so the domain never imports config."""

    approvals: bool = True
    financial_threshold_cents: int = 500_000


@dataclass
class CallContext:
    """What a capability handler receives: the acting principal and that principal's tenant store."""

    principal: Principal
    store: Any  # the tenant's connection; opaque to the domain
    today: date  # the business clock; connectors never read the wall clock, so runs replay identically
    operation_id: str | None = None  # server-minted for writes; the connector's idempotency key
    extra: dict[str, Any] = field(default_factory=dict)


__all__ = ["CallContext", "Capability", "Decision", "Effect", "Parameter", "PolicyGates", "Risk"]
