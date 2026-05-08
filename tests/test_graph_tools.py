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

"""Tests for the agent-callable graph tools."""

import pytest

from forktex.agent.tools.graph_tools import create_graph_tools
from forktex.graph.query import bust_cache


pytestmark = [pytest.mark.usefixtures("isolated_home"), pytest.mark.asyncio]


@pytest.fixture
def seeded_project(project_root):
    """Add a small Python tree so the graph has shape."""
    pkg = project_root / "src" / "proj" / "auth"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "login.py").write_text("import json\nfrom proj.auth import session\n")
    (pkg / "session.py").write_text("import os\n")
    (project_root / "src" / "proj" / "__init__.py").write_text("")
    (project_root / "pyproject.toml").write_text(
        '[project]\nname = "proj"\nversion = "0.1.0"\n'
        'dependencies = ["pydantic (>=2)"]\n'
    )
    bust_cache()
    return project_root


def _by_name(tools, name):
    return next(t for t in tools if t.name == name)


async def test_graph_summary_tool(seeded_project):
    tools = create_graph_tools(seeded_project)
    result = await _by_name(tools, "graph_summary").execute()
    assert not result.is_error
    assert "packages=" in result.content
    assert result.data["package_count"] >= 1


async def test_list_packages_tool(seeded_project):
    tools = create_graph_tools(seeded_project)
    result = await _by_name(tools, "list_packages").execute()
    assert not result.is_error
    assert "packages" in result.data
    assert len(result.data["packages"]) >= 1


async def test_find_package_tool(seeded_project):
    tools = create_graph_tools(seeded_project)
    result = await _by_name(tools, "find_package").execute(
        rel_path="src/proj/auth/login.py"
    )
    assert not result.is_error
    assert result.data is not None


async def test_list_domains_tool(seeded_project):
    tools = create_graph_tools(seeded_project)
    result = await _by_name(tools, "list_domains").execute()
    assert not result.is_error
    names = {d["name"] for d in result.data["domains"]}
    assert "auth" in names


async def test_find_modules_tool(seeded_project):
    tools = create_graph_tools(seeded_project)
    result = await _by_name(tools, "find_modules").execute(name_pattern="*login*")
    assert not result.is_error
    assert any(m["name"] == "login" for m in result.data["matches"])


async def test_find_importers_tool(seeded_project):
    tools = create_graph_tools(seeded_project)
    result = await _by_name(tools, "find_importers").execute(target="proj.auth.session")
    assert not result.is_error
    assert any("login" in i["src"] for i in result.data["importers"])


async def test_fsd_status_tool(seeded_project):
    tools = create_graph_tools(seeded_project)
    result = await _by_name(tools, "fsd_status").execute()
    assert not result.is_error
    assert "statuses" in result.data


async def test_validate_path_tool(seeded_project):
    tools = create_graph_tools(seeded_project)
    ok = await _by_name(tools, "validate_path").execute(rel_path="graph.json")
    assert ok.data["ok"] is True
    bad = await _by_name(tools, "validate_path").execute(rel_path="rogue.bin")
    assert bad.data["ok"] is False


async def test_recent_writes_tool(seeded_project):
    tools = create_graph_tools(seeded_project)
    result = await _by_name(tools, "recent_writes").execute(hours=1)
    assert not result.is_error
    assert "touches" in result.data


async def test_ecosystem_matrix_tool(seeded_project):
    tools = create_graph_tools(seeded_project)
    result = await _by_name(tools, "ecosystem_matrix").execute()
    assert not result.is_error
    assert "rows" in result.data


async def test_list_modules_tool(seeded_project):
    tools = create_graph_tools(seeded_project)
    domains = await _by_name(tools, "list_domains").execute()
    domain_id = domains.data["domains"][0]["id"]
    result = await _by_name(tools, "list_modules").execute(domain_id=domain_id)
    assert not result.is_error
    assert "modules" in result.data


async def test_package_imports_tool(seeded_project):
    tools = create_graph_tools(seeded_project)
    pkgs = await _by_name(tools, "list_packages").execute()
    pkg_id = pkgs.data["packages"][0]["id"]
    result = await _by_name(tools, "package_imports").execute(package_id=pkg_id)
    assert not result.is_error
    assert "imports" in result.data
