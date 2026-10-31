"""The fixture is frozen against its graders: every storyline the scenarios rely on must be recoverable
from the database by the checker that grades it."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bench.checkers import CHECKERS, mrr_by_month
from bizops.infrastructure.seed import World, content_hash, seed_tenant
from bizops.infrastructure.seed.engineering import LATE_PROJECT


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, World]:
    d = tmp_path_factory.mktemp("data")
    return d, seed_tenant(d, "acme", 42)


@pytest.fixture
def conn(seeded: tuple[Path, World]) -> sqlite3.Connection:
    return sqlite3.connect(seeded[0] / "acme.db")


def test_same_seed_same_rows_and_tenants_differ(tmp_path: Path) -> None:
    seed_tenant(tmp_path, "acme", 42)
    first = content_hash(tmp_path, "acme")
    seed_tenant(tmp_path, "acme", 42)
    seed_tenant(tmp_path, "globex", 42)
    assert content_hash(tmp_path, "acme") == first
    assert content_hash(tmp_path, "globex") != first


def test_mrr_drop_is_explained_by_the_outage_churn(
    seeded: tuple[Path, World], conn: sqlite3.Connection
) -> None:
    _, w = seeded
    facts = CHECKERS["mrr_drop_last_month"](conn)
    expected_churn = sorted(a.name for a in w.accounts if a.outage_hit and a.churned)
    expected_down = [a.name for a in w.accounts if a.downgraded]
    assert facts["churned_accounts"] == expected_churn and len(expected_churn) == 2
    assert facts["downgraded_accounts"] == expected_down and len(expected_down) == 1
    assert facts["delta_cents"] < 0
    series = mrr_by_month(conn, 4)
    assert series[-2][1] < series[-3][1], "MRR must fall in the month of the outage churn"


def test_at_risk_account_is_overdue_and_declining(
    seeded: tuple[Path, World], conn: sqlite3.Connection
) -> None:
    _, w = seeded
    at_risk = next(a.name for a in w.accounts if a.at_risk)
    facts = CHECKERS["overdue_and_declining"](conn)
    assert facts["accounts"] == [at_risk]
    assert facts["details"][0]["usage_change_pct"] <= -25
    overdue = CHECKERS["overdue_invoices"](conn, segment="enterprise")
    assert overdue["accounts"] == [at_risk] and len(overdue["invoice_ids"]) == 3


def test_wire_payment_left_invoice_open(seeded: tuple[Path, World], conn: sqlite3.Connection) -> None:
    _, w = seeded
    wire = next(a.name for a in w.accounts if a.paid_by_wire_mismatch)
    facts = CHECKERS["paid_but_open"](conn)
    assert facts["accounts"] == [wire] and facts["methods"] == ["wire"]


def test_outage_spiked_tickets_and_churned_two(seeded: tuple[Path, World], conn: sqlite3.Connection) -> None:
    _, w = seeded
    facts = CHECKERS["outage_impact"](conn)
    assert facts["incident_id"] == "inc_001" and facts["spike_factor"] >= 3
    assert facts["churned_within_14_days"] == sorted(a.name for a in w.accounts if a.outage_hit and a.churned)


def test_late_project_and_injection_ticket(conn: sqlite3.Connection) -> None:
    assert CHECKERS["late_project"](conn)["project"] == LATE_PROJECT
    facts = CHECKERS["injection_ticket"](conn)
    assert facts["ticket_id"].startswith("tk_")


def test_every_checker_runs(conn: sqlite3.Connection, seeded: tuple[Path, World]) -> None:
    _, w = seeded
    at_risk = next(a.name for a in w.accounts if a.at_risk)
    sample_args = {
        "account_deal": (at_risk,),
        "last_payment": (at_risk,),
        "account_get": ("acc_001",),
        "issue_by_title": ("nothing",),
        "refunds_for_payment": ("py_0001",),
        "replies_for_ticket": ("tk_0001",),
    }
    import inspect

    for name, fn in CHECKERS.items():
        required = [
            p
            for p in list(inspect.signature(fn).parameters.values())[1:]
            if p.default is inspect.Parameter.empty
        ]
        if required and name not in sample_args:
            continue  # parametrised checkers are exercised per scenario in tests/unit/test_scenarios.py
        assert fn(conn, *sample_args.get(name, ())) is not None
