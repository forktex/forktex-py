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

"""``forktex knowledge ingest`` — bulk-import workspace sources into the knowledge base.

**Local-first.** By default this writes the discovered markdown (each
``AGENTS.md`` + curated docs across the workspace) as knowledge **nodes** into
the global doc-space (``~/.forktex/knowledge``) — pure on-disk, no external
service. The global layer composes into every project (docs ← global ← project),
so the ingested workspace knowledge is queryable from anywhere via
``forktex knowledge search``.

``--remote`` (opt-in) *additionally* pushes the same sources to the optional
ForkTex Intelligence vector store (the Layer-4 semantic index, a derived
projection — never the source of truth). Only that path needs Intelligence, and
it checks the connection first and degrades with clear guidance.

Was ``forktex intelligence index-workspace`` before 0.8.0.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from pathlib import Path

import asyncclick as click

from forktex.agent.ui.console import console, error, info
from forktex.core.paths import find_workspace_root

DEFAULT_SPACE = "forktex-workspace"

#: Curated workspace files to ingest, relative to the workspace root.
KNOWLEDGE_FILES: list[tuple[str, str]] = [
    ("docs/AGENTS.md", "workspace-grounding"),
    ("forktex-py/AGENTS.md", "forktex-cli-agent"),
    ("network/AGENTS.md", "network-platform"),
    ("cloud/AGENTS.md", "cloud-platform"),
    ("intelligence/AGENTS.md", "intelligence-platform"),
    ("workflow/AGENTS.md", "workflow-engine"),
    ("contracts/AGENTS.md", "contracts-engine"),
    ("solar/AGENTS.md", "solar-platform"),
    ("corporate/AGENTS.md", "corporate-platform"),
    ("survey/AGENTS.md", "survey-platform"),
    ("docs/ecosystem.md", "workspace-overview"),
    ("docs/overview.md", "factory-overview"),
    ("docs/engineering/libraries.json", "library-graph"),
    ("docs/compliance/fsd/README.md", "fsd-standard"),
]


def _discover_agents_md(root: Path) -> list[tuple[str, str]]:
    """Find every ``AGENTS.md`` one level under the workspace root."""
    files: list[tuple[str, str]] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        agents_md = d / "AGENTS.md"
        if agents_md.exists():
            files.append((str(agents_md.relative_to(root)), f"{d.name}-agents"))
    return files


def _collect_files(root: Path) -> list[tuple[str, str]]:
    """The deduped list of (relpath, label) to ingest from *root*."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for rel, label in _discover_agents_md(root) + KNOWLEDGE_FILES:
        if rel not in seen and (root / rel).exists():
            seen.add(rel)
            out.append((rel, label))
    arch_dir = root / ".forktex" / "cache" / "architecture"
    arch_files = sorted(arch_dir.glob("arch-*.json")) if arch_dir.is_dir() else []
    if arch_files:
        out.append((str(arch_files[-1].relative_to(root)), "latest-architecture"))
    return out


def _node_id(rel: str) -> str:
    """Stable knowledge-node id for a source relpath (idempotent re-ingest)."""
    slug = re.sub(r"[^a-z0-9]+", "-", rel.lower()).strip("-")
    return f"reference.{slug}"


def _ingest_local(files: list[tuple[str, str]], root: Path, target) -> int:
    """Write each source file as a ``reference`` node into ``target`` doc-space."""
    from forktex.agent.knowledge.recycle import recycle

    written = 0
    for rel, label in files:
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            console.print(f"  [yellow]skip[/yellow] {rel} (unreadable)")
            continue
        recycle(
            target,
            id=_node_id(rel),
            title=rel,
            body_md=text,
            kind="reference",
            summary=f"Workspace source: {rel} ({label})",
            tags=[label, "workspace", "ingest"],
            source_ids=[rel],
            source_root=str(root),
            source_hashes={rel: _source_hash(text)},
            agent="forktex.agent.knowledge.ingest",
        )
        written += 1
    return written


def _source_hash(text: str) -> str:
    """Content hash of an ingested source — lets ``doctor`` detect post-ingest drift."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _push_remote(files: list[tuple[str, str]], root: Path, space: str) -> None:
    """Push the same sources to the Intelligence vector store (opt-in projection).

    Checks configuration + reachability first so a missing/unreachable
    Intelligence degrades with clear guidance instead of a post-listing crash.
    """
    from forktex.agent.intelligence.settings import load_intelligence_settings
    from forktex.intelligence import Intelligence

    settings = load_intelligence_settings()
    if not settings.api_key:
        error(
            "--remote needs ForkTex Intelligence — none configured. "
            "Run `forktex auth intelligence`, then retry."
        )
        return

    try:
        async with Intelligence(
            endpoint=settings.endpoint, api_key=settings.api_key
        ) as ai:
            try:
                await asyncio.wait_for(ai.health(), timeout=5.0)
            except Exception:
                error(
                    f"Intelligence not reachable at {settings.endpoint} — is it running? "
                    "(`forktex auth intelligence` to reconfigure)."
                )
                return
            info("Connected to Intelligence API")
            space_obj = await ai.knowledge.find_space(name=space)
            if space_obj is None:
                space_obj = await ai.knowledge.create_space(space, template="text-kb")
                info(f"Created knowledge space: {space} ({space_obj.id})")
            else:
                info(f"Using knowledge space: {space} ({space_obj.id})")

            uploaded = 0
            for rel, label in files:
                try:
                    text = (root / rel).read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                try:
                    await space_obj.upsert(
                        kind="document",
                        external_id=rel,
                        content=text,
                        tags=[label],
                        origin="sync:workspace",
                    )
                    uploaded += 1
                except Exception as exc:  # one bad file shouldn't abort the batch
                    console.print(f"  [red]failed[/red] {rel}: {exc}")
            console.print(
                f"[bold green]Pushed {uploaded}/{len(files)} to remote '{space}'.[/bold green]"
            )
    except Exception as exc:
        error(f"Intelligence remote push failed: {exc}")


@click.command("ingest")
@click.option(
    "--dir", "root_dir", default=None, help="Workspace/source root (default: discover)."
)
@click.option(
    "--project",
    "to_project",
    is_flag=True,
    default=False,
    help="Write nodes into the cwd project doc-space instead of the global ~/.forktex/knowledge.",
)
@click.option(
    "--remote",
    is_flag=True,
    default=False,
    help="Also push to the ForkTex Intelligence vector store (needs `forktex auth intelligence`).",
)
@click.option(
    "--space",
    default=DEFAULT_SPACE,
    help="Remote knowledge space name (with --remote).",
)
@click.option(
    "--dry-run", is_flag=True, help="List what would be ingested; write nothing."
)
async def ingest_cmd(
    root_dir: str | None,
    to_project: bool,
    remote: bool,
    space: str,
    dry_run: bool,
) -> None:
    """Ingest workspace markdown into the local knowledge base (no service needed).

    Default target is the global doc-space (``~/.forktex/knowledge``), queryable
    from any project. ``--remote`` additionally syncs to the Intelligence vector
    store.
    """
    root = Path(root_dir) if root_dir else find_workspace_root(Path.cwd())
    if not root or not root.is_dir():
        error("Could not find a workspace root. Pass --dir.")
        return
    info(f"Workspace root: {root}")

    files = _collect_files(root)
    console.print(f"\n[bold]Files to ingest ({len(files)}):[/bold]")
    for rel, label in files:
        size = (root / rel).stat().st_size
        console.print(f"  [green]OK[/green] {rel:<58} [{label}] ({size:,} b)")

    if dry_run:
        info("Dry run — nothing written.")
        return

    from forktex.agent.knowledge.sources import ensure_doc_space, project_doc_space
    from forktex.substrate import paths as _sub

    if to_project:
        target = ensure_doc_space(project_doc_space(os.getcwd()))
    else:
        target = ensure_doc_space(_sub.global_knowledge_dir())

    written = _ingest_local(files, root, target)
    console.print(
        f"\n[bold green]Ingested {written}/{len(files)} nodes → {target}[/bold green]"
    )
    info("Query them with `forktex knowledge search <term>`.")

    if remote:
        console.print()
        await _push_remote(files, root, space)


__all__ = ["ingest_cmd"]
