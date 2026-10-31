"""Run BizOpsBench: scenarios x arms x repeats against fresh copies of the seeded company.

    uv run python -m bench run --scenarios bench/scenarios/pilot --arms static,discover --repeat 2
    uv run python -m bench report bench/results/pilot

Each run gets its own data directory (a byte copy of the seeded tenants) and its own journal, so runs never
see each other's side effects. Raw rows go to <out>/results.jsonl; nothing is aggregated at run time."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from bench.harness.agent import Arm, api_tools, run_agent
from bench.harness.grade import grade
from bench.harness.scenario import Scenario, load_scenarios
from bench.scaling.distractors import with_distractors
from bizops.application.config import ControlPlaneConfig
from bizops.infrastructure.config.settings import Settings
from bizops.infrastructure.di.container import build_container
from bizops.infrastructure.seed import seed_tenant

PRICES = {  # $/MTok: input, output, cache write (1.25x input), cache read
    "claude-sonnet-5-5": (2.0, 10.0, 2.5, 0.20),
    "claude-opus-5-5": (4.0, 20.0, 5.0, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01),
}
CONFIGS = {
    "full": ControlPlaneConfig(name="full"),
    "approvals-only": ControlPlaneConfig(name="approvals-only", journal=False),
    "scopes-only": ControlPlaneConfig(name="scopes-only", approvals=False, journal=False),
}


def cost(model: str, usage: dict[str, int]) -> float:
    p_in, p_out, p_cw, p_cr = PRICES.get(model, PRICES["claude-sonnet-5-5"])
    return (
        usage["input_tokens"] * p_in
        + usage["output_tokens"] * p_out
        + usage["cache_write_tokens"] * p_cw
        + usage["cache_read_tokens"] * p_cr
    ) / 1e6


TRANSIENT = (
    "APITimeoutError",
    "APIConnectionError",
    "InternalServerError",
    "OverloadedError",
    "RateLimitError",
)


def transient(row: dict[str, Any]) -> bool:
    """Network and capacity failures are not model behaviour: they are retried, never graded."""
    return bool(row.get("error")) and str(row["error"]).startswith(TRANSIENT)


def _key(row: dict[str, Any]) -> tuple[str, str, str, int, int]:
    return (row["scenario"], row["arm"], row["config"], int(row["repeat"]), int(row.get("catalogue", 25)))


def _real_size(catalogue: int) -> int:
    """The catalogue size a run records: the real capabilities, or the padded total."""
    from bizops.infrastructure.connectors import build_registry

    return max(catalogue, len(build_registry()))


def _template(root: Path, seed: int) -> Path:
    tpl = root / "template"
    if not (tpl / "acme.db").exists():
        tpl.mkdir(parents=True, exist_ok=True)
        for tenant in ("acme", "globex"):
            seed_tenant(tpl, tenant, seed)
    return tpl


async def run_one(
    client: Any,
    scenario: Scenario,
    arm: Arm,
    config: ControlPlaneConfig,
    model: str,
    repeat: int,
    work: Path,
    template: Path,
    catalogue: int = 0,
) -> dict[str, Any]:
    data = work / uuid.uuid4().hex[:10]
    shutil.copytree(template, data)
    try:
        settings = Settings(_env_file=None, data_dir=data, llm="anthropic", model=model)  # type: ignore[call-arg]
        surface_name = "discover" if arm == "discover" else "static"
        container = build_container(settings, config.model_copy(update={"surface": surface_name}))
        if catalogue:
            container = container.with_registry(with_distractors(container.registry, catalogue))
        if scenario.chaos:
            container = container.with_chaos(scenario.chaos.profile, scenario.chaos.capability)
        tenant, user = scenario.principal.split("/")
        principal = container.tenants.principal(tenant, user)
        assert principal is not None, scenario.principal
        surface = container.surface(surface_name)
        t = await run_agent(
            client,
            model=model,
            surface=surface,
            arm=arm,
            principal=principal,
            task=scenario.task,
            human=scenario.human,
        )
        g = grade(scenario, t, data, sqlite3.connect(data / "journal.db"), container.registry)
        usage = t.usage.__dict__
        return {
            "scenario": scenario.id,
            "category": scenario.category,
            "arm": arm,
            "config": config.name,
            "model": model,
            "repeat": repeat,
            "catalogue": len(container.registry),
            **g.as_dict(),
            "usage": usage,
            "billed_input_tokens": usage["input_tokens"]
            + usage["cache_write_tokens"]
            + usage["cache_read_tokens"],
            "cost_usd": round(cost(model, usage), 6),
            "tool_calls": len(t.tool_calls),
            "calls": t.tool_calls,
            "approvals": t.approvals,
            "turns": t.turns,
            "latency_ms": round(t.latency_ms),
            "stop_reason": t.stop_reason,
            "error": t.error,
            "final_answer": t.final_answer,
        }
    finally:
        shutil.rmtree(data, ignore_errors=True)


async def surface_tokens(
    client: Any, model: str, template: Path, arms: list[Arm], catalogue: int = 0
) -> dict[str, int]:
    """Serialized tool-surface size as the API counts it: tokens with the tools minus tokens without."""
    data = template.parent / "surface-probe"
    shutil.copytree(template, data, dirs_exist_ok=True)
    container = build_container(
        Settings(_env_file=None, data_dir=data, llm="anthropic"), ControlPlaneConfig()
    )  # type: ignore[call-arg]
    if catalogue:
        container = container.with_registry(with_distractors(container.registry, catalogue))
    msg = [{"role": "user", "content": "hello"}]
    base = (await client.messages.count_tokens(model=model, messages=msg)).input_tokens
    out = {}
    for arm in arms:
        tools = api_tools(container.surface("discover" if arm == "discover" else "static"), arm)
        n = (await client.messages.count_tokens(model=model, messages=msg, tools=tools)).input_tokens
        out[arm] = n - base
    shutil.rmtree(data, ignore_errors=True)
    return out


async def main_run(args: argparse.Namespace) -> None:
    from anthropic import AsyncAnthropic

    settings = Settings()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key, max_retries=4, timeout=180.0)
    scenarios = load_scenarios(Path(args.scenarios))
    if args.only:
        scenarios = [s for s in scenarios if s.id in set(args.only.split(","))]
    if args.categories:
        scenarios = [s for s in scenarios if s.category in set(args.categories.split(","))]
    arms: list[Arm] = [a for a in args.arms.split(",")]  # type: ignore[misc]
    out = Path(args.out)
    work = out / ".work"
    template = _template(work, args.seed)
    out.mkdir(parents=True, exist_ok=True)
    surfaces_file = out / "surfaces.json"
    surfaces = json.loads(surfaces_file.read_text()) if surfaces_file.exists() else {}
    size = args.catalogue or 0
    surfaces[str(size)] = await surface_tokens(client, args.model, template, arms, size)
    surfaces_file.write_text(json.dumps(surfaces, indent=2))

    results = out / "results.jsonl"
    kept: list[str] = []
    done_keys: set[tuple[str, str, str, int, int]] = set()
    if results.exists():  # resume: keep graded rows, drop transient failures so they run again
        for line in results.read_text().splitlines():
            row = json.loads(line)
            if not transient(row):
                kept.append(line)
                done_keys.add(_key(row))
        results.write_text("".join(f"{line}\n" for line in kept))
    jobs = [
        (s, a, c, r)
        for r in range(args.repeat)
        for s in scenarios
        for a in arms
        for c in args.configs.split(",")
        if (s.id, a, c, r, _real_size(args.catalogue)) not in done_keys
    ]
    sem = asyncio.Semaphore(args.concurrency)
    sink = results.open("a")
    done = 0
    started = time.time()

    async def job(s: Scenario, a: Arm, c: str, r: int) -> None:
        nonlocal done
        async with sem:
            for attempt in range(1, 4):
                row = await run_one(client, s, a, CONFIGS[c], args.model, r, work, template, args.catalogue)
                row["attempt"] = attempt
                if not transient(row):
                    break
                await asyncio.sleep(5 * attempt)
        sink.write(json.dumps(row, default=str) + "\n")
        sink.flush()
        done += 1
        mark = "ok " if row["task_success"] else "FAIL"
        print(
            f"[{done}/{len(jobs)}] {mark} {s.id:28} {a:12} {c:14} r{r} calls={row['tool_calls']:2} "
            f"in={row['billed_input_tokens']:6} ${row['cost_usd']:.4f} {row['error'] or ''}",
            flush=True,
        )

    await asyncio.gather(*(job(*j) for j in jobs))
    sink.close()
    print(f"{len(jobs)} runs in {time.time() - started:.0f}s -> {out / 'results.jsonl'}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m bench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--scenarios", default="bench/scenarios/pilot")
    r.add_argument("--arms", default="static,tool_search,discover")
    r.add_argument("--configs", default="full")
    r.add_argument("--model", default="claude-sonnet-5-5")
    r.add_argument("--repeat", type=int, default=1)
    r.add_argument("--concurrency", type=int, default=4)
    r.add_argument("--seed", type=int, default=42)
    r.add_argument("--only", default="", help="comma-separated scenario ids")
    r.add_argument(
        "--categories", default="", help="comma-separated categories, e.g. approval,failure,security"
    )
    r.add_argument("--out", default="bench/results/pilot")
    r.add_argument("--catalogue", type=int, default=0, help="pad the catalogue with distractors to this size")
    p = sub.add_parser("report")
    p.add_argument("dir")
    args = ap.parse_args()
    if args.cmd == "run":
        asyncio.run(main_run(args))
    else:
        from bench.harness.report import write_report

        print(write_report(Path(args.dir)))


__all__ = ["main"]
