"""CRM fixture: every account, one to three contacts, an open deal on a third of active accounts and an
expansion deal in Proposal on the at-risk enterprise account."""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from bizops.infrastructure.connectors.crm.store import STAGES
from bizops.infrastructure.seed.world import World

TITLES = ["CTO", "VP Engineering", "Head of Ops", "CFO", "Procurement Lead", "Product Manager"]
GIVEN = ["Sam", "Priya", "Lin", "Omar", "Noor", "Kai", "Ava", "Yusuf", "Mei", "Tom", "Ines", "Rafael"]


def seed(conn: sqlite3.Connection, w: World) -> None:
    rng = w.rng
    for a in w.accounts:
        conn.execute(
            "INSERT INTO crm_accounts VALUES (?,?,?,?,?,?,?,?,?)",
            (
                a.id,
                a.name,
                a.segment,
                a.industry,
                a.owner,
                a.arr_cents,
                "churned" if a.churned else "active",
                a.created.isoformat(),
                a.churned.isoformat() if a.churned else None,
            ),
        )
        for j in range(rng.randrange(1, 4)):
            given = rng.choice(GIVEN)
            domain = a.name.split()[0].lower().replace(" ", "")
            conn.execute(
                "INSERT INTO crm_contacts VALUES (?,?,?,?,?)",
                (
                    f"con_{a.id[4:]}_{j}",
                    a.id,
                    f"{given} {a.name.split()[0]}",
                    f"{given.lower()}@{domain}.example",
                    rng.choice(TITLES),
                ),
            )
    n = 0
    for a in w.accounts:
        if a.churned or (not a.at_risk and rng.random() > 0.33):
            continue
        n += 1
        stage = "Proposal" if a.at_risk else rng.choice(STAGES[:3])
        conn.execute(
            "INSERT INTO crm_deals VALUES (?,?,?,?,?,?,?,NULL)",
            (
                f"deal_{n:03d}",
                a.id,
                f"{a.name.split()[0]} expansion",
                stage,
                int(a.arr_cents * rng.uniform(0.2, 0.6)) // 100 * 100,
                a.owner,
                (w.now - timedelta(days=rng.randrange(1, 40))).isoformat(),
            ),
        )


__all__ = ["seed"]
