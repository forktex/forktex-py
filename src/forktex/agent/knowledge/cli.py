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

"""``forktex knowledge`` — query the live knowledge graph from the CLI."""

from __future__ import annotations

import os
from pathlib import Path

import asyncclick as click

from forktex_core.fractal import FractalQuery, NamespaceNotFound, NodeNotFound

from forktex.agent.lazy_group import AsyncLazyGroup
from forktex.agent.knowledge.doctor import exit_code as doctor_exit_code
from forktex.agent.knowledge.doctor import format_report as doctor_format_report
from forktex.agent.knowledge.doctor import run_doctor
from forktex.agent.knowledge.init import init_doc_space
from forktex.agent.knowledge.recycle import recycle as recycle_node
from forktex.agent.knowledge.retire import retire as retire_node
from forktex.agent.knowledge.rollup import rollup as rollup_subtree
from forktex.agent.knowledge.search import ranked_search
from forktex.agent.knowledge.sources import (
    COMPOSED_NAMESPACE,
    build_knowledge_resolver,
    ensure_doc_space,
    project_doc_space,
    resolve_doc_space,
)


def _default_project() -> str | None:
    """The cwd project doc-space, if it already holds nodes (so it overlays)."""
    space = project_doc_space(os.getcwd())
    return str(space) if (space / "nodes").is_dir() else None


def _parse_sources(sources) -> list[tuple[str, str, str]]:
    """Parse ``--source ADAPTER:PATH`` values into ``(name, path, adapter)`` triples."""
    from pathlib import Path

    from forktex.agent.knowledge.sources import known_adapters

    valid = known_adapters()
    out: list[tuple[str, str, str]] = []
    for raw in sources or ():
        if ":" not in raw:
            raise click.ClickException(f"--source must be ADAPTER:PATH (got {raw!r})")
        adapter, path = raw.split(":", 1)
        if adapter not in valid:
            raise click.ClickException(
                f"unknown adapter {adapter!r} — valid: {sorted(valid)}"
            )
        out.append((f"{adapter}:{Path(path).name or adapter}", path, adapter))
    return out


def _query(docs: str | None, project: str | None, sources=()) -> FractalQuery:
    from forktex.agent.knowledge.config import load_knowledge_config
    from forktex.agent.knowledge.memory import memory_source
    from forktex.core.paths import find_project_root

    extra = _parse_sources(sources)
    mem = memory_source(find_project_root() or os.getcwd())  # recall working memory (5.2)
    if mem:
        extra = [mem, *extra]
    return FractalQuery(
        build_knowledge_resolver(
            docs_path=docs,
            project_path=project or _default_project(),
            config=load_knowledge_config(None),
            extra_sources=extra,
        )
    )


@click.group("knowledge", cls=AsyncLazyGroup)
async def knowledge() -> None:
    """Query the live knowledge graph (docs principles + project knowledge)."""


# Nested ``forktex knowledge mcp`` — the MCP stdio server is knowledge-specific
# (exposes ``knowledge_*`` tools); the lazy registration keeps the heavy
# ``mcp.server`` import out of every ``forktex knowledge`` invocation.
knowledge.add_lazy_command(
    "mcp",
    "forktex.agent.knowledge.mcp_server:mcp_cmd",
    short_help="Run an MCP server (stdio) exposing fractal knowledge tools.",
    optional=True,
    install_hint="pip install 'forktex-py[mcp]'",
)
knowledge.add_lazy_command(
    "ingest",
    "forktex.agent.knowledge.ingest:ingest_cmd",
    short_help="Bulk-import a source (workspace AGENTS.md → remote vector store).",
    optional=True,
    install_hint="pip install forktex-intelligence",
)


@knowledge.command("search")
@click.argument("query")
@click.option("--kind", default=None, help="Filter by node kind (e.g. docs.standard).")
@click.option("--limit", default=10, show_default=True, help="Max results.")
@click.option(
    "--docs", default=None, help="Global docs repo path (else $FORKTEX_DOCS)."
)
@click.option("--project", "-d", default=None, help="Project doc-space to overlay.")
@click.option(
    "--source",
    multiple=True,
    help="Ad-hoc layer ADAPTER:PATH (e.g. code_index:../repo, generic_markdown:./notes); repeatable.",
)
@click.option("--namespace", "-n", default=COMPOSED_NAMESPACE, show_default=True)
async def ask_cmd(query, kind, limit, docs, project, source, namespace) -> None:
    """Search the knowledge graph for nodes matching QUERY (tokenised + ranked)."""
    try:
        nodes = ranked_search(
            _query(docs, project, source), namespace, query, kind=kind, limit=limit
        )
    except (NamespaceNotFound, KeyError):
        # Run-anywhere: no knowledge sources here is not an error.
        click.echo(
            "no knowledge sources — run `forktex knowledge init` or set $FORKTEX_DOCS"
        )
        return
    if not nodes:
        click.echo("no matches")
        return
    click.echo(f"{len(nodes)} match(es) in '{namespace}':\n")
    for node in nodes:
        tags = f"  ({', '.join(node.tags)})" if node.tags else ""
        click.echo(f"  • {node.id}  [{node.kind}]  {node.title}{tags}")


@knowledge.command("show")
@click.argument("node_id")
@click.option("--docs", default=None)
@click.option("--project", "-d", default=None)
@click.option("--source", multiple=True, help="Ad-hoc layer ADAPTER:PATH; repeatable.")
@click.option("--namespace", "-n", default=COMPOSED_NAMESPACE, show_default=True)
async def show_cmd(node_id, docs, project, source, namespace) -> None:
    """Print a knowledge node in full (frontmatter + body)."""
    try:
        node = _query(docs, project, source).get_node(namespace, node_id).node
    except (NamespaceNotFound, NodeNotFound) as exc:
        raise click.ClickException(str(exc))
    click.echo(f"# {node.title}\n")
    click.echo(f"id:      {node.id}")
    click.echo(f"kind:    {node.kind}")
    click.echo(f"status:  {node.status}")
    if node.tags:
        click.echo(f"tags:    {', '.join(node.tags)}")
    if node.edges:
        click.echo(f"edges:   {dict(node.edges)}")
    click.echo("\n" + (node.body_md or "(no body)"))


@knowledge.command("neighbors")
@click.argument("node_id")
@click.option("--docs", default=None)
@click.option("--project", "-d", default=None)
@click.option("--source", multiple=True, help="Ad-hoc layer ADAPTER:PATH; repeatable.")
@click.option("--namespace", "-n", default=COMPOSED_NAMESPACE, show_default=True)
async def neighbors_cmd(node_id, docs, project, source, namespace) -> None:
    """Show a node's typed adjacency — outgoing + incoming edges by kind.

    ``parent`` incoming is the derived children; other kinds (``reference``, …)
    are arbitrary cross-links.
    """
    try:
        res = _query(docs, project, source).neighbors(namespace, node_id)
    except (NamespaceNotFound, NodeNotFound) as exc:
        raise click.ClickException(str(exc))

    def _render(label: str, by_kind: dict) -> None:
        if not any(by_kind.values()):
            return
        click.echo(f"{label}:")
        for kind, summaries in sorted(by_kind.items()):
            for s in summaries:
                click.echo(f"  [{kind}] {s.id}  [{s.kind}]  {s.title}")

    _render("outgoing", res.outgoing)
    _render("incoming", res.incoming)
    if not any(res.outgoing.values()) and not any(res.incoming.values()):
        click.echo(f"no neighbors for {node_id!r}")


@knowledge.command("recycle")
@click.argument("node_id")
@click.option("--title", required=True, help="Short human title.")
@click.option("--summary", default=None, help="One-line précis (embedded + injected).")
@click.option("--body", default="", help="Optional extra markdown detail.")
@click.option("--kind", default="lesson", show_default=True, help="Node kind.")
@click.option("--why", default=None, help="Why this matters (rationale).")
@click.option("--how", "how_to_apply", default=None, help="The actionable rule.")
@click.option("--ref", "references", multiple=True, help="Referenced node id (repeatable).")
@click.option("--tag", "tags", multiple=True, help="Tag (repeatable); 'pinned' = always-inject.")
@click.option(
    "--replace-tags",
    is_flag=True,
    default=False,
    help="Replace the existing node's tags with --tag (default: union — accretive).",
)
@click.option(
    "--replace-refs",
    is_flag=True,
    default=False,
    help="Replace the existing node's references with --ref (default: union).",
)
@click.option(
    "--project", "-d", default=None,
    help="Project doc-space or repo root (else ./.forktex/knowledge)."
)
@click.option(
    "--global",
    "to_global",
    is_flag=True,
    default=False,
    help="Recycle into the host-wide layer (~/.forktex/knowledge) — cross-project "
    "lessons + workspace constraints, queryable from any forktex project.",
)
async def recycle_cmd(
    node_id,
    title,
    summary,
    body,
    kind,
    why,
    how_to_apply,
    references,
    tags,
    replace_tags,
    replace_refs,
    project,
    to_global,
) -> None:
    """Capture a learning back into the project doc-space (dedup by NODE_ID).

    By default, ``--tag`` and ``--ref`` *union* with the existing node — the
    accretive refinement that's right for "I learned something new about this."
    Pass ``--replace-tags`` / ``--replace-refs`` for the demotion path (drop a
    tag, swap references). See also ``forktex knowledge retire`` to mark a
    node superseded without rewriting its content.
    """
    if to_global:
        from forktex.substrate import paths as _sub

        default_space = _sub.global_knowledge_dir()
    else:
        default_space = project_doc_space(os.getcwd())
    target = ensure_doc_space(resolve_doc_space(project) if project else default_space)
    node = recycle_node(
        target,
        id=node_id,
        title=title,
        summary=summary,
        body_md=body,
        kind=kind,
        why=why,
        how_to_apply=how_to_apply,
        references=list(references),
        tags=list(tags),
        replace_tags=replace_tags,
        replace_refs=replace_refs,
        agent="cli",
    )
    click.echo(f"recycled {node.id} → {target}/nodes/{node.id}.md  (updated {node.updated_at})")


@knowledge.command("retire")
@click.argument("node_id")
@click.option("--reason", default=None, help="Why this node is retired (recorded on the patch).")
@click.option(
    "--project", "-d", default=None,
    help="Project doc-space or repo root (else ./.forktex/knowledge)."
)
async def retire_cmd(node_id, reason, project) -> None:
    """Mark NODE_ID retired — filtered from grounding + ranked_search by default.

    The node stays on disk and remains resolvable by ``forktex knowledge show``
    (an audit trail). The grounding tier + ranked_search filter
    ``status="retired"`` from default queries, so the agent no longer sees it
    unless asked by id. Pair with ``--replace-tags`` on a fresh ``recycle`` to
    fully replace a superseded lesson.
    """
    target = resolve_doc_space(project) if project else project_doc_space(os.getcwd())
    try:
        node = retire_node(target, node_id, reason=reason, agent="cli")
    except KeyError as exc:
        raise click.ClickException(str(exc))
    click.echo(f"retired {node.id}  (status={node.status}, updated {node.updated_at})")


@knowledge.command("rollup")
@click.argument("parent_id")
@click.option("--summary", default=None, help="Compact summary; auto-composed if omitted.")
@click.option("--child", "child_ids", multiple=True, help="Explicit child id (repeatable).")
@click.option(
    "--project", "-d", default=None,
    help="Project doc-space or repo root (else ./.forktex/knowledge)."
)
async def rollup_cmd(parent_id, summary, child_ids, project) -> None:
    """Compact PARENT_ID's subtree into its summary and demote the children."""
    target = ensure_doc_space(
        resolve_doc_space(project) if project else project_doc_space(os.getcwd())
    )
    try:
        parent = rollup_subtree(
            target,
            parent_id,
            summary=summary,
            child_ids=list(child_ids) or None,
            agent="cli",
        )
    except (KeyError, ValueError) as exc:
        raise click.ClickException(str(exc))
    click.echo(f"rolled up {parent.id}  (updated {parent.updated_at})")
    click.echo(f"  summary: {parent.summary}")


@knowledge.command("list")
@click.option("--kind", default=None, help="Filter by node kind.")
@click.option("--docs", default=None)
@click.option("--project", "-d", default=None)
@click.option("--source", multiple=True, help="Ad-hoc layer ADAPTER:PATH; repeatable.")
@click.option("--namespace", "-n", default=COMPOSED_NAMESPACE, show_default=True)
async def list_cmd(kind, docs, project, source, namespace) -> None:
    """List node summaries in the knowledge graph."""
    try:
        result = _query(docs, project, source).list_nodes(namespace, kind=kind)
    except NamespaceNotFound as exc:
        raise click.ClickException(str(exc))
    click.echo(f"{result.count} node(s) in '{namespace}':\n")
    for node in result.nodes:
        click.echo(f"  • {node.id}  [{node.kind}]  {node.title}")


@knowledge.command("init")
@click.option(
    "--no-readme", is_flag=True, default=False, help="Skip writing the .forktex/knowledge/README.md."
)
@click.option(
    "--no-manifest",
    is_flag=True,
    default=False,
    help="Skip appending the [knowledge] block to forktex.json (if present).",
)
async def init_cmd(no_readme, no_manifest) -> None:
    """Bootstrap the project doc-space (.forktex/knowledge/) in the current dir.

    Idempotent — running it again on an existing doc-space prints what's already
    in place without overwriting anything. After running, you can recycle /
    retire / ask / rollup / doctor in this project, and any forktex-grounded
    agent (Claude via `forktex mcp`, the intelligence agent, …) composes the
    global docs corpus with this project's local knowledge.
    """
    result = init_doc_space(
        os.getcwd(),
        with_readme=not no_readme,
        with_manifest_block=not no_manifest,
    )
    space = result.doc_space
    if result.created_dirs:
        click.echo(f"created  {space}/nodes/  +  {space}/patches/")
    else:
        click.echo(f"exists   {space}/")
    if result.created_readme:
        click.echo(f"wrote    {space}/README.md")
    if result.added_manifest_block:
        click.echo("seeded   forktex.json [knowledge] (explicit defaults)")
    click.echo("")
    click.echo("Next:")
    click.echo('  forktex knowledge search "<topic>"   # query the composed view')
    click.echo("  forktex knowledge recycle <id> --title ... --summary ... --tag pinned")
    click.echo("  forktex knowledge doctor             # check for drift")
    click.echo(
        "  claude mcp add forktex -- forktex knowledge mcp   # let agents use it too"
    )


@knowledge.command("doctor")
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Exit non-zero on warnings too (default: only on errors).",
)
@click.option(
    "--project",
    "-d",
    default=None,
    help="Project root to check (default: cwd).",
)
@click.option(
    "--composed",
    is_flag=True,
    default=False,
    help="Resolve refs against the composed view (docs ← global ← project) so "
    "cross-layer references aren't flagged as dangling.",
)
async def doctor_cmd(strict, project, composed) -> None:
    """Drift report — surface broken refs, cycles, retired-but-referenced, etc.

    Six checks in v1: filename↔id match, dangling references, parent cycles,
    patch output_ids resolve, retired nodes with inbound refs, KnowledgeConfig
    validates. With ``--composed``, a reference resolving in another layer (a
    project lesson citing a docs standard) is treated as a legitimate cross-layer
    link, not a dangling warning. Exits 0 on a clean run; exits 1 on an error (or
    any warning with --strict). Run this in CI to gate doc-space hygiene.
    """
    root = Path(project) if project else Path(os.getcwd())
    issues = run_doctor(root, composed=composed)
    click.echo(doctor_format_report(issues, project_root=root))
    code = doctor_exit_code(issues, strict=strict)
    if code != 0:
        raise click.exceptions.Exit(code)


__all__ = ["knowledge"]
