"""Pure value types shared by every layer. No I/O, no framework types."""

from bizops.domain.models.capability import Risk
from bizops.domain.models.principal import Principal

__all__ = ["Principal", "Risk"]
