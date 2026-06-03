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

Top-level shape (the agent-first surface; see ``cli_help.CATEGORIES``):

    forktex                          bare REPL / menu
    forktex chat / run               talk to the agent · orchestrated task
    forktex knowledge <…>            the substrate — search · recycle · ingest · mcp
    forktex arch <…>                 structural authority — build · show · c4 · search · serve
    forktex cloud <…>                deploy & operate (+ connect / disconnect)
    forktex fsd <…>                  delivery standard — check / report / makefile
    forktex auth <…>                 aggregate credential state across services
    forktex clean                    purge .forktex/ artefacts

Loading model
-------------

Subcommand modules import **lazily** via :class:`AsyncLazyGroup` — the user
only pays for what they invoke. ``forktex --help`` lists every command without
importing any of them (the lazy entries declare a dotted-path spec; the leaf
loads on first ``get_command``). Only the bits that need to run on every
invocation stay eager here: the audit hook (graph io tracking) and FSD-atom
registration (it reads the project manifest to add manifest-derived verbs to
``--help``).
"""
# ruff: noqa: E402

import asyncio
import sys

import asyncclick as click

from forktex.agent.lazy_group import AsyncLazyGroup
from forktex.agent.ui.console import console
from forktex.agent.ui.display import CLI_VERSION

# =============================================================================
# CLI Root
# =============================================================================


@click.group(cls=AsyncLazyGroup, invoke_without_command=True)
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
# Audit hook — must run before any file-mutating command, so eager.
# =============================================================================

from forktex.graph.io_proxy import install_audit_hook

install_audit_hook()


# =============================================================================
# Lazy subcommand registrations — the final v0.7.0 root taxonomy.
# =============================================================================
# 10 deliberate keys, no FSD-atom mirroring: forktex is the agentic CLI; ``make``
# owns the lifecycle. The grouping below mirrors the categories rendered by
# ``forktex --help`` (see :mod:`forktex.agent.cli_help`).
#
# Bare ``forktex`` (above) still opens the chat REPL. ``forktex chat`` is the
# explicit alias; ``forktex run`` is the orchestrated agentic task. The
# ``intelligence`` / ``agents`` / ``network`` groups and the ``mcp`` / ``serve``
# / ``status`` leaf commands no longer exist at root — see the BREAKING CHANGES
# section of forktex-py/CHANGELOG.md (0.7.0) for the per-command migration.

# Core (the agentic identity).
cli.add_lazy_command(
    "chat",
    "forktex.agent.intelligence.cli.chat:chat",
    short_help="Open the interactive chat REPL.",
)
cli.add_lazy_command(
    "run",
    "forktex.agent.intelligence.cli.run:run",
    short_help="Run an orchestrated agentic task with tools.",
)
cli.add_lazy_command(
    "plan",
    "forktex.agent.workflow.cli:plan",
    short_help="Craft a multi-agent plan and execute it.",
)

# Grounding (the substrate the agent reads).
cli.add_lazy_command(
    "knowledge",
    "forktex.agent.knowledge.cli:knowledge",
    short_help="Doctrine + project lessons (search, recycle, ingest, mcp, …).",
    optional=True,
    install_hint="pip install 'forktex-core[fractal]'",
)
cli.add_lazy_command(
    "arch",
    "forktex.agent.graph:arch",
    short_help="Structural authority — build · show · c4 · search · serve.",
)

# Services.
cli.add_lazy_command(
    "cloud",
    "forktex.agent.cloud:cloud",
    short_help="Deploy, manage, observe your infrastructure.",
    optional=True,
    install_hint="pip install 'forktex[cloud]'  # or fix the import error in forktex.agent.cloud",
)
cli.add_lazy_command(
    "fsd",
    "forktex.agent.fsd:fsd",
    short_help="Verify your project against the delivery standard.",
)
cli.add_lazy_command(
    "auth",
    "forktex.agent.auth:auth",
    short_help="Sign-in state + credentials across services (default action: status).",
)
cli.add_lazy_command(
    "serve",
    "forktex.api.serve:serve_cmd",
    short_help="Serve the generic tool API — knowledge · arch · fsd over HTTP + MCP (/mcp).",
    optional=True,
    install_hint="pip install 'forktex-py[mcp]'",
)

# Housekeeping.
cli.add_lazy_command(
    "clean",
    "forktex.agent.purge:clean_cmd",
    short_help="Purge .forktex/ artefacts.",
)


# FSD atom mirroring (``forktex test`` / ``build`` / ``lint`` / …) was removed
# in 0.7.0 — ``make`` owns lifecycle. The dispatcher in ``forktex.agent.atoms``
# stays importable for any downstream tooling that needs to construct atom
# ``Make`` targets programmatically; only the CLI registration is gone.
# ``forktex fsd check`` continues to work (it reads the static Makefile and
# never depended on atom dispatch). See ``forktex-py/CHANGELOG.md`` (0.7.0
# BREAKING CHANGES) and the ``convention.root-taxonomy`` knowledge lesson for
# the rationale.


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
