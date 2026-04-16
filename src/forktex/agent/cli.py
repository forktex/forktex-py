"""
forktex.agent.cli - CLI dispatcher for Forktex.

Commands:
- Intelligence commands: chat, ask, run
- Cloud commands: cloud ...
- Core commands: init, info
"""
# ruff: noqa: E402

import asyncio
import sys
from pathlib import Path

import asyncclick as click
from rich.panel import Panel
from rich.prompt import Prompt

from forktex.agent.ui.console import console, info
from forktex.agent.ui.display import CLI_VERSION


def _get_project_root() -> str:
    return str(Path.cwd().absolute())


# =============================================================================
# CLI Root
# =============================================================================

@click.group(invoke_without_command=True)
@click.version_option(version=CLI_VERSION, prog_name="forktex")
@click.option("--project", "-d", default=None, help="Project directory")
@click.pass_context
async def cli(ctx, project):
    """Forktex - Development Toolkit

    AI-powered development assistant, cloud infrastructure management,
    and core development utilities.

    Run without a subcommand to start interactive chat.
    """
    if ctx.invoked_subcommand is None:
        from forktex.agent.intelligence.cli.chat import chat as _chat_fn
        await ctx.invoke(_chat_fn, project=project)


# =============================================================================
# Core Commands
# =============================================================================

@cli.command(name="init")
@click.option("--project", "-d", default=None, help="Project directory")
async def init_cmd(project):
    """Interactive setup wizard.

    Configures Intelligence API and/or Cloud services for this project.
    """
    project_root = project or _get_project_root()

    console.print(Panel.fit(
        "[bold]Forktex Setup[/bold]\n\n"
        "Configure Forktex for this project.\n"
        f"Project root: [cyan]{project_root}[/cyan]",
        border_style="blue",
    ))
    console.print()

    choice = Prompt.ask(
        "[bold]What would you like to configure?[/bold]",
        choices=["intelligence", "cloud", "both"],
        default="intelligence",
    )

    if choice in ("intelligence", "both"):
        info("Setting up Intelligence API...")
        from forktex.agent.intelligence.cli.init import init_cmd as intel_init
        ctx = click.get_current_context()
        await ctx.invoke(intel_init, project=project_root, save_global=False)

    if choice in ("cloud", "both"):
        info("Setting up Cloud...")
        from forktex.agent.cloud.login import login
        ctx = click.get_current_context()
        await ctx.invoke(login)


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
        "Installed modules: intelligence, cloud, agent",
    ]

    console.print(Panel.fit(
        "\n".join(lines),
        title="Info",
        border_style="blue",
    ))

    # Show intelligence config
    from forktex_intelligence.config import get_intelligence_settings
    settings = get_intelligence_settings(project_root=project_root)
    console.print("\n[bold]Intelligence API:[/bold]")
    console.print(f"  Endpoint: {settings.endpoint}")
    console.print(f"  API Key: {'***' + settings.api_key[-4:] if settings.api_key else 'not set'}")

    # Show cloud config
    from forktex_cloud.config import CloudContext
    cloud_ctx = CloudContext.load(Path(project_root))
    console.print("\n[bold]Cloud:[/bold]")
    console.print(f"  Controller: {cloud_ctx.controller or 'not set'}")
    console.print(f"  Connected: {cloud_ctx.is_connected}")


# Rename info_cmd to 'info' for CLI
info_cmd.name = "info"


# =============================================================================
# Intelligence Commands
# =============================================================================

from forktex.agent.intelligence.cli import register_intelligence_commands
register_intelligence_commands(cli)


# =============================================================================
# Cloud Commands
# =============================================================================

from forktex.agent.cloud import cloud
cli.add_command(cloud)


# =============================================================================
# Agent Commands
# =============================================================================

from forktex.agent.commands.agents import agents
from forktex.agent.commands.ground import ground
from forktex.agent.commands.root_agent import root_agent
agents.add_command(ground)
agents.add_command(root_agent)
cli.add_command(agents)


# =============================================================================
# Scraper Command
# =============================================================================

from forktex.agent.scraper.cli import scrape
cli.add_command(scrape)


# =============================================================================
# FSD Commands (ForkTex Standard for Delivery)
# =============================================================================

from forktex.agent.fsd import fsd
cli.add_command(fsd)


# =============================================================================
# Git Commands (multi-project operations)
# =============================================================================

from forktex.agent.commands.git_cli import git
cli.add_command(git)


# =============================================================================
# Architecture Commands (C4 model auto-discovery)
# =============================================================================

from forktex.agent.fsd.arch_cli import arch
cli.add_command(arch)

from forktex.agent.fsd.overview import overview
cli.add_command(overview)

from forktex.agent.fsd.present import present
cli.add_command(present)


# =============================================================================
# Local Commands (multi-project local environment)
# =============================================================================

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
