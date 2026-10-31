"""Agent-facing surfaces. `base` holds the shared contract; `static` and `discover` implement it."""

from bizops.application.surfaces.base import ExecutorSurface, Surface, ToolReply, ToolSpec

__all__ = ["ExecutorSurface", "Surface", "ToolReply", "ToolSpec"]
