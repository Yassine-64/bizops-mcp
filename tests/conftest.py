from __future__ import annotations

from pathlib import Path

import pytest

from bizops.application.config import ControlPlaneConfig
from bizops.domain.models import Principal
from bizops.infrastructure.container import Container, build_container
from bizops.infrastructure.seed import seed_tenant
from bizops.infrastructure.settings import Settings


def offline_settings(data_dir: Path, **overrides: object) -> Settings:
    return Settings(_env_file=None, data_dir=data_dir, **overrides)  # type: ignore[arg-type]


@pytest.fixture
def container(tmp_path: Path) -> Container:
    return build_container(offline_settings(tmp_path), ControlPlaneConfig())


@pytest.fixture
def seeded(container: Container) -> Container:
    """Two tenants with the same shapes and different rows, freshly seeded per test."""
    seed_tenant(container.settings.data_dir, "acme", 42)
    seed_tenant(container.settings.data_dir, "globex", 42)
    return container


def who(c: Container, principal: str) -> Principal:
    tenant, user = principal.split("/")
    p = c.tenants.principal(tenant, user)
    assert p is not None
    return p
