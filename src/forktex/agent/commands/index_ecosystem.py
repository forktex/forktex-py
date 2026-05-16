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

"""forktex intelligence index-ecosystem — Index ecosystem knowledge for RAG.

Indexes AGENTS.md files, ecosystem.json, architecture data, and library
definitions into a knowledge Space for semantic search by agents.

This creates the "ecosystem brain" — agents can query it to understand
the full FORKTEX factory before taking action.

Usage:
    forktex intelligence index-ecosystem
    forktex intelligence index-ecosystem --space forktex-ecosystem
    forktex intelligence index-ecosystem --dir ~/Desktop/forktex
"""

from __future__ import annotations

from pathlib import Path

import asyncclick as click

from forktex.agent.ui.console import console, info, error
from forktex.core.paths import find_ecosystem_root


COLLECTION_NAME = "forktex-ecosystem"

# Files to index, relative to ecosystem root
KNOWLEDGE_FILES = [
    # AGENTS.md files (ground knowledge)
    ("docs/AGENTS.md", "ecosystem-grounding"),
    ("forktex-py/AGENTS.md", "forktex-cli-agent"),
    ("network/AGENTS.md", "network-platform"),
    ("cloud/AGENTS.md", "cloud-platform"),
    ("intelligence/AGENTS.md", "intelligence-platform"),
    ("workflow/AGENTS.md", "workflow-engine"),
    ("contracts/AGENTS.md", "contracts-engine"),
    ("solar/AGENTS.md", "solar-platform"),
    ("corporate/AGENTS.md", "corporate-platform"),
    ("survey/AGENTS.md", "survey-platform"),
    # Ecosystem data
    ("docs/ecosystem.md", "ecosystem-overview"),
    ("docs/overview.md", "factory-overview"),
    ("docs/engineering/libraries.json", "library-graph"),
    # FSD standard
    ("docs/compliance/fsd/README.md", "fsd-standard"),
]


def _discover_agents_md(root: Path) -> list[tuple[str, str]]:
    """Find all AGENTS.md files under the ecosystem root."""
    files = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        agents_md = d / "AGENTS.md"
        if agents_md.exists():
            rel = str(agents_md.relative_to(root))
            files.append((rel, f"{d.name}-agents"))
    return files


@click.command(name="index-ecosystem")
@click.option("--dir", "-d", "root_dir", default=None, help="Ecosystem root directory")
@click.option(
    "--space", "-c", "space_name", default=COLLECTION_NAME, help="Knowledge space name"
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be indexed without uploading"
)
async def index_ecosystem(root_dir: str | None, space_name: str, dry_run: bool):
    """Index ecosystem knowledge into Intelligence API for RAG queries.

    Creates a vector collection containing all AGENTS.md files, ecosystem
    metadata, and architecture data. Agents can then search this collection
    to understand the full FORKTEX factory.
    """
    if root_dir:
        root = Path(root_dir)
    else:
        root = find_ecosystem_root(Path.cwd())

    if not root or not root.is_dir():
        error("Could not find ecosystem root. Use --dir to specify.")
        return

    info(f"Ecosystem root: {root}")

    # Discover all indexable files (dedup by path)
    seen_paths: set[str] = set()
    all_files: list[tuple[str, str]] = []

    for rel_path, label in _discover_agents_md(root):
        if rel_path not in seen_paths:
            seen_paths.add(rel_path)
            all_files.append((rel_path, label))

    for rel_path, label in KNOWLEDGE_FILES:
        full = root / rel_path
        if full.exists() and rel_path not in seen_paths:
            seen_paths.add(rel_path)
            all_files.append((rel_path, label))

    # Also discover architecture JSON
    arch_dir = root / ".forktex" / "architecture"
    if arch_dir.exists():
        arch_files = sorted(arch_dir.glob("arch-*.json"))
        if arch_files:
            latest = arch_files[-1]
            all_files.append((str(latest.relative_to(root)), "latest-architecture"))

    console.print(f"\n[bold]Files to index ({len(all_files)}):[/bold]\n")
    for rel_path, label in all_files:
        full = root / rel_path
        exists = full.exists()
        status_icon = "[green]OK[/green]" if exists else "[red]MISSING[/red]"
        size = full.stat().st_size if exists else 0
        console.print(f"  {status_icon} {rel_path:<60} [{label}] ({size:,} bytes)")

    existing = [(p, label) for p, label in all_files if (root / p).exists()]
    console.print(f"\n  [bold]{len(existing)}/{len(all_files)}[/bold] files found")

    if dry_run:
        info("Dry run — no files uploaded.")
        return

    # Connect to Intelligence API
    from forktex.intelligence import Intelligence

    try:
        async with Intelligence() as ai:
            info("Connected to Intelligence API")

            # Find or create the knowledge space
            space = await ai.knowledge.find_space(name=space_name)
            if space is None:
                space = await ai.knowledge.create_space(space_name, template="text-kb")
                info(f"Created knowledge space: {space_name} ({space.id})")
            else:
                info(f"Using existing knowledge space: {space_name} ({space.id})")

            # Idempotent upload: each file's relative path is the external_id,
            # so re-running the command updates entries in place rather than
            # creating duplicates.
            uploaded = 0
            for rel_path, label in existing:
                full = root / rel_path
                content_bytes = full.read_bytes()
                filename = f"{label}--{Path(rel_path).name}"

                try:
                    text = content_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    console.print(f"  [yellow]Skip[/yellow] {filename}: binary file")
                    continue

                try:
                    await space.upsert(
                        kind="document",
                        external_id=rel_path,
                        content=text,
                        tags=[label],
                        origin="sync:ecosystem",
                    )
                    uploaded += 1
                    console.print(f"  [green]Upserted[/green] {filename}")
                except Exception as e:
                    console.print(f"  [red]Failed[/red] {filename}: {e}")

            console.print(
                f"\n[bold green]Indexed {uploaded}/{len(existing)} files into '{space_name}'[/bold green]"
            )
            console.print("\nAgents can now search this knowledge:")
            console.print(
                "  [cyan]forktex ask 'What database does the network platform use?'[/cyan]"
            )
            console.print("  [cyan]forktex ask 'How are workflows structured?'[/cyan]")

    except Exception as e:
        error(f"Intelligence API error: {e}")
        error("Make sure the Intelligence API is running: forktex intelligence status")
