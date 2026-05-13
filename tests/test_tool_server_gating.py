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

"""Tests for SECURITY.md §D — bash-tool gating in ToolServer."""

import pytest

from forktex.agent.intelligence.tool_server import ToolServer


pytestmark = pytest.mark.usefixtures("isolated_home")


def test_bash_enabled_by_default(project_root):
    srv = ToolServer(project_root=str(project_root))
    assert srv.bash_enabled is True
    assert srv.desktop_enabled is False
    assert "bash_execute" in srv.list_tools()
    assert "desktop_observe" not in srv.list_tools()


def test_enable_bash_false_removes_bash_execute(project_root):
    srv = ToolServer(project_root=str(project_root), enable_bash=False)
    assert srv.bash_enabled is False
    assert "bash_execute" not in srv.list_tools()
    # Other tool families remain registered.
    assert "read_file" in srv.list_tools()
    assert "git_status" in srv.list_tools()
    assert "graph_summary" in srv.list_tools()


def test_disable_via_env_var(project_root, monkeypatch):
    monkeypatch.setenv("FORKTEX_DISABLE_BASH", "1")
    srv = ToolServer(project_root=str(project_root))
    assert srv.bash_enabled is False
    assert "bash_execute" not in srv.list_tools()


@pytest.mark.parametrize("value", ["true", "TRUE", "yes"])
def test_disable_via_env_var_accepts_truthy_values(project_root, monkeypatch, value):
    monkeypatch.setenv("FORKTEX_DISABLE_BASH", value)
    srv = ToolServer(project_root=str(project_root))
    assert srv.bash_enabled is False


@pytest.mark.parametrize("value", ["", "0", "false", "no"])
def test_falsy_env_var_keeps_bash_enabled(project_root, monkeypatch, value):
    monkeypatch.setenv("FORKTEX_DISABLE_BASH", value)
    srv = ToolServer(project_root=str(project_root))
    assert srv.bash_enabled is True
    assert "bash_execute" in srv.list_tools()


def test_explicit_kwarg_overrides_env_var(project_root, monkeypatch):
    monkeypatch.setenv("FORKTEX_DISABLE_BASH", "1")
    # Explicit True overrides the env var.
    srv = ToolServer(project_root=str(project_root), enable_bash=True)
    assert srv.bash_enabled is True
    assert "bash_execute" in srv.list_tools()


def test_desktop_tools_are_explicitly_gated(project_root):
    srv = ToolServer(project_root=str(project_root))
    assert srv.desktop_enabled is False
    assert "desktop_info" not in srv.list_tools()
    assert "desktop_screenshot" not in srv.list_tools()
    assert "desktop_observe" not in srv.list_tools()


def test_enable_desktop_registers_observe_only_tools(project_root):
    srv = ToolServer(project_root=str(project_root), enable_desktop=True)
    names = srv.list_tools()
    assert srv.desktop_enabled is True
    assert "desktop_info" in names
    assert "desktop_screenshot" in names
    assert "desktop_observe" in names
    assert "desktop_click" not in names
    assert "desktop_key" not in names


def test_enable_desktop_env_var(project_root, monkeypatch):
    monkeypatch.setenv("FORKTEX_ENABLE_DESKTOP", "1")
    srv = ToolServer(project_root=str(project_root))
    assert srv.desktop_enabled is True
    assert "desktop_observe" in srv.list_tools()
