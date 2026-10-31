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


@pytest.fixture(scope="module")
def seeded_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from bizops.infrastructure.seed import seed_tenant

    d = tmp_path_factory.mktemp("seed")
    seed_tenant(d, "acme", 42)
    seed_tenant(d, "globex", 42)
    return d


@pytest.mark.parametrize("s", [s for s in SCENARIOS if s.expect or s.state or s.leak], ids=lambda s: s.id)
def test_facts_exist_and_a_perfect_answer_grades(s: Scenario, seeded_db: Path) -> None:
    """Every checker returns a non-empty fact on the seed, and an answer that states the facts passes."""
    import sqlite3

    from bench.harness.grade import _mentioned, _values

    conn = sqlite3.connect(seeded_db / f"{s.tenant}.db")
    if s.expect:
        facts = CHECKERS[s.expect.checker](conn, *s.expect.args)
        values = [v for key in s.expect.mention for v in _values(facts[key])]
        assert values and all(v not in ("", "None") for v in values), facts
        answer = " ; ".join(values)
        assert all(_mentioned(answer, v) for v in values)
    for check in s.state:
        args = list(check.args)
        if check.args_from:
            args.append(CHECKERS[check.args_from.checker](conn, *check.args_from.args)[check.args_from.field])
        assert CHECKERS[check.checker](conn, *args) is not None
    if s.leak:
        other = sqlite3.connect(seeded_db / f"{s.leak.tenant}.db")
        secret = CHECKERS[s.leak.checker](other, *s.leak.args)
        assert all(secret.get(k) for k in s.leak.fields), secret
