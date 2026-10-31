"""Schema-scaling experiment: what each surface costs, and whether retrieval still finds the right capability,
as the catalogue grows from the 25 real capabilities to ~1,000 with near-miss distractors.

    uv run python -m bench.scaling.experiment --out bench/results/scaling

Measured per size, all deterministic except the token counts (which come from the count_tokens endpoint):
  static_tokens       every capability as a tool, as the API counts it
  tool_search_tokens  the same tools deferred behind the tool search tool
  discover_tokens     the three bizops tools (independent of size by construction; measured anyway)
  recall@k            share of pilot tasks for which discover's top-k contains the required capabilities
  signature_complete  share of hits whose signature lists every parameter of the capability (by design 1.0)
  search_ms           p50 latency of one discover search
Model-in-the-loop selection accuracy at each size is a separate, paid probe (--probe)."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from statistics import median
from typing import Any

from bench.harness.scenario import load_scenarios
from bench.scaling.catalogue import synthetic_catalogue
from bizops.application.discovery import CapabilityIndex
from bizops.application.surfaces.discover import DISCOVER, EXECUTE, INSPECT
from bizops.application.surfaces.static import tool_description
from bizops.domain.models.capability import Capability, PolicyGates
from bizops.domain.services.signature import compact_signature, tool_name
from bizops.infrastructure.connectors import build_registry

SIZES = [25, 50, 100, 250, 500, 1000]
GATES = PolicyGates()


def catalogue(size: int) -> list[Capability]:
    real = build_registry().capabilities()
    return real + synthetic_catalogue()[: max(0, size - len(real))]


def queries(root: Path) -> list[tuple[str, list[str], list[str]]]:
    """(task text, required capabilities, any-of capabilities) from every scenario that names some."""
    out = []
    for s in load_scenarios(root):
        req, anyof = s.trajectory.required, s.trajectory.required_any
        if req or anyof:
            out.append((s.task, req, anyof))
    return out


def recall(index: CapabilityIndex, qs: list[tuple[str, list[str], list[str]]], k: int) -> float:
    hits = 0
    for task, req, anyof in qs:
        top = {c.name for c, _ in index.search(task, k)}
        hits += all(r in top for r in req) and (not anyof or any(a in top for a in anyof))
    return hits / len(qs)


def static_tools(caps: list[Capability]) -> list[dict[str, Any]]:
    return [
        {
            "name": tool_name(c.name),
            "description": tool_description(c, GATES),
            "input_schema": c.input_schema(),
        }
        for c in caps
    ]


async def count(client: Any, model: str, tools: list[dict[str, Any]] | None) -> int:
    msg = [{"role": "user", "content": "hello"}]
    kwargs: dict[str, Any] = {"model": model, "messages": msg}
    if tools:
        kwargs["tools"] = tools
    return int((await client.messages.count_tokens(**kwargs)).input_tokens)


async def run(out: Path, model: str, scenarios: Path, k: int) -> list[dict[str, Any]]:
    from anthropic import AsyncAnthropic

    from bizops.infrastructure.settings import Settings

    client = AsyncAnthropic(api_key=Settings().anthropic_api_key)
    qs = queries(scenarios)
    base = await count(client, model, None)
    discover_tools = [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in (DISCOVER, EXECUTE, INSPECT)
    ]
    discover_tokens = await count(client, model, discover_tools) - base
    rows = []
    for size in SIZES:
        caps = catalogue(size)
        index = CapabilityIndex(caps)
        timings = []
        for task, _, _ in qs:
            t0 = time.perf_counter()
            index.search(task, k)
            timings.append((time.perf_counter() - t0) * 1000)
        hits = [c for task, _, _ in qs for c, _ in index.search(task, k)]
        complete = sum(all(p.name in compact_signature(c) for p in c.parameters) for c in hits) / max(
            len(hits), 1
        )
        st = static_tools(caps)
        deferred = [
            {"type": "tool_search_tool_bm25_20251119", "name": "tool_search_tool_bm25"},
            *({**t, "defer_loading": True} for t in st),
        ]
        row = {
            "size": len(caps),
            "static_tokens": await count(client, model, st) - base,
            "tool_search_tokens": await count(client, model, deferred) - base,
            "discover_tokens": discover_tokens,
            f"recall@{k}": round(recall(index, qs, k), 3),
            "recall@3": round(recall(index, qs, 3), 3),
            "signature_complete": round(complete, 3),
            "search_ms_p50": round(median(timings), 3),
            "queries": len(qs),
        }
        rows.append(row)
        print(json.dumps(row), flush=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "scaling.json").write_text(json.dumps(rows, indent=2))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="bench/results/scaling")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--scenarios", default="bench/scenarios")
    ap.add_argument("--k", type=int, default=8)
    args = ap.parse_args()
    asyncio.run(run(Path(args.out), args.model, Path(args.scenarios), args.k))


if __name__ == "__main__":
    main()
