"""Usage fixture: 16 weeks of daily usage. The at-risk account decays about 40% over the last 8 weeks,
churned accounts drop to zero after churn, everyone dips on the outage day."""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from bizops.infrastructure.seed.world import World

DAYS = 16 * 7
BASE_USERS = {"enterprise": 180, "mid": 40, "smb": 8}


def seed(conn: sqlite3.Connection, w: World) -> None:
    rng = w.rng
    first = w.now - timedelta(days=DAYS)
    rows: list[tuple[str, str, int, int]] = []
    for a in w.accounts:
        base = BASE_USERS[a.segment] * rng.uniform(0.7, 1.3)
        for i in range(DAYS):
            day = first + timedelta(days=i)
            if day < a.created or (a.churned and day >= a.churned):
                users = 0.0
            else:
                users = base * rng.uniform(0.85, 1.15)
                if day.weekday() >= 5:
                    users *= 0.35
                if a.at_risk and i > DAYS - 56:
                    users *= 1 - 0.4 * (i - (DAYS - 56)) / 56
                if w.outage_start <= day < w.outage_start + timedelta(days=1):
                    users *= 0.3
            rows.append((a.id, day.isoformat(), int(users), int(users * rng.uniform(40, 60))))
    conn.executemany("INSERT INTO usage_daily VALUES (?,?,?,?)", rows)


__all__ = ["seed"]
