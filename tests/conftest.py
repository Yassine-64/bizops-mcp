from __future__ import annotations

from pathlib import Path

import pytest

from bizops.application.config import ControlPlaneConfig
from bizops.infrastructure.config.settings import Settings
from bizops.infrastructure.di.container import Container, build_container


def offline_settings(data_dir: Path, **overrides: object) -> Settings:
    return Settings(_env_file=None, data_dir=data_dir, llm="scripted", **overrides)  # type: ignore[arg-type]


@pytest.fixture
def container(tmp_path: Path) -> Container:
    return build_container(offline_settings(tmp_path), ControlPlaneConfig())
