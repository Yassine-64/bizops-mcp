from bench.harness.stats import by_family, paired_difference


def _rows(arm: str, outcomes: dict[str, list[float]]) -> list[dict[str, object]]:
    return [{"scenario": s, "arm": arm, "ok": v} for s, vs in outcomes.items() for v in vs]


def test_parametrised_cases_collapse_into_one_family() -> None:
    family = {"read-profile-a": "read-profile", "read-profile-b": "read-profile", "lone": "lone"}.__getitem__
    rows = _rows("x", {"read-profile-a": [1.0, 1.0], "read-profile-b": [0.0], "lone": [1.0]})
    assert by_family(rows, lambda r: float(r["ok"]), family) == {"read-profile": 0.5, "lone": 1.0}


def test_paired_difference_counts_families_not_scenarios() -> None:
    a = {"f1": 0.0, "f2": 1.0}
    b = {"f1": 1.0, "f2": 1.0}
    diff, lo, hi = paired_difference(a, b, n=2_000)
    assert diff == 0.5 and 0.0 <= lo <= hi <= 1.0
