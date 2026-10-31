"""Paired statistics over scenarios. Runs are paired by scenario id: same tasks, same seed, a different
arm. Repeats of one scenario are averaged first, then scenarios are resampled, so a scenario with three
repeats does not count three times."""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Callable, Iterable
from statistics import mean
from typing import Any

Row = dict[str, Any]


def by_scenario(rows: Iterable[Row], value: Callable[[Row], float]) -> dict[str, float]:
    groups: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        groups[r["scenario"]].append(value(r))
    return {k: mean(v) for k, v in groups.items()}


def bootstrap_mean(values: list[float], n: int = 10_000, seed: int = 0) -> tuple[float, float, float]:
    if not values:
        return (float("nan"),) * 3  # type: ignore[return-value]
    rng = random.Random(seed)
    means = sorted(mean(rng.choices(values, k=len(values))) for _ in range(n))
    return mean(values), means[int(0.025 * n)], means[int(0.975 * n) - 1]


def paired_difference(
    a: dict[str, float], b: dict[str, float], n: int = 10_000, seed: int = 0
) -> tuple[float, float, float]:
    """Mean of b - a over shared scenarios with a 95% paired-bootstrap interval."""
    shared = sorted(set(a) & set(b))
    return bootstrap_mean([b[k] - a[k] for k in shared], n, seed)


def percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


__all__ = ["bootstrap_mean", "by_scenario", "paired_difference", "percentile"]
