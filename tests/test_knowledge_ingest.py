# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.

"""Tests for `forktex knowledge ingest` — local-first, no Intelligence required.

Local ingest writes the discovered workspace markdown as knowledge nodes into a
doc-space using the recycle() machinery (pure on-disk). The remote vector push
is opt-in and degrades gracefully when Intelligence isn't configured.
"""

from __future__ import annotations

import pytest

from forktex_core.fractal import load_node

from forktex.agent.knowledge import ingest as ingest_mod
from forktex.agent.knowledge.ingest import (
    _collect_files,
    _ingest_local,
    _node_id,
    _push_remote,
)
from forktex.agent.knowledge.sources import ensure_doc_space


def _make_workspace(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "proj-a").mkdir()
    (root / "proj-a" / "AGENTS.md").write_text(
        "# proj-a agent guide\nalpha", encoding="utf-8"
    )
    (root / "proj-b").mkdir()
    (root / "proj-b" / "AGENTS.md").write_text(
        "# proj-b agent guide\nbeta", encoding="utf-8"
    )
    (root / ".hidden").mkdir()  # skipped (dotdir)
    (root / ".hidden" / "AGENTS.md").write_text("nope", encoding="utf-8")
    return root


def test_node_id_stable_and_slugged():
    assert _node_id("forktex-py/AGENTS.md") == "reference.forktex-py-agents-md"
    assert _node_id("docs/overview.md") == "reference.docs-overview-md"


def test_collect_files_finds_agents_md(tmp_path):
    _make_workspace(tmp_path)
    found = dict(_collect_files(tmp_path))
    assert "proj-a/AGENTS.md" in found
    assert "proj-b/AGENTS.md" in found
    assert ".hidden/AGENTS.md" not in found  # dotdirs skipped


def test_ingest_local_writes_nodes_no_intelligence(tmp_path):
    root = _make_workspace(tmp_path / "ws")
    space = ensure_doc_space(tmp_path / "space")

    files = _collect_files(root)
    written = _ingest_local(files, root, space)

    assert written == len(files) >= 2
    node_files = list((space / "nodes").glob("reference.*.md"))
    assert len(node_files) == written

    node = load_node(space / "nodes" / "reference.proj-a-agents-md.md")
    assert node.kind == "reference"
    assert "alpha" in node.body_md
    assert "workspace" in node.tags and "ingest" in node.tags


def test_ingest_records_source_hash_on_patch(tmp_path):
    """Ingest stamps each source's content hash + workspace root on the provenance
    patch so doctor can later detect drift."""
    from forktex_core.fractal.io import load_patch

    root = _make_workspace(tmp_path / "ws")
    space = ensure_doc_space(tmp_path / "space")
    _ingest_local(_collect_files(root), root, space)

    patch = load_patch(
        space / "patches" / "patch.recycle.reference.proj-a-agents-md.md"
    )
    assert getattr(patch, "source_root", None) == str(root)
    hashes = getattr(patch, "source_hashes", None)
    assert hashes and "proj-a/AGENTS.md" in hashes


def test_ingest_local_is_idempotent(tmp_path):
    root = _make_workspace(tmp_path / "ws")
    space = ensure_doc_space(tmp_path / "space")
    files = _collect_files(root)

    _ingest_local(files, root, space)
    first = set((space / "nodes").glob("*.md"))
    _ingest_local(files, root, space)  # re-run
    second = set((space / "nodes").glob("*.md"))

    assert first == second  # same ids → updated in place, no duplicates


@pytest.mark.asyncio
async def test_push_remote_graceful_without_config(tmp_path, monkeypatch):
    """--remote with no api_key must guide, not crash."""

    class _Settings:
        api_key = ""
        endpoint = "https://x"

    monkeypatch.setattr(
        "forktex.agent.intelligence.settings.load_intelligence_settings",
        lambda *a, **k: _Settings(),
    )
    errors: list[str] = []
    monkeypatch.setattr(ingest_mod, "error", lambda msg: errors.append(msg))

    # Must return cleanly (no exception, no Intelligence import/use).
    await _push_remote([], tmp_path, "forktex-workspace")
    assert errors and "auth intelligence" in errors[0]
