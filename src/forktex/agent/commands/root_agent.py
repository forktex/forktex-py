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

"""forktex agents root — Multi-repo AI assistant with full codebase context.

Starts a persistent agent that loads:
- Per-project briefings (so it knows what each project does)
- The latest architecture snapshot (services, ports, dependencies)
- Semantic search over your indexed codebase
- Filesystem + git + shell tools

Best for cross-cutting questions like *"Where does the order flow touch
each service?"* or *"What databases is the platform using?"*

Usage:
    forktex agents root
    forktex agents root --task "What databases does each platform use?"
    forktex agents root --dir ~/Desktop/forktex
"""

from __future__ import annotations

import json
from pathlib import Path

import asyncclick as click

from forktex.agent.ui.console import console, info, error
from forktex.core.paths import find_ecosystem_root, get_architecture_dir


ECOSYSTEM_SPACE = "forktex-ecosystem"


def _load_grounding(root: Path) -> str:
    """Load the ecosystem AGENTS.md as grounding context."""
    agents_md = root / "docs" / "AGENTS.md"
    if agents_md.exists():
        return agents_md.read_text(encoding="utf-8")
    return ""


def _load_architecture(root: Path) -> str:
    """Load the latest architecture snapshot summary."""
    arch_dir = get_architecture_dir(root)
    if not arch_dir.exists():
        return ""

    arch_files = sorted(arch_dir.glob("arch-*.json"))
    if not arch_files:
        return ""

    latest = arch_files[-1]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
        systems = data.get("systems", [])
        summary_lines = [
            f"Architecture snapshot ({data.get('generated_at', 'unknown')}):"
        ]
        for sys in systems:
            name = sys.get("name", "?")
            level = sys.get("fsd_level", "?")
            containers = len(sys.get("containers", []))
            summary_lines.append(f"  - {name}: {level}, {containers} containers")
        return "\n".join(summary_lines)
    except (json.JSONDecodeError, OSError):  # fmt: skip
        return ""


def _load_libraries(root: Path) -> str:
    """Load the library dependency graph summary."""
    lib_file = root / "docs" / "engineering" / "libraries.json"
    if not lib_file.exists():
        return ""

    try:
        data = json.loads(lib_file.read_text(encoding="utf-8"))
        libs = data.get("libraries", [])
        lines = ["Library catalog:"]
        for lib in libs:
            lines.append(
                f"  - {lib['name']} v{lib.get('version', '?')} ({lib['path']}) — {lib.get('description', '')}"
            )

        edges = data.get("dependency_graph", {}).get("edges", [])
        if edges:
            lines.append("Dependencies:")
            for a, b in edges:
                lines.append(f"  {a} → {b}")

        return "\n".join(lines)
    except (json.JSONDecodeError, OSError):  # fmt: skip
        return ""


def _build_system_prompt(root: Path) -> str:
    """Assemble the agent's system prompt from workspace knowledge."""
    parts = [
        "You are an AI assistant with full context of this multi-project codebase.",
        "You can reason about cross-project dependencies, architecture, and workflows.",
        "You have access to filesystem, git, shell, and web tools.",
        "",
        "When asked about the codebase, draw on the briefings below.",
        "When asked to make changes, consider the impact across every project.",
        "When unsure, search the indexed codebase for detailed context.",
        "",
    ]

    grounding = _load_grounding(root)
    if grounding:
        parts.append("=== PROJECT BRIEFINGS ===")
        parts.append(grounding)
        parts.append("")

    architecture = _load_architecture(root)
    if architecture:
        parts.append("=== ARCHITECTURE ===")
        parts.append(architecture)
        parts.append("")

    libraries = _load_libraries(root)
    if libraries:
        parts.append("=== LIBRARIES ===")
        parts.append(libraries)
        parts.append("")

    return "\n".join(parts)


@click.command(name="root")
@click.option("--dir", "-d", "root_dir", default=None, help="Workspace root directory")
@click.option(
    "--task", "-t", default=None, help="One-shot task (otherwise interactive)"
)
@click.option(
    "--type",
    "agent_type",
    default="assistant",
    help="Agent type (assistant, developer, researcher)",
)
async def root_agent(root_dir: str | None, task: str | None, agent_type: str):
    """Start a multi-repo AI assistant with full codebase context.

    Loads per-project briefings, the latest architecture snapshot, and
    (when available) a semantic index of your codebase. Best for
    cross-cutting questions and changes that ripple across projects.

    With ``--task`` runs once; without, drops into interactive chat.
    """
    if root_dir:
        root = Path(root_dir)
    else:
        root = find_ecosystem_root(Path.cwd())

    if not root or not root.is_dir():
        error("Could not find your workspace root. Use --dir to specify.")
        return

    info(f"Workspace root: {root}")
    info("Loading workspace knowledge...")

    system_prompt = _build_system_prompt(root)
    context_size = len(system_prompt)
    info(f"System context: {context_size:,} chars")

    # Enhance with the indexed codebase, when available.
    rag_available = False
    try:
        from forktex.intelligence import Intelligence

        async with Intelligence() as ai:
            space = await ai.knowledge.find_space(name=ECOSYSTEM_SPACE)
            if space is not None:
                rag_available = True
                entries = await space.list_entries(limit=200)
                info(f"Codebase index ready ({len(entries):,} entries)")

        if not rag_available:
            info("Codebase not yet indexed. Run: forktex intelligence index-ecosystem")
    except Exception:
        info("Intelligence API not available — running with static context only")

    # Build agent tools configuration
    from forktex.agent.types import AGENT_TYPES

    resolved_type = AGENT_TYPES.get(agent_type, AGENT_TYPES["assistant"])
    info(f"Agent type: {resolved_type.name} ({len(resolved_type.allowed_tools)} tools)")

    if task:
        # One-shot mode
        info(f"Task: {task}")

        from forktex.agent.intelligence.agent import LocalAgentLoop
        from forktex.agent.intelligence.tool_server import IntelligenceToolServer

        tool_server = IntelligenceToolServer(str(root))
        tools = tool_server.get_tool_schemas()

        agent = LocalAgentLoop(
            system=system_prompt, tools=tools, tool_server=tool_server
        )
        response = await agent.run(task)

        console.print("\n[bold]Response:[/bold]\n")
        console.print(response.text)

        if response.tool_calls_made:
            console.print(
                f"\n[dim]{response.tool_calls_made} tool calls, "
                f"{response.input_tokens + response.output_tokens} tokens[/dim]"
            )
    else:
        # Interactive mode — delegate to chat with enriched system prompt
        from forktex.agent.intelligence.cli.chat import chat as _chat_fn

        ctx = click.get_current_context()
        # Store system prompt in context for the chat to pick up
        ctx.ensure_object(dict)
        ctx.obj["system_prompt"] = system_prompt
        ctx.obj["project"] = str(root)
        await ctx.invoke(_chat_fn, project=str(root))
