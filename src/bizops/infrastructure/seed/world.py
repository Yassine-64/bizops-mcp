"""The company skeleton every connector seeds from: a fixed clock, named users, and accounts with the
storylines attached. Connectors add their own tables from this; nothing here touches SQLite."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

NOW = date(2026, 10, 1)  # fixed: the benchmark must not drift with the wall clock
MONTHS = 12

SEGMENTS = {"enterprise": (120_000, 480_000), "mid": (24_000, 110_000), "smb": (3_600, 20_000)}  # ARR $/year
INDUSTRIES = ["fintech", "healthcare", "logistics", "media", "retail", "edtech", "insurance", "manufacturing"]
FIRST = [
    "Initech",
    "Globodyne",
    "Vandelay",
    "Hooli",
    "Umbrella",
    "Stark",
    "Wayne",
    "Acme",
    "Wonka",
    "Tyrell",
    "Cyberdyne",
    "Soylent",
    "Oscorp",
    "Gringotts",
    "Pied Piper",
    "Aviato",
    "Dunder",
    "Sterling",
    "Prestige",
    "Massive",
    "Virtucon",
    "Bluth",
    "Nakatomi",
    "Weyland",
    "Ingen",
    "Octan",
    "Zorg",
    "Veridian",
    "Rekall",
    "Wernham",
    "Omni",
    "Lumon",
    "Buy n Large",
    "Gekko",
    "Sirius",
    "Monarch",
    "Hanso",
    "Primatech",
    "Abstergo",
    "Roxxon",
    "Kord",
    "Sunrise",
    "Northwind",
    "Contoso",
    "Fabrikam",
    "Tailspin",
    "Woodgrove",
    "Adatum",
    "Litware",
    "Proseware",
    "Wingtip",
    "Alpine",
    "Coho",
    "Humongous",
    "Lucerne",
    "Margie",
    "Trey",
    "Blue Yonder",
]
SUFFIX = ["Inc", "Ltd", "Labs", "Systems", "Group", "Co", "Holdings", "Networks"]

USERS = {  # user -> roles; same four people in every tenant so scenarios can name them
    "alice": {"sales"},
    "bob": {"engineering"},
    "carol": {"finance"},
    "dana": {"admin"},
    "eve": {"support"},
}


@dataclass
class Account:
    id: str
    name: str
    segment: str
    industry: str
    owner: str
    arr_cents: int
    created: date
    churned: date | None = None
    # storyline flags
    at_risk: bool = False  # overdue invoices + declining usage
    paid_by_wire_mismatch: bool = False  # paid, invoice still open
    outage_hit: bool = False  # ticket spike in the outage week
    downgraded: date | None = None


@dataclass
class World:
    tenant: str
    seed: int
    now: date = NOW
    accounts: list[Account] = field(default_factory=list)
    outage_start: date = NOW - timedelta(days=24)  # last month, week 4
    outage_hours: int = 6
    rng: random.Random = field(init=False, repr=False)  # one stream per world, shared by every fixture

    def __post_init__(self) -> None:
        self.rng = random.Random(f"{self.tenant}:{self.seed}")

    def month_start(self, months_ago: int) -> date:
        y, m = self.now.year, self.now.month - months_ago
        while m <= 0:
            y, m = y - 1, m + 12
        return date(y, m, 1)


def build_world(tenant: str, seed: int, n_accounts: int = 55) -> World:
    w = World(tenant=tenant, seed=seed)
    rng = w.rng
    names = rng.sample(FIRST, n_accounts)
    users = [u for u, r in USERS.items() if "sales" in r or "admin" in r]
    for i, first in enumerate(names):
        segment = rng.choices(list(SEGMENTS), weights=[1, 3, 6])[0]
        lo, hi = SEGMENTS[segment]
        arr = rng.randrange(lo, hi, 100) * 100
        created = w.now - timedelta(days=rng.randrange(90, 365 * 3))
        w.accounts.append(
            Account(
                id=f"acc_{i + 1:03d}",
                name=f"{first} {rng.choice(SUFFIX)}",
                segment=segment,
                industry=rng.choice(INDUSTRIES),
                owner=rng.choice(users),
                arr_cents=arr,
                created=created,
            )
        )
    # storylines: deterministic picks over the shuffled list
    ent = [a for a in w.accounts if a.segment == "enterprise"] or w.accounts[:3]
    ent[0].at_risk = True  # overdue + declining usage
    ent[1].paid_by_wire_mismatch = True
    hit = rng.sample([a for a in w.accounts if a not in ent[:2]], 15)  # storylines never overlap
    for a in hit:
        a.outage_hit = True
    # two outage-hit accounts churn within two weeks of the outage (last month), one downgrades
    for a in hit[:2]:
        a.churned = w.outage_start + timedelta(days=rng.randrange(5, 14))
    hit[2].downgraded = w.outage_start + timedelta(days=9)
    # background churn earlier in the year so "last month" is not the only churn ever
    for a in rng.sample([a for a in w.accounts if not a.outage_hit], 4):
        a.churned = w.now - timedelta(days=rng.randrange(60, 300))
    return w


__all__ = ["MONTHS", "NOW", "USERS", "Account", "World", "build_world"]
