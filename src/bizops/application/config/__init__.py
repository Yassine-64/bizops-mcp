"""The experiment: which agent-facing surface, and which control-plane layers are on."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

Surface = Literal["static", "tool_search", "discover"]


class ControlPlaneConfig(BaseModel):
    name: str = "full"
    surface: Surface = "discover"
    approvals: bool = Field(default=True, description="risk gates pause for a human; off = scopes only")
    journal: bool = Field(default=True, description="durable steps with server-owned operation identity")
    discover_limit: int = 8
    financial_threshold_cents: int = Field(default=500_000, description="financial actions above this pause")

    @classmethod
    def load(cls, path: str | Path | None) -> ControlPlaneConfig:
        if path is None:
            return cls()
        return cls.model_validate(yaml.safe_load(Path(path).read_text()) or {})


__all__ = ["ControlPlaneConfig", "Surface"]
