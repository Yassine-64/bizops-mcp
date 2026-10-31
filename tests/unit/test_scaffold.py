from bizops.application.config import ControlPlaneConfig
from bizops.infrastructure.container import Container


def test_container_builds_offline(container: Container) -> None:
    assert container.settings.data_dir.exists()
    assert container.config.surface == "discover"


def test_with_config_keeps_settings(container: Container) -> None:
    sibling = container.with_config(ControlPlaneConfig(name="scopes-only", approvals=False, journal=False))
    assert sibling.settings is container.settings
    assert sibling.config.approvals is False and container.config.approvals is True
