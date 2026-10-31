"""The deterministic company fixture: `world` holds the storylines, one module per system writes its rows,
`tenant` builds a tenant's database from them."""

from bizops.infrastructure.seed.tenant import World, content_hash, seed_tenant

__all__ = ["World", "content_hash", "seed_tenant"]
