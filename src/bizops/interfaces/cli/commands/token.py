"""bizops token issue | revoke: bearer credentials for the HTTP transport."""

from __future__ import annotations

import typer

from bizops.infrastructure.container import build_container

app = typer.Typer(no_args_is_help=True, help="Issue or revoke a principal's bearer token.")


def _split(principal: str) -> tuple[str, str]:
    if "/" not in principal:
        raise typer.BadParameter("use tenant/user, e.g. acme/carol")
    tenant, user = principal.split("/", 1)
    return tenant, user


@app.command()
def issue(principal: str = typer.Argument(..., help="tenant/user")) -> None:
    """Print a new token once. Only its hash is stored; any earlier token for this principal stops working."""
    tenant, user = _split(principal)
    typer.echo(build_container().tenants.issue_token(tenant, user))


@app.command()
def revoke(principal: str = typer.Argument(..., help="tenant/user")) -> None:
    """Remove the principal's token: every request with it gets a 401."""
    tenant, user = _split(principal)
    build_container().tenants.revoke_token(tenant, user)
    typer.echo(f"revoked {principal}")


__all__ = ["app"]
