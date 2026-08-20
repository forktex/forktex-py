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

"""The central forktex tool catalog — one builder per tool group.

The tool *definitions* already live one-per-module (``filesystem``, ``bash``,
``git``, ``graph``, ``web``, ``desktop``, plus ``knowledge`` and ``fsd``). What
was scattered was the *composition* — three callers each wired the builders by
hand: the full agent ToolServer, the intelligence ToolServer, and the generic
HTTP/MCP API. This module is the single place that knows **how to build each
group** (including the per-group setup, like the knowledge resolver), so every
caller composes from one source instead of re-importing builders ad hoc.

- ``build_group(name, project_root, **opts)`` — build one group's tools.
- ``compose(project_root, groups, …)`` — register several groups into a
  :class:`ToolRegistry` (the flat surface the agent loop drives).

Groups in :data:`OPTIONAL_GROUPS` degrade to ``[]`` when their optional dep is
missing (Playwright for ``web``, ``forktex-core[fractal]`` for ``knowledge``) —
they never break tool-server construction. Required groups propagate errors.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable

from forktex.agent.tools.base import Tool, ToolRegistry

#: Groups that gracefully degrade to ``[]`` if their optional dependency or
#: source isn't available, rather than raising during composition.
OPTIONAL_GROUPS: frozenset[str] = frozenset({"web", "knowledge", "desktop"})


def _filesystem(root: str, **_: Any) -> list[Tool]:
    from forktex.agent.tools.filesystem import create_filesystem_tools

    return create_filesystem_tools(root)


def _bash(root: str, **_: Any) -> list[Tool]:
    from forktex.agent.tools.bash import create_bash_tools

    return create_bash_tools(root)


def _git(root: str, **_: Any) -> list[Tool]:
    from forktex.agent.tools.git import create_git_tools

    return create_git_tools(root)


def _graph(root: str, **_: Any) -> list[Tool]:
    from forktex.agent.tools.graph_tools import create_graph_tools

    return create_graph_tools(root)


def _desktop(root: str, **_: Any) -> list[Tool]:
    from forktex.agent.tools.desktop import create_desktop_tools

    return create_desktop_tools(root)


def _web(_root: str, **_: Any) -> list[Tool]:
    from forktex.agent.tools.web import create_web_tools

    return create_web_tools()


def _fsd(root: str, **_: Any) -> list[Tool]:
    from forktex.agent.fsd.tools import create_fsd_tools

    return create_fsd_tools(root)


def _memory(root: str, **_: Any) -> list[Tool]:
    from forktex.agent.knowledge.memory import create_memory_tools

    return create_memory_tools(root)


def _knowledge(root: str, *, read_only: bool = False, **_: Any) -> list[Tool]:
    from forktex_core.fractal import FractalQuery

    from forktex.agent.knowledge.config import load_knowledge_config
    from forktex.agent.knowledge.memory import memory_source
    from forktex.agent.knowledge.sources import (
        build_knowledge_resolver,
        ensure_doc_space,
        project_doc_space,
    )
    from forktex.agent.knowledge.tools import build_knowledge_tools

    # Guarantee the project doc-space exists so it overlays and freshly recycled
    # nodes are queryable in-session (the compounding loop). Read-only callers
    # (a shared HTTP surface) skip the write tools.
    recycle_dir = None if read_only else ensure_doc_space(project_doc_space(root))
    # Working memory (5.2) composes as the top recall layer when notes exist, so
    # the agent recalls what it noted earlier this session.
    mem = memory_source(root)
    resolver = build_knowledge_resolver(
        project_path=str(recycle_dir) if recycle_dir else str(project_doc_space(root)),
        config=load_knowledge_config(root),
        extra_sources=[mem] if mem else None,
    )
    return build_knowledge_tools(FractalQuery(resolver), recycle_dir=recycle_dir)


#: The one registry of tool-group builders. ``(project_root, **opts) -> [Tool]``.
GROUP_BUILDERS: dict[str, Callable[..., list[Tool]]] = {
    "filesystem": _filesystem,
    "bash": _bash,
    "git": _git,
    "graph": _graph,
    "desktop": _desktop,
    "web": _web,
    "knowledge": _knowledge,
    "memory": _memory,
    "fsd": _fsd,
}


def build_group(name: str, project_root: str | Path, **opts: Any) -> list[Tool]:
    """Build one tool group. Optional groups degrade to ``[]`` on failure."""
    builder = GROUP_BUILDERS.get(name)
    if builder is None:
        raise KeyError(f"unknown tool group: {name!r} (have {sorted(GROUP_BUILDERS)})")
    try:
        return builder(str(project_root), **opts)
    except Exception:
        if name in OPTIONAL_GROUPS:
            return []
        raise


def compose(
    project_root: str | Path,
    groups: Iterable[str],
    *,
    into: ToolRegistry | None = None,
    **opts: Any,
) -> ToolRegistry:
    """Register the named groups into a registry (the flat agent-loop surface)."""
    registry = into if into is not None else ToolRegistry()
    for name in groups:
        for tool in build_group(name, project_root, **opts):
            registry.register(tool)
    return registry


__all__ = ["GROUP_BUILDERS", "OPTIONAL_GROUPS", "build_group", "compose"]
