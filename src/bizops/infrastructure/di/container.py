"""Composition root. Ports become @cached_property members; adapters are imported inside the branch
that selects them so optional extras stay optional, and the offline double is the fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace

from bizops.application.config import ControlPlaneConfig
from bizops.infrastructure.config.settings import Settings

log = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    config: ControlPlaneConfig = field(default_factory=ControlPlaneConfig)

    def with_config(self, config: ControlPlaneConfig) -> Container:
        """A sibling container for another experiment config over the same engines and stores."""
        return replace(self, config=config)


def build_container(settings: Settings | None = None, config: ControlPlaneConfig | None = None) -> Container:
    settings = settings or Settings()
    config = config or ControlPlaneConfig.load(settings.config_path)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return Container(settings=settings, config=config)


__all__ = ["Container", "build_container"]
