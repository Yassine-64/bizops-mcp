"""REPORT.md from raw rows. Every number in the README tables is pasted from here."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from bench.harness.stats import bootstrap_mean, by_scenario, paired_difference, percentile

Row = dict[str, Any]


TRANSIENT = (
    "APITimeoutError",
    "APIConnectionError",
    "InternalServerError",
    "OverloadedError",
    "RateLimitError",
)


def _load(d: Path) -> tuple[list[Row], int]:
    """Graded rows, and the number excluded because the API or network failed after every retry."""
    rows = [json.loads(line) for line in (d / "results.jsonl").read_text().splitlines() if line.strip()]
    graded = [r for r in rows if not str(r.get("error") or "").startswith(TRANSIENT)]
    return graded, len(rows) - len(graded)


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def table_a(rows: list[Row], surfaces: dict[str, int]) -> str:
    out = [
        "| Surface | Success (95% CI) | Trajectory correct | Approval correct | Billed input tok | Output tok "
        "| Surface tok | Calls | $/task | p50 / p95 s |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for arm in ("static", "tool_search", "discover"):
        rs = [r for r in rows if r["arm"] == arm and r["config"] == "full"]
        if not rs:
            continue
        succ, lo, hi = bootstrap_mean(list(by_scenario(rs, lambda r: float(r["task_success"])).values()))
        lat = [r["latency_ms"] / 1000 for r in rs]
        out.append(
            f"| {arm} | {_pct(succ)} ({_pct(lo)}–{_pct(hi)}) | {_pct(mean(r['trajectory_ok'] for r in rs))} "
            f"| {_pct(mean(r['approval_correct'] for r in rs))} | {mean(r['billed_input_tokens'] for r in rs):,.0f} "
            f"| {mean(r['usage']['output_tokens'] for r in rs):,.0f} | {surfaces.get(arm, 0):,} "
            f"| {mean(r['tool_calls'] for r in rs):.1f} | ${mean(r['cost_usd'] for r in rs):.4f} "
            f"| {percentile(lat, 0.5):.1f} / {percentile(lat, 0.95):.1f} |"
        )
    return "\n".join(out)


def paired(rows: list[Row]) -> str:
    full = [r for r in rows if r["config"] == "full"]
    succ = {
        a: by_scenario([r for r in full if r["arm"] == a], lambda r: float(r["task_success"]))
        for a in ("static", "tool_search", "discover")
    }
    tok = {
        a: by_scenario([r for r in full if r["arm"] == a], lambda r: float(r["billed_input_tokens"]))
        for a in ("static", "tool_search", "discover")
    }
    lines = [
        "| Comparison | Δ success (95% CI) | Δ billed input tokens (95% CI) | Scenarios |",
        "|---|---|---|---|",
    ]
    for a, b in (("static", "discover"), ("tool_search", "discover"), ("static", "tool_search")):
        if not succ[a] or not succ[b]:
            continue
        d, lo, hi = paired_difference(succ[a], succ[b])
        t, tlo, thi = paired_difference(tok[a], tok[b])
        n = len(set(succ[a]) & set(succ[b]))
        lines.append(
            f"| {b} vs {a} | {100 * d:+.0f} pts ({100 * lo:+.0f}, {100 * hi:+.0f}) "
            f"| {t:+,.0f} ({tlo:+,.0f}, {thi:+,.0f}) | {n} |"
        )
    return "\n".join(lines)


def per_scenario(rows: list[Row]) -> str:
    cells: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["config"] == "full":
            cells[r["scenario"]][r["arm"]].append(bool(r["task_success"]))
    arms = [a for a in ("static", "tool_search", "discover") if any(a in c for c in cells.values())]
    lines = ["| Scenario | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    for sid in sorted(cells):
        lines.append(
            f"| {sid} | "
            + " | ".join(f"{sum(cells[sid][a])}/{len(cells[sid][a])}" if cells[sid][a] else "–" for a in arms)
            + " |"
        )
    return "\n".join(lines)


def table_b(rows: list[Row]) -> str:
    out = [
        "| Control plane | Risky actions without approval | Approval errors | Duplicate effects "
        "| Uncertain writes | Runs |",
        "|---|---|---|---|---|---|",
    ]
    for config in ("scopes-only", "approvals-only", "full"):
        rs = [r for r in rows if r["config"] == config and r["arm"] == "discover"]
        if not rs:
            continue
        out.append(
            f"| {config} | {sum(r['unapproved_risky'] for r in rs)} "
            f"| {sum(not r['approval_correct'] for r in rs)} | {sum(r['duplicate_effects'] for r in rs)} "
            f"| {sum(r['uncertain_writes'] for r in rs)} | {len(rs)} |"
        )
    return "\n".join(out)


def gates(rows: list[Row], excluded: int) -> str:
    full = [r for r in rows if r["config"] == "full"]
    leaks = sum(bool(r["leaked"]) for r in full)
    bypass = sum(len(r["forbidden_executed"]) for r in full)
    errors = sum(bool(r["error"]) for r in rows)
    return (
        f"- cross-tenant leaks: **{leaks}**\n- forbidden capabilities executed: **{bypass}**\n"
        f"- graded runs with an error: {errors}\n- runs excluded after three transient API failures: {excluded}"
    )


def write_report(d: Path) -> str:
    rows, excluded = _load(d)
    surfaces = json.loads((d / "surfaces.json").read_text()) if (d / "surfaces.json").exists() else {}
    models = sorted({r["model"] for r in rows})
    repeats = max(r["repeat"] for r in rows) + 1
    text = (
        "\n\n".join(
            [
                f"# BizOpsBench report: {d.name}",
                f"Model {', '.join(models)}; {len({r['scenario'] for r in rows})} scenarios; {repeats} repeat(s); "
                f"{len(rows)} runs; total ${sum(r['cost_usd'] for r in rows):.2f}.",
                "## Table A: the interface (full control plane behind every surface)",
                table_a(rows, surfaces),
                "## Paired differences",
                paired(rows),
                "## Table B: control-plane ablation (discover surface)",
                table_b(rows),
                "## Invariant gates (full configuration)",
                gates(rows, excluded),
                "## Per scenario (successes / runs)",
                per_scenario(rows),
            ]
        )
        + "\n"
    )
    (d / "REPORT.md").write_text(text)
    return text


__all__ = ["write_report"]
