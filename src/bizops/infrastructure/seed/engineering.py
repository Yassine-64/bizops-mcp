"""Engineering fixture: four projects, one of them clearly late (seven open P1s, due in twelve days), and
two incidents, one of which is the sev1 outage the support and billing storylines hang off."""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from bizops.infrastructure.seed.world import World

PROJECTS = [  # name, owner, due in days, age in days
    ("SSO rewrite", "bob", 45, 30),
    ("Billing v2 migration", "bob", 12, 90),
    ("Mobile uploads", "dana", 60, 20),
    ("Data export service", "bob", 90, 10),
]
LATE_PROJECT = "Billing v2 migration"
ISSUE_TITLES = [
    "Flaky test in auth",
    "Pagination off by one",
    "Retry storm on webhook",
    "Migration lock timeout",
    "Slow query on invoices",
    "Missing index on usage_daily",
    "Race in job scheduler",
    "Type error in export",
    "Permission check bypass in admin",
    "Memory leak in worker",
]


def seed(conn: sqlite3.Connection, w: World) -> None:
    rng = w.rng
    n = 0
    for i, (name, owner, due_in, age) in enumerate(PROJECTS):
        pid = f"proj_{i + 1}"
        conn.execute(
            "INSERT INTO eng_projects VALUES (?,?,?,?,?)",
            (pid, name, owner, (w.now + timedelta(days=due_in)).isoformat(), "active"),
        )
        open_p1 = 7 if name == LATE_PROJECT else rng.randrange(0, 2)
        for j in range(10 + rng.randrange(0, 8)):
            n += 1
            p1 = j < open_p1
            closed = None if p1 or rng.random() < 0.35 else w.now - timedelta(days=rng.randrange(1, age + 1))
            conn.execute(
                "INSERT INTO eng_issues VALUES (?,?,?,?,?,?,?,NULL)",
                (
                    f"iss_{n:03d}",
                    pid,
                    rng.choice(ISSUE_TITLES),
                    "P1" if p1 else rng.choice(["P2", "P3"]),
                    "closed" if closed else "open",
                    (w.now - timedelta(days=rng.randrange(1, age + 1))).isoformat(),
                    closed.isoformat() if closed else None,
                ),
            )
    start = w.outage_start.isoformat()
    conn.execute(
        "INSERT INTO eng_incidents VALUES (?,?,?,?,?,?,?)",
        (
            "inc_001",
            "API outage: auth service returned 503",
            "sev1",
            f"{start}T08:10:00",
            f"{start}T{8 + w.outage_hours:02d}:40:00",
            "api,dashboard,login",
            "Expired certificate on the auth service load balancer",
        ),
    )
    earlier = (w.now - timedelta(days=70)).isoformat()
    conn.execute(
        "INSERT INTO eng_incidents VALUES (?,?,?,?,?,?,?)",
        (
            "inc_002",
            "Export queue backlog",
            "sev3",
            f"{earlier}T14:00:00",
            f"{earlier}T16:30:00",
            "exports",
            "Worker pool undersized",
        ),
    )


__all__ = ["LATE_PROJECT", "seed"]
