"""How a capability is shown to the model. Compact, but exact: every parameter with its type and whether
it is optional, the output type, the risk class and what the policy will do. Tool names for the static
surface map the qualified name onto the [A-Za-z0-9_-] alphabet the Claude API allows."""

from __future__ import annotations

from bizops.domain.models import Risk
from bizops.domain.models.capability import Capability, PolicyGates

SEP = "__"


def tool_name(qualified: str) -> str:
    return qualified.replace(".", SEP)


def qualified_name(tool: str) -> str:
    return tool.replace(SEP, ".")


def compact_signature(cap: Capability, gates: PolicyGates | None = None) -> str:
    params = ", ".join(f"{p.name}{'' if p.required else '?'}: {p.type}" for p in cap.parameters)
    tags = [str(cap.risk)]
    if cap.send:
        tags.append("send, approval required")
    elif cap.risk in (Risk.DESTRUCTIVE, Risk.ADMIN):
        tags.append("approval required")
    elif cap.risk is Risk.FINANCIAL:
        threshold = (gates or PolicyGates()).financial_threshold_cents
        tags.append(f"approval over ${threshold / 100:,.0f}")
    if cap.scopes:
        tags.append("scope " + ", ".join(sorted(cap.scopes)))
    return f"{cap.name}({params}) -> {cap.output}  [{'; '.join(tags)}]"


def discover_entry(cap: Capability, gates: PolicyGates | None = None) -> str:
    """Signature plus the one-line description: what `discover` returns per hit."""
    return f"{compact_signature(cap, gates)}\n  {cap.description}"


__all__ = ["SEP", "compact_signature", "discover_entry", "qualified_name", "tool_name"]
