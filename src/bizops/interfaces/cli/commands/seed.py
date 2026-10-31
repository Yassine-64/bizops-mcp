"""bizops seed: deterministic tenant fixture."""

from __future__ import annotations

import typer

from bizops.infrastructure.seed import content_hash, seed_tenant
from bizops.infrastructure.settings import Settings


def seed(
    tenant: str = typer.Option("acme", help="tenant name; its SQLite file is <data_dir>/<tenant>.db"),
    seed: int = typer.Option(42, help="RNG seed; same tenant and seed give the same rows"),
) -> None:
    """Create or replace a tenant's synthetic company."""
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    world = seed_tenant(settings.data_dir, tenant, seed)
    digest = content_hash(settings.data_dir, tenant)
    typer.echo(f"{tenant}: {len(world.accounts)} accounts, content sha256 {digest[:16]}")
