"""The large-catalogue arm: distractors sit behind the same control plane, cost the agent a call when picked,
and leave the three-tool surface unchanged."""

from __future__ import annotations

import pytest

from bench.scaling.distractors import with_distractors
from bizops.domain.exceptions import NotFound
from bizops.domain.models.capability import Effect
from bizops.infrastructure.di.container import Container
from tests.conftest import who

pytestmark = pytest.mark.integration


async def test_distractors_are_registered_reachable_and_harmless(seeded: Container) -> None:
    big = seeded.with_registry(with_distractors(seeded.registry, 500))
    assert len(big.registry) == 500 and len(seeded.registry) < 500
    distractor = next(
        c
        for c in big.registry.capabilities()
        if c.connector not in {"billing", "crm", "support", "usage", "engineering", "people"}
    )
    assert distractor.scopes == frozenset()
    alice = who(big, "acme/alice")
    if big.dispatcher.decide(alice, distractor.name, {}).effect is Effect.ALLOW:
        with pytest.raises(NotFound):
            await big.dispatcher.run(alice, distractor.name, {})
    assert len(big.surface("static").tools()) == 500
    assert [t.name for t in big.surface("discover").tools()] == ["discover", "execute", "inspect"]
    real = await big.dispatcher.run(who(big, "acme/carol"), "billing.mrr_by_month", {"months": 2})
    assert real.executed
