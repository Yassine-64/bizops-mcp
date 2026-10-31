"""Connectors of the fixture company, one package per system; `registry` assembles them."""

from bizops.infrastructure.connectors.registry import CONNECTORS, build_registry

__all__ = ["CONNECTORS", "build_registry"]
