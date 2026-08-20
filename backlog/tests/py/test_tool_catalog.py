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

"""Battle tests for the central tool catalog (the one tool-builder source)."""

from __future__ import annotations

import pytest

from forktex.agent.tools.catalog import GROUP_BUILDERS, build_group, compose


def test_catalog_lists_every_known_group():
    assert set(GROUP_BUILDERS) == {
        "filesystem",
        "bash",
        "git",
        "graph",
        "desktop",
        "web",
        "knowledge",
        "memory",
        "fsd",
    }


def test_build_group_returns_tools(tmp_path):
    tools = build_group("git", tmp_path)
    names = {t.name for t in tools}
    assert "git_status" in names


def test_unknown_group_raises(tmp_path):
    with pytest.raises(KeyError):
        build_group("nonsense", tmp_path)


def test_compose_unions_groups_into_one_registry(tmp_path):
    reg = compose(tmp_path, ["filesystem", "git"])
    names = {t.name for t in reg.list_tools()}
    assert {"read_file", "git_status"} <= names


def test_read_only_knowledge_drops_write_tools(tmp_path):
    ro = {t.name for t in build_group("knowledge", tmp_path, read_only=True)}
    rw = {t.name for t in build_group("knowledge", tmp_path, read_only=False)}
    # read-only exposes search but never recycle; read-write adds the writes.
    assert "knowledge_recycle" not in ro
    if rw:  # knowledge degrades to [] without forktex-core[fractal]
        assert "knowledge_recycle" in rw


def test_both_tool_servers_compose_from_catalog(tmp_path):
    """The agent-loop ToolServers and the catalog stay in lockstep."""
    from forktex.agent.tools.server import intelligence_tool_server as Intel
    from forktex.agent.tools.server import ToolServer as Full

    full = set(Full(str(tmp_path), enable_web=False, enable_desktop=False).list_tools())
    intel = set(
        Intel(str(tmp_path), enable_bash=True, enable_desktop=False).list_tools()
    )
    # Full = filesystem+bash+git; Intel additionally has graph (arch) tools.
    assert {"read_file", "git_status", "bash_execute"} <= full
    assert "graph_summary" in intel
