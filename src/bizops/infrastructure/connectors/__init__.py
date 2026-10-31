"""The connectors of the fixture company, registered under their system prefix."""

from __future__ import annotations

from bizops.application.catalogue import Registry
from bizops.infrastructure.connectors.billing.connector import BillingConnector
from bizops.infrastructure.connectors.crm.connector import CrmConnector
from bizops.infrastructure.connectors.engineering.connector import EngineeringConnector
from bizops.infrastructure.connectors.support.connector import SupportConnector
from bizops.infrastructure.connectors.usage.connector import UsageConnector

CONNECTORS: dict[str, object] = {
    "billing": BillingConnector(),
    "crm": CrmConnector(),
    "support": SupportConnector(),
    "usage": UsageConnector(),
    "engineering": EngineeringConnector(),
}


def build_registry() -> Registry:
    registry = Registry()
    for prefix, connector in CONNECTORS.items():
        registry.add_connector(prefix, connector)
    return registry


__all__ = ["CONNECTORS", "build_registry"]
