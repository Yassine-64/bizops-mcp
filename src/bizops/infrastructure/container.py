"""Composition root. Ports become @cached_property members; adapters are imported inside the property that
builds them so optional extras stay optional; the offline double is the fallback when a key is missing."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from functools import cached_property

from bizops.application.approvals import Approvals
from bizops.application.catalogue import Registry
from bizops.application.config import ControlPlaneConfig, SurfaceName
from bizops.application.execution.dispatch import Dispatcher
from bizops.application.execution.executor import Executor
from bizops.application.surfaces import Surface
from bizops.domain.models.capability import PolicyGates
from bizops.infrastructure.db.tenants import TenantDatabases
from bizops.infrastructure.journal import SqliteJournal
from bizops.infrastructure.settings import Settings

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

    @cached_property
    def journal(self) -> SqliteJournal:
        return SqliteJournal(self.settings.data_dir / "journal.db")

    @staticmethod
    def wall_clock() -> datetime:
        """Operational time (run creation, approval expiry), as opposed to the business clock."""
        return datetime.now(UTC)

    @cached_property
    def approvals(self) -> Approvals:
        return Approvals(self.journal, self.wall_clock)

    @cached_property
    def executor(self) -> Executor:
        return Executor(
            self.dispatcher, self.journal, self.approvals, self.wall_clock, durable=self.config.journal
        )

    def surface(self, name: SurfaceName | None = None) -> Surface:
        name = name or self.config.surface
        if name == "discover":
            from bizops.application.surfaces.discover import DiscoverSurface

            return DiscoverSurface(self.registry, self.executor, self.gates, self.config.discover_limit)
        from bizops.application.surfaces.static import StaticSurface

        return StaticSurface(self.registry, self.executor, self.gates)  # tool_search presents the same tools

    def with_registry(self, registry: Registry) -> Container:
        """A sibling over another capability registry (failure injection, larger catalogues). Stores and the
        journal are shared; the dispatcher, executor and surfaces are rebuilt over the new registry."""
        sibling = replace(self)
        sibling.__dict__["registry"] = registry
        for shared in ("tenants", "journal"):
            if shared in self.__dict__:
                sibling.__dict__[shared] = self.__dict__[shared]
        return sibling

    def with_chaos(self, profile: str, capability: str) -> Container:
        """A sibling whose registry fails once on `capability` in the named way (bench and tests)."""
        from bizops.infrastructure.connectors.chaos import with_chaos

        return self.with_registry(with_chaos(self.registry, profile, capability))  # type: ignore[arg-type]

    def with_config(self, config: ControlPlaneConfig) -> Container:
        """A sibling container for another experiment config. Stateless engines are shared; anything built
        from the config (gates, dispatcher, executor) is rebuilt."""
        sibling = replace(self, config=config)
        for shared in ("tenants", "registry", "journal"):
            if shared in self.__dict__:
                sibling.__dict__[shared] = self.__dict__[shared]
        return sibling


def build_container(settings: Settings | None = None, config: ControlPlaneConfig | None = None) -> Container:
    settings = settings or Settings()
    config = config or ControlPlaneConfig.load(settings.config_path)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return Container(settings=settings, config=config)


__all__ = ["Container", "build_container"]
