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

"""The forktex ``Tool`` catalog over ``forktex_core.fractal.FractalQuery``.

This is where the agent-tool surface lives — the slim ``forktex_core`` substrate
exposes only the generic query core; forktex-py wraps it as tools (and, via
``mcp_server``, as an MCP surface) so the intelligence agent / Claude Code / Codex
can query live knowledge mid-task.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from forktex_core.fractal import FractalQuery, NamespaceNotFound, NodeNotFound

from forktex.agent.knowledge.recycle import recycle as _recycle_node
from forktex.agent.knowledge.retire import retire as _retire_node
from forktex.agent.knowledge.rollup import rollup as _rollup_subtree
from forktex.agent.knowledge.search import ranked_search
from forktex.agent.knowledge.sources import (
    ensure_doc_space,
    resolve_doc_space,
)
from forktex.agent.tools.base import Tool, ToolResult

DEFAULT_NAMESPACE = "knowledge"

#: Env var a host (Claude Code, Codex) can export per workspace so write tools
#: target the repo actually in use rather than the server's startup directory.
DOC_SPACE_ENV = "FORKTEX_DOC_SPACE"

_NAMESPACE_PARAM = {
    "type": "string",
    "description": "Knowledge namespace; defaults to the composed 'knowledge' view.",
}

_DOC_SPACE_PARAM = {
    "type": "string",
    "description": (
        "Target project to write to — a repo root or a .forktex/knowledge dir. "
        "A long-lived MCP server is bound to one repo at startup; pass this (or "
        f"export {DOC_SPACE_ENV}) so a write lands in the repo you're actually in, "
        "not the server's home. Defaults to that startup doc-space."
    ),
}


def build_knowledge_tools(
    query: FractalQuery,
    *,
    default_namespace: str = DEFAULT_NAMESPACE,
    recycle_dir: str | Path | None = None,
) -> list[Tool]:
    """Bind a ``FractalQuery`` into the forktex knowledge tool catalog.

    Read tools (search/show/neighbors/list) are always present. When
    ``recycle_dir`` is given (a project doc-space), the write-back tool
    ``knowledge_recycle`` is added — the agent can capture a learning into the
    shared project memory, where the next query/grounding surfaces it.
    """

    def _ns(kwargs: dict[str, Any]) -> str:
        return kwargs.get("namespace") or default_namespace

    def _ok(payload: Any) -> ToolResult:
        return ToolResult(content=json.dumps(payload, ensure_ascii=False))

    def _write_target(kw: dict[str, Any]) -> Path | None:
        """Resolve the write doc-space at call time, not server-start time.

        Precedence: explicit ``doc_space`` arg → ``$FORKTEX_DOC_SPACE`` →
        the server's startup ``recycle_dir`` fallback. Returns ``None`` only when
        no target is available at all (write tools then report not-enabled).
        """
        raw = kw.get("doc_space") or os.environ.get(DOC_SPACE_ENV)
        if raw:
            return ensure_doc_space(resolve_doc_space(raw))
        if recycle_dir is not None:
            return Path(recycle_dir)
        return None

    async def _search(**kw: Any) -> ToolResult:
        namespace = _ns(kw)
        try:
            nodes = ranked_search(
                query,
                namespace,
                kw["q"],
                kind=kw.get("kind"),
                limit=int(kw.get("limit", 10)),
            )
        except NamespaceNotFound as exc:
            return ToolResult(content=str(exc), is_error=True)
        return _ok(
            {
                "namespace": namespace,
                "count": len(nodes),
                "nodes": [n.model_dump(mode="json") for n in nodes],
            }
        )

    async def _show(**kw: Any) -> ToolResult:
        try:
            res = query.get_node(_ns(kw), kw["id"])
        except (NamespaceNotFound, NodeNotFound) as exc:
            return ToolResult(content=str(exc), is_error=True)
        return _ok(res.model_dump(mode="json"))

    async def _neighbors(**kw: Any) -> ToolResult:
        try:
            res = query.neighbors(_ns(kw), kw["id"])
        except (NamespaceNotFound, NodeNotFound) as exc:
            return ToolResult(content=str(exc), is_error=True)
        return _ok(res.model_dump(mode="json"))

    async def _list(**kw: Any) -> ToolResult:
        try:
            res = query.list_nodes(
                _ns(kw), kind=kw.get("kind"), status=kw.get("status")
            )
        except NamespaceNotFound as exc:
            return ToolResult(content=str(exc), is_error=True)
        return _ok(res.model_dump(mode="json"))

    async def _recycle(**kw: Any) -> ToolResult:
        target = _write_target(kw)
        if target is None:  # defensive — tool only registered when a default exists
            return ToolResult(
                content="recycling not enabled (no doc-space)", is_error=True
            )
        node = _recycle_node(
            target,
            id=kw["id"],
            title=kw["title"],
            body_md=kw.get("body", ""),
            kind=kw.get("kind", "lesson"),
            summary=kw.get("summary"),
            references=kw.get("references") or [],
            source_ids=kw.get("source_ids") or [],
            why=kw.get("why"),
            how_to_apply=kw.get("how_to_apply"),
            tags=kw.get("tags") or [],
            replace_tags=bool(kw.get("replace_tags", False)),
            replace_refs=bool(kw.get("replace_refs", False)),
            agent=kw.get("agent") or "knowledge_recycle",
        )
        return _ok(
            {
                "recycled": node.id,
                "kind": node.kind,
                "updated_at": node.updated_at,
                "doc_space": str(target),
            }
        )

    async def _retire(**kw: Any) -> ToolResult:
        target = _write_target(kw)
        if target is None:
            return ToolResult(
                content="retire not enabled (no doc-space)", is_error=True
            )
        try:
            node = _retire_node(
                target,
                kw["id"],
                reason=kw.get("reason"),
                agent=kw.get("agent") or "knowledge_retire",
            )
        except KeyError as exc:
            return ToolResult(content=str(exc), is_error=True)
        return _ok(
            {
                "retired": node.id,
                "status": node.status,
                "updated_at": node.updated_at,
                "doc_space": str(target),
            }
        )

    async def _rollup(**kw: Any) -> ToolResult:
        target = _write_target(kw)
        if target is None:
            return ToolResult(
                content="rollup not enabled (no doc-space)", is_error=True
            )
        try:
            parent = _rollup_subtree(
                target,
                kw["parent_id"],
                summary=kw.get("summary"),
                child_ids=kw.get("child_ids"),
                agent=kw.get("agent") or "knowledge_rollup",
            )
        except (KeyError, ValueError) as exc:
            return ToolResult(content=str(exc), is_error=True)
        return _ok(
            {
                "rolled_up": parent.id,
                "summary": parent.summary,
                "updated_at": parent.updated_at,
                "doc_space": str(target),
            }
        )

    tools = [
        Tool(
            name="knowledge_search",
            description=(
                "Search the knowledge graph (docs principles + project knowledge) by "
                "free text over titles / ids / tags / body. Use this to find the "
                "standard, archetype, or note relevant to the work at hand."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Query text."},
                    "kind": {
                        "type": "string",
                        "description": "Optional kind filter (e.g. 'docs.standard').",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 10,
                    },
                    "namespace": _NAMESPACE_PARAM,
                },
                "required": ["q"],
                "additionalProperties": False,
            },
            handler=_search,
        ),
        Tool(
            name="knowledge_show",
            description="Fetch one knowledge node in full (incl. its markdown body) by id.",
            parameters={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Node id (e.g. 'standard.quality-pipeline').",
                    },
                    "namespace": _NAMESPACE_PARAM,
                },
                "required": ["id"],
                "additionalProperties": False,
            },
            handler=_show,
        ),
        Tool(
            name="knowledge_neighbors",
            description=(
                "Return a node's edges grouped by kind (outgoing + incoming). "
                "'parent' incoming = children; other kinds are arbitrary typed links."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Node id."},
                    "namespace": _NAMESPACE_PARAM,
                },
                "required": ["id"],
                "additionalProperties": False,
            },
            handler=_neighbors,
        ),
        Tool(
            name="knowledge_list",
            description="List node summaries in the knowledge graph, optionally filtered by kind/status.",
            parameters={
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "description": "Optional kind filter."},
                    "status": {
                        "type": "string",
                        "description": "Optional status filter.",
                    },
                    "namespace": _NAMESPACE_PARAM,
                },
                "additionalProperties": False,
            },
            handler=_list,
        ),
    ]

    if recycle_dir is not None:
        tools.append(
            Tool(
                name="knowledge_recycle",
                description=(
                    "Capture a learning back into the shared project memory so future "
                    "sessions (you, Claude Code, Codex, the user) start informed by it — "
                    "anti-amnesia. Use it when you reach a non-obvious decision, "
                    "convention, or correction worth keeping. Provide a stable 'id' "
                    "(re-using one refines that note rather than duplicating), and fill "
                    "'why' (the rationale) + 'how_to_apply' (the actionable rule). Tag "
                    "'pinned' for a must-always-follow standard."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Stable node id (dedup key), e.g. 'lesson.testcontainers-not-mocks'.",
                        },
                        "title": {
                            "type": "string",
                            "description": "Short human title.",
                        },
                        "summary": {
                            "type": "string",
                            "description": "One-line précis — the text that gets embedded + injected.",
                        },
                        "why": {
                            "type": "string",
                            "description": "Why this matters (rationale).",
                        },
                        "how_to_apply": {
                            "type": "string",
                            "description": "The actionable rule — what to do next time.",
                        },
                        "body": {
                            "type": "string",
                            "description": "Optional extra markdown detail.",
                        },
                        "kind": {
                            "type": "string",
                            "default": "lesson",
                            "description": "Node kind (default 'lesson').",
                        },
                        "references": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Related node ids to link (reference edges).",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tags; 'pinned' = always-inject into grounding.",
                        },
                        "replace_tags": {
                            "type": "boolean",
                            "default": False,
                            "description": "Replace existing tags instead of unioning (default: union — accretive).",
                        },
                        "replace_refs": {
                            "type": "boolean",
                            "default": False,
                            "description": "Replace existing references instead of unioning.",
                        },
                        "doc_space": _DOC_SPACE_PARAM,
                    },
                    "required": ["id", "title"],
                    "additionalProperties": False,
                },
                handler=_recycle,
            )
        )
        tools.append(
            Tool(
                name="knowledge_retire",
                description=(
                    "Mark a knowledge node as retired (superseded) — the demotion "
                    "path 'recycle' lacks. The node stays on disk and remains "
                    "resolvable by 'knowledge_show' (an audit trail), but is "
                    "filtered from grounding and default ranked search. Use it "
                    "when a previously-recycled lesson is no longer correct or "
                    "when an over-pinned standard should stop dominating context."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Node id to retire."},
                        "reason": {
                            "type": "string",
                            "description": "Why this node is retired (recorded on the patch).",
                        },
                        "doc_space": _DOC_SPACE_PARAM,
                    },
                    "required": ["id"],
                    "additionalProperties": False,
                },
                handler=_retire,
            )
        )
        tools.append(
            Tool(
                name="knowledge_rollup",
                description=(
                    "Compact a resolved subtree into its parent's summary, demoting "
                    "the children to status='rolled-up'. The fractal-of-fractals analogue "
                    "of context compaction — use this at session-end housekeeping or when "
                    "a parent has accumulated enough resolved children that the detail "
                    "should fold upward into a compact summary. Children are derived from "
                    "the typed graph (nodes with edges.parent ⊇ parent_id); pass "
                    "'child_ids' to scope explicitly."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "parent_id": {
                            "type": "string",
                            "description": "Node id whose subtree to compact.",
                        },
                        "summary": {
                            "type": "string",
                            "description": "Optional compact summary; auto-composed from children if omitted.",
                        },
                        "child_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Explicit children to roll up (default: derived from graph).",
                        },
                        "doc_space": _DOC_SPACE_PARAM,
                    },
                    "required": ["parent_id"],
                    "additionalProperties": False,
                },
                handler=_rollup,
            )
        )

    return tools


__all__ = ["DEFAULT_NAMESPACE", "build_knowledge_tools"]
