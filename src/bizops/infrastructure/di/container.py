"""Composition root. Ports become @cached_property members; adapters are imported inside the property that
builds them so optional extras stay optional; the offline double is the fallback when a key is missing."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import date
from functools import cached_property

from bizops.application.catalogue import Registry
from bizops.application.config import ControlPlaneConfig
from bizops.application.execution.dispatch import Dispatcher
from bizops.domain.models.capability import PolicyGates
from bizops.infrastructure.config.settings import Settings
from bizops.infrastructure.db.tenants import TenantDatabases

log = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    config: ControlPlaneConfig = field(default_factory=ControlPlaneConfig)

    # ---- stores and catalogue ------------------------------------------------------------------

    @cached_property
    def tenants(self) -> TenantDatabases:
        return TenantDatabases(self.settings.data_dir)

    @cached_property
    def registry(self) -> Registry:
        from bizops.infrastructure.connectors import build_registry

        return build_registry()

    def clock(self) -> date:
        """The business clock is the fixture's: every run sees the same 'today'."""
        from bizops.infrastructure.seed.world import NOW

        return NOW

    # ---- control plane -------------------------------------------------------------------------

    @property
    def gates(self) -> PolicyGates:
        return PolicyGates(
            approvals=self.config.approvals, financial_threshold_cents=self.config.financial_threshold_cents
        )

    @cached_property
    def dispatcher(self) -> Dispatcher:
        return Dispatcher(self.registry, self.tenants, self.gates, self.clock)

    def with_config(self, config: ControlPlaneConfig) -> Container:
        """A sibling container for another experiment config. Stateless engines are shared; anything built
        from the config (gates, dispatcher, executor) is rebuilt."""
        sibling = replace(self, config=config)
        for shared in ("tenants", "registry"):
            if shared in self.__dict__:
                sibling.__dict__[shared] = self.__dict__[shared]
        return sibling


def build_container(settings: Settings | None = None, config: ControlPlaneConfig | None = None) -> Container:
    settings = settings or Settings()
    config = config or ControlPlaneConfig.load(settings.config_path)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return Container(settings=settings, config=config)


__all__ = ["Container", "build_container"]
