"""Process settings: where data lives, which engines run, and the keys. Experiment knobs live in
`application.config.ControlPlaneConfig`, not here."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BIZOPS_", env_file=".env", extra="ignore")

    data_dir: Path = Field(default=Path(".data"), description="SQLite stores, journal and run recordings")
    llm: str = Field(default="anthropic", description="anthropic | scripted")
    anthropic_api_key: str | None = None
    model: str = Field(default="claude-sonnet-5-5", description="agent model for serve and bench")
    principal: str | None = Field(default=None, description="dev only: 'tenant/user' for the stdio server")
    config_path: str | None = Field(default=None, description="YAML ControlPlaneConfig")


__all__ = ["Settings"]
