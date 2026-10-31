"""A BizOpsBench scenario: who asks, what they ask, and how the answer and the side effects are graded.
Expected values are never written here; `expect`, `state` and `leak` name checkers that compute them from
the seeded database."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

Category = Literal["read", "multi", "write", "approval", "failure", "security"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a typo in a scenario must fail loudly, not grade silently


class ArgsFrom(Strict):
    checker: str
    args: list[Any] = Field(default_factory=list)
    field: str


class Expect(Strict):
    checker: str
    args: list[Any] = Field(default_factory=list)
    mention: list[str]  # fields of the checker's facts that the final answer must contain


class StateCheck(Strict):
    checker: str
    args: list[Any] = Field(default_factory=list)
    args_from: ArgsFrom | None = None
    equals: dict[str, Any]


class Leak(Strict):
    tenant: str
    checker: str
    args: list[Any] = Field(default_factory=list)
    fields: list[str]


class Trajectory(Strict):
    required: list[str] = Field(default_factory=list)
    required_any: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)
    max_calls: int = 12


class Safety(Strict):
    approvals: int = 0
    denials: int = 0


class Chaos(Strict):
    profile: Literal["rate_limit_once", "timeout_once", "credential_expired", "commit_then_drop"]
    capability: str


class Scenario(Strict):
    id: str
    category: Category
    principal: str
    task: str
    human: Literal["approve", "decline"] = "approve"
    expect: Expect | None = None
    state: list[StateCheck] = Field(default_factory=list)
    leak: Leak | None = None
    trajectory: Trajectory = Field(default_factory=Trajectory)
    safety: Safety = Field(default_factory=Safety)
    chaos: Chaos | None = None

    @property
    def tenant(self) -> str:
        return self.principal.split("/", 1)[0]


def load_scenarios(root: Path, pattern: str = "**/*.yaml") -> list[Scenario]:
    return [Scenario.model_validate(yaml.safe_load(p.read_text())) for p in sorted(root.glob(pattern))]


__all__ = ["Scenario", "load_scenarios"]
