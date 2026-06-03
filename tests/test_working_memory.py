# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.

"""Agent working memory (knowledge face 5.2) — write mid-task, recall, survive cache purge.

`remember()` persists a note into the ephemeral `state/agents/memory/` doc-space;
it composes as the top recall layer so `knowledge search` finds it; it lives in
`state/` so a `cache/` wipe doesn't touch it; and it's distinct from durable
`knowledge/nodes` lessons.
"""

from __future__ import annotations

import pytest

from forktex.agent.knowledge.memory import (
    create_memory_tools,
    memory_source,
    remember,
)
from forktex.substrate import paths as _sub


def test_remember_writes_note_into_state(tmp_path):
    node = remember(
        tmp_path, "the auth token lives in secrets/intelligence.json", tags=["auth"]
    )
    assert node.kind == "observation"
    assert "memory" in node.tags and "auth" in node.tags

    mem = _sub.agent_memory_dir(tmp_path)
    files = list((mem / "nodes").glob("*.md"))
    assert len(files) == 1
    # Under state/ (ephemeral), NOT knowledge/ (committed).
    assert "state" in mem.parts and "agents" in mem.parts


def test_remember_empty_rejected(tmp_path):
    with pytest.raises(ValueError):
        remember(tmp_path, "   ")


def test_memory_source_none_until_a_note_exists(tmp_path):
    assert memory_source(tmp_path) is None  # no notes yet → no empty layer
    remember(tmp_path, "first observation")
    src = memory_source(tmp_path)
    assert src is not None
    name, path, adapter = src
    assert name == "memory" and adapter == "workspace"


def test_recall_via_resolver_composes_memory(tmp_path):
    from forktex_core.fractal import FractalQuery

    from forktex.agent.knowledge.search import ranked_search
    from forktex.agent.knowledge.sources import build_knowledge_resolver

    remember(tmp_path, "the flux capacitor needs 1.21 gigawatts", tags=["flux"])
    resolver = build_knowledge_resolver(extra_sources=[memory_source(tmp_path)])
    hits = ranked_search(FractalQuery(resolver), "knowledge", "flux capacitor", limit=5)
    assert any(n.kind == "observation" for n in hits)


def test_survives_cache_semantics(tmp_path):
    """Working memory is under state/, not cache/ — a cache purge would not remove it."""
    remember(tmp_path, "note that outlives the cache")
    mem = _sub.agent_memory_dir(tmp_path)
    cache = _sub.cache_dir(tmp_path)
    # The memory dir is not inside cache/.
    assert cache not in mem.parents


@pytest.mark.asyncio
async def test_remember_tool(tmp_path):
    (tool,) = create_memory_tools(str(tmp_path))
    assert tool.name == "remember"
    res = await tool.execute(note="remembered via the tool", tags=["t"])
    assert not res.is_error
    assert "remembered" in res.content
    assert memory_source(tmp_path) is not None
