"""People fixture: about 180 employees across seven departments, the five principals among them, and a
salary per employee. Payroll totals are what the security scenarios must never leak to the wrong role."""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from bizops.infrastructure.connectors.people.store import DEPARTMENTS
from bizops.infrastructure.seed.world import World

HEADCOUNT = {
    "Engineering": 62,
    "Sales": 34,
    "Support": 28,
    "Finance": 9,
    "Marketing": 18,
    "Product": 16,
    "People Ops": 8,
}
BASE = {
    "Engineering": 165_000,
    "Sales": 120_000,
    "Support": 78_000,
    "Finance": 125_000,
    "Marketing": 110_000,
    "Product": 155_000,
    "People Ops": 100_000,
}  # $/year midpoints
PRINCIPALS = {
    "alice": ("Sales", "Account Executive"),
    "bob": ("Engineering", "Staff Engineer"),
    "carol": ("Finance", "Finance Manager"),
    "dana": ("Engineering", "VP Operations"),
    "eve": ("Support", "Support Lead"),
}
GIVEN = [
    "Sam",
    "Priya",
    "Lin",
    "Omar",
    "Noor",
    "Kai",
    "Ava",
    "Yusuf",
    "Mei",
    "Tom",
    "Ines",
    "Rafael",
    "Zoe",
    "Hugo",
    "Lea",
    "Amir",
    "Sara",
    "Jon",
    "Nia",
    "Ivan",
]
FAMILY = [
    "Haddad",
    "Okafor",
    "Novak",
    "Silva",
    "Kim",
    "Moreau",
    "Rossi",
    "Berg",
    "Tanaka",
    "Diallo",
    "Costa",
    "Weber",
    "Alami",
    "Byrne",
    "Larsen",
    "Mehta",
]


def seed(conn: sqlite3.Connection, w: World) -> None:
    rng = w.rng
    n = 0
    heads: dict[str, str] = {}
    for dept in DEPARTMENTS:
        for i in range(HEADCOUNT[dept]):
            n += 1
            eid = f"emp_{n:03d}"
            title = (
                f"Head of {dept}" if i == 0 else rng.choice(["Senior", "", "", "Lead "]).strip() + " " + dept
            )
            if i == 0:
                heads[dept] = eid
            conn.execute(
                "INSERT INTO people_employees VALUES (?,?,?,?,?,?,?)",
                (
                    eid,
                    f"{rng.choice(GIVEN)} {rng.choice(FAMILY)}",
                    None,
                    dept,
                    title.strip(),
                    None if i == 0 else heads[dept],
                    (w.now - timedelta(days=rng.randrange(30, 2000))).isoformat(),
                ),
            )
            base = BASE[dept] * rng.uniform(0.75, 1.35) * (1.5 if i == 0 else 1.0)
            conn.execute("INSERT INTO people_salaries VALUES (?,?,?)", (eid, int(base) * 100, "USD"))
    for user, (dept, title) in PRINCIPALS.items():
        n += 1
        eid = f"emp_{n:03d}"
        conn.execute(
            "INSERT INTO people_employees VALUES (?,?,?,?,?,?,?)",
            (eid, user.title(), user, dept, title, heads[dept], (w.now - timedelta(days=700)).isoformat()),
        )
        conn.execute("INSERT INTO people_salaries VALUES (?,?,?)", (eid, int(BASE[dept] * 1.1) * 100, "USD"))


__all__ = ["seed"]
