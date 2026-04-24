"""
forktex.agent.cli - CLI dispatcher for Forktex.

Top-level shape (all three facets are peers):

    forktex                          bare REPL / menu
    forktex status                   aggregate credential state (all 3 facets)
    forktex cloud <…>                cloud operations + sync / disconnect
    forktex intelligence <…>         intelligence operations + sync / disconnect
    forktex network <…>              network operations + sync / disconnect
    forktex fsd / arch / git / local / overview / present / agents / info
"""
# ruff: noqa: E402

import asyncio
import sys
from pathlib import Path

import asyncclick as click
from rich.panel import Panel

from forktex.agent.ui.console import console, info
from forktex.agent.ui.display import CLI_VERSION

_CLOUD_IMPORT_ERROR: ModuleNotFoundError | None = None


def _get_project_root() -> str:
    return str(Path.cwd().absolute())


def _require_cloud_support() -> None:
    if _CLOUD_IMPORT_ERROR is None:
        return
    raise click.ClickException(
        "Cloud commands are unavailable because the optional "
        f"dependency { _CLOUD_IMPORT_ERROR.name!r } is not installed."
    )


# =============================================================================
# CLI Root
# =============================================================================


@click.group(invoke_without_command=True)
@click.version_option(version=CLI_VERSION, prog_name="forktex")
@click.option("--project", "-d", default=None, help="Project directory")
@click.pass_context
async def cli(ctx, project):
    """Forktex — unified CLI across cloud, intelligence, and network.

    Run with no subcommand to open the menu-driven root loop
    (auto-upgrades to the intelligence chat REPL when reachable).
    """
    if ctx.invoked_subcommand is None:
        from forktex.agent.root_loop import run as _root_run

        await _root_run(project=project)


# =============================================================================
# Core Commands
# =============================================================================


@cli.command()
async def info_cmd():
    """Show project and environment information."""
    project_root = _get_project_root()

    lines = [
        f"[bold]Forktex CLI[/bold] v{CLI_VERSION}",
        "",
        f"Project Root: {project_root}",
        f"Python: {sys.version.split()[0]}",
        f"Platform: {sys.platform}",
    ]

    console.print(
        Panel.fit(
            "\n".join(lines),
            title="Info",
            border_style="blue",
        )
    )

    from forktex.agent.intelligence.settings import get_intelligence_settings

    settings = get_intelligence_settings(project_root=project_root)
    console.print("\n[bold]Intelligence API:[/bold]")
    console.print(f"  Endpoint: {settings.endpoint}")
    console.print(
        f"  API Key: {'***' + settings.api_key[-4:] if settings.api_key else 'not set'}"
    )

    console.print("\n[bold]Cloud:[/bold]")
    if _CLOUD_IMPORT_ERROR is not None:
        console.print(
            f"  Unavailable: missing optional dependency {_CLOUD_IMPORT_ERROR.name!r}"
        )
    else:
        from forktex.agent.cloud.settings import load_cloud_context

        cloud_ctx = load_cloud_context(Path(project_root))
        console.print(f"  Controller: {cloud_ctx.controller or 'not set'}")
        console.print(f"  Connected: {cloud_ctx.is_connected}")


info_cmd.name = "info"


# =============================================================================
# Top-level `forktex status` — aggregate credential state across facets
# =============================================================================

from forktex.agent.auth import status_cmd as _status_cmd

cli.add_command(_status_cmd)


# =============================================================================
# Intelligence facet (chat, ask, run, scrape, index-ecosystem, sync, disconnect, status)
# =============================================================================

from forktex.agent.intelligence.cli import register_intelligence_commands

register_intelligence_commands(cli)


# =============================================================================
# Cloud facet
# =============================================================================

try:
    from forktex.agent.cloud import cloud
except ModuleNotFoundError as exc:
    _CLOUD_IMPORT_ERROR = exc
else:
    cli.add_command(cloud)


# =============================================================================
# Network facet
# =============================================================================

from forktex.agent.network import network as network_group

cli.add_command(network_group)


# =============================================================================
# Cross-cutting groups (agents, fsd, arch, overview, present, git, local)
# =============================================================================

from forktex.agent.commands.agents import agents
from forktex.agent.commands.ground import ground
from forktex.agent.commands.root_agent import root_agent

agents.add_command(ground)
agents.add_command(root_agent)
cli.add_command(agents)

from forktex.agent.fsd import fsd

cli.add_command(fsd)

from forktex.agent.commands.git_cli import git

cli.add_command(git)

from forktex.agent.fsd.arch_cli import arch

cli.add_command(arch)

from forktex.agent.fsd.overview import overview

cli.add_command(overview)

from forktex.agent.fsd.present import present

cli.add_command(present)

from forktex.agent.commands.local_cli import local

cli.add_command(local)


# =============================================================================
# Entry Point
# =============================================================================


def main():
    """Main entry point for the CLI."""
    try:
        asyncio.run(cli(_anyio_backend="asyncio"))
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
