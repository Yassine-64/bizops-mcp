"""bizops serve: the MCP server over stdio for one principal."""

from __future__ import annotations

from typing import Any

import anyio
import typer

from bizops.application.config import ControlPlaneConfig
from bizops.infrastructure.container import build_container
from bizops.infrastructure.settings import Settings


def serve(
    surface: str = typer.Option("discover", help="discover | static"),
    principal: str | None = typer.Option(None, help="tenant/user; defaults to BIZOPS_PRINCIPAL"),
) -> None:
    """Serve the control plane to an MCP client over stdio."""
    from mcp.server.stdio import stdio_server

    from bizops.interfaces.mcp_server import build_server

    settings = Settings()
    config = ControlPlaneConfig.load(settings.config_path).model_copy(update={"surface": surface})
    container = build_container(settings, config)
    from bizops.infrastructure.telemetry import configure_tracing

    configure_tracing(settings.data_dir)
    spec = principal or settings.principal
    if not spec or "/" not in spec:
        raise typer.BadParameter("pass --principal tenant/user or set BIZOPS_PRINCIPAL")
    tenant, user = spec.split("/", 1)
    who = container.tenants.principal(tenant, user)
    if who is None:
        raise typer.BadParameter(f"unknown principal {spec}; run `bizops seed --tenant {tenant}` first")
    server = build_server(container.surface(config.surface), lambda _ctx: who)

    async def main() -> Any:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(main)


def approve(
    run_id: str = typer.Argument(..., help="the paused run"),
    step: int = typer.Argument(..., help="step number shown by inspect"),
    decline: bool = typer.Option(False, help="decline instead of approving"),
    by: str = typer.Option("operator", help="recorded as the approver"),
) -> None:
    """Approve or decline a paused step out of band. The agent continues with execute(run_id)."""
    container = build_container()
    run = container.journal.get_run(run_id)
    if run is None:
        raise typer.BadParameter(f"no run {run_id}")
    outcome = container.approvals.resolve_as_operator(
        run_id=run_id, step_id=f"{run_id}_s{step}", tenant=run.tenant, approve=not decline, by=by
    )
    typer.echo(f"{run_id} step {step}: {outcome}")
    if not outcome.resolved:
        raise typer.Exit(1)


def replay(run_id: str = typer.Argument(..., help="a recorded run")) -> None:
    """Re-run a recorded run through today's policy and executor against its recorded connector results."""
    import tempfile
    from pathlib import Path

    from bizops.application.replay import Replayer
    from bizops.infrastructure.journal import SqliteJournal

    container = build_container()
    scratch = Path(tempfile.mkdtemp()) / "replay.db"
    replayer = Replayer(
        container.journal,
        container.registry,
        container.gates,
        container.tenants.principal,
        lambda: SqliteJournal(scratch),
        container.clock,
        container.wall_clock,
    )
    report = anyio.run(replayer.replay, run_id)
    for d in report.divergences:
        typer.echo(f"step {d.step} {d.field}: recorded {d.recorded!r}, replayed {d.replayed!r}")
    typer.echo(f"{run_id}: {report.steps} steps, {len(report.divergences)} divergences")
    if not report.clean:
        raise typer.Exit(1)


__all__ = ["approve", "replay", "serve"]
