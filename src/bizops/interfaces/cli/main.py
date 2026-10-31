"""bizops: serve | seed | approve | runs | replay | bench. Commands are registered as they land."""

from __future__ import annotations

import typer

from bizops.interfaces.cli.commands import seed as seed_cmd
from bizops.interfaces.cli.commands import serve as serve_cmd
from bizops.interfaces.cli.commands import token as token_cmd

app = typer.Typer(no_args_is_help=True, add_completion=False, help="An evaluated control plane for agents.")


@app.callback()
def _root() -> None:
    """bizops command group."""


@app.command()
def version() -> None:
    """Print the installed version."""
    from importlib.metadata import version as v

    typer.echo(v("bizops"))


app.command("seed")(seed_cmd.seed)
app.command("serve")(serve_cmd.serve)
app.command("approve")(serve_cmd.approve)
app.command("replay")(serve_cmd.replay)
app.add_typer(token_cmd.app, name="token")

__all__ = ["app"]
