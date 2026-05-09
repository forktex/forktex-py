# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.
#
# For commercial licensing -- including use in proprietary products, SaaS
# deployments, or any context where AGPL obligations cannot be met -- you
# MUST obtain a commercial license from FORKTEX S.R.L. (info@forktex.com).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
forktex.agent.cli - CLI dispatcher for the ForkTex software delivery toolkit.

Top-level shape (all three integrations are peers):

    forktex                          bare REPL / menu
    forktex status                   aggregate credential state (all 3 services)
    forktex cloud <…>                cloud operations + connect / disconnect
    forktex intelligence <…>         intelligence operations + connect / disconnect
    forktex network <…>              network operations + connect / disconnect
    forktex fsd / arch / git / local / overview / present / agents / info
"""
# ruff: noqa: E402

import asyncio
import sys

import asyncclick as click

from forktex.agent.ui.console import console
from forktex.agent.ui.display import CLI_VERSION

_CLOUD_IMPORT_ERROR: ModuleNotFoundError | None = None


def _require_cloud_support() -> None:
    if _CLOUD_IMPORT_ERROR is None:
        return
    raise click.ClickException(
        "Cloud commands are unavailable because the optional "
        f"dependency {_CLOUD_IMPORT_ERROR.name!r} is not installed."
    )


# =============================================================================
# CLI Root
# =============================================================================


@click.group(invoke_without_command=True)
@click.version_option(version=CLI_VERSION, prog_name="forktex")
@click.option("--project", "-d", default=None, help="Project directory")
@click.pass_context
async def cli(ctx, project):
    """ForkTex — software delivery toolkit CLI.

    Plan, build, deploy, observe, and query your projects from one tool.
    Run with no subcommand to open an interactive menu (and chat with an
    AI assistant when one is configured).
    """
    if ctx.invoked_subcommand is None:
        # Bare `forktex` opens the REPL — register a long-running instance
        # and ensure the project's .forktex/ is installed if there is one.
        from forktex.runtime.lifecycle import deactivate, ensure_runtime
        from forktex.agent.root_loop import run as _root_run

        rec = ensure_runtime(
            needs_project=False,
            long_running=True,
            kind="repl",
            project_hint=project,
        )
        try:
            await _root_run(project=project)
        finally:
            if rec is not None:
                deactivate(rec)


# =============================================================================
# Core Commands
# =============================================================================


# =============================================================================
# Top-level `forktex status` — project + environment + auth at a glance
# =============================================================================

from forktex.agent.auth import status_cmd as _status_cmd

cli.add_command(_status_cmd)


# =============================================================================
# Intelligence service (chat, ask, run, scrape, index-ecosystem, sync, disconnect, status)
# =============================================================================

from forktex.agent.intelligence.cli import register_intelligence_commands

register_intelligence_commands(cli)


# =============================================================================
# Cloud service
# =============================================================================

try:
    from forktex.agent.cloud import cloud
except ModuleNotFoundError as exc:
    _CLOUD_IMPORT_ERROR = exc
else:
    cli.add_command(cloud)


# =============================================================================
# Network service
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

from forktex.agent.graph import graph as graph_group
from forktex.agent.manual import manual as manual_group
from forktex.agent.purge import clean_cmd
from forktex.agent.serve import serve_cmd
from forktex.graph.io_proxy import install_audit_hook

install_audit_hook()
cli.add_command(graph_group)
cli.add_command(manual_group)
cli.add_command(serve_cmd)
cli.add_command(clean_cmd)


# =============================================================================
# Catalog atoms as first-class CLI commands
# =============================================================================
# Every FSD atom from the bundled standard becomes a top-level
# `forktex <atom>` command (1:1 with the catalog). Bare `forktex`
# stays the runtime agent (chat REPL) — this only adds new verbs.
# Atoms whose IDs collide with an existing command/group are skipped
# (the existing surface owns the name); for `manual`, the group's
# `invoke_without_command=True` body owns the no-subverb dispatch.

from forktex.agent.atoms import register_atom_commands as _register_atom_commands
from forktex.fsd.loader import load_standard as _load_standard

try:
    _atom_manifest = None
    try:
        from forktex.core.paths import find_project_root as _find_root
        from forktex.manifest.models import ForktexManifest as _ForktexManifest

        _root = _find_root(__import__("pathlib").Path.cwd())
        if _root is not None:
            _atom_manifest = _ForktexManifest.load(_root / "forktex.json")
    except Exception:
        # Manifest is optional for atom registration — variant axes
        # just stay empty when there's no manifest in scope.
        _atom_manifest = None
    _register_atom_commands(cli, standard=_load_standard(), manifest=_atom_manifest)
except Exception as exc:  # pragma: no cover — defensive
    console.print(f"[yellow]warn:[/yellow] atom CLI registration failed: {exc}")


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
