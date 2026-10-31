"""Every scenario file parses, names only real checkers and capabilities, and has something to grade."""

from __future__ import annotations

from pathlib import Path

import pytest

from bench.checkers import CHECKERS
from bench.harness.scenario import Scenario, load_scenarios
from bizops.infrastructure.connectors import build_registry

ROOT = Path(__file__).resolve().parents[2] / "bench" / "scenarios"
SCENARIOS = load_scenarios(ROOT)
CAPABILITIES = {c.name for c in build_registry().capabilities()}


def test_ids_are_unique() -> None:
    ids = [s.id for s in SCENARIOS]
    assert len(ids) == len(set(ids)) and len(ids) >= 15


@pytest.mark.parametrize("s", SCENARIOS, ids=lambda s: s.id)
def test_scenario_is_gradeable(s: Scenario) -> None:
    names = [s.expect.checker] if s.expect else []
    names += [c.checker for c in s.state] + [c.args_from.checker for c in s.state if c.args_from]
    names += [s.leak.checker] if s.leak else []
    assert all(n in CHECKERS for n in names), names
    traj = s.trajectory
    unknown = [c for c in traj.required + traj.required_any + traj.forbidden if c not in CAPABILITIES]
    assert not unknown, unknown
    assert s.expect or s.state or s.leak or traj.forbidden or s.safety.denials, "nothing to grade"
