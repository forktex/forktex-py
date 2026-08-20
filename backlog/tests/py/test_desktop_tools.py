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

"""Tests for observe-only desktop tools."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from forktex.agent.tools.desktop import GnomeWaylandProvider, create_desktop_tools


pytestmark = pytest.mark.usefixtures("isolated_home")


def _tool_by_name(name: str, project_root: Path):
    tools = {tool.name: tool for tool in create_desktop_tools(str(project_root))}
    return tools[name]


def test_desktop_info_reports_observe_only_capabilities(project_root, monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    monkeypatch.setattr("forktex.agent.tools.desktop.shutil.which", lambda cmd: None)

    provider = GnomeWaylandProvider(str(project_root))
    info = provider.info()

    assert info["provider"] == "gnome-wayland"
    assert info["session"]["type"] == "wayland"
    assert info["capabilities"]["mouse"] is False
    assert info["capabilities"]["keyboard"] is False
    assert info["capabilities"]["screenshot"] is False
    assert info["safety"]["mode"] == "observe-only"


@pytest.mark.asyncio
async def test_desktop_screenshot_returns_structured_metadata(
    project_root, monkeypatch
):
    def fake_which(cmd):
        return "/usr/bin/grim" if cmd == "grim" else None

    def fake_run(cmd, capture_output, text, timeout):
        Path(cmd[-1]).write_bytes(b"fake-png")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("forktex.agent.tools.desktop.shutil.which", fake_which)
    monkeypatch.setattr("forktex.agent.tools.desktop.subprocess.run", fake_run)

    result = await _tool_by_name("desktop_screenshot", project_root).execute()

    assert result.is_error is False
    assert result.data["provider"] == "gnome-wayland"
    assert result.data["backend"] == "grim"
    assert result.data["mime_type"] == "image/png"
    assert result.data["bytes"] == 8
    assert Path(result.data["path"]).exists()


@pytest.mark.asyncio
async def test_desktop_observe_omits_base64_from_content(project_root, monkeypatch):
    def fake_which(cmd):
        return "/usr/bin/grim" if cmd == "grim" else None

    def fake_run(cmd, capture_output, text, timeout):
        Path(cmd[-1]).write_bytes(b"fake-png")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("forktex.agent.tools.desktop.shutil.which", fake_which)
    monkeypatch.setattr("forktex.agent.tools.desktop.subprocess.run", fake_run)

    result = await _tool_by_name("desktop_observe", project_root).execute(
        include_base64=True
    )

    assert result.is_error is False
    assert result.data["desktop"]["capabilities"]["observe"] is True
    assert "base64" in result.data["screenshot"]
    assert result.data["screenshot"]["base64"]
    assert "<omitted>" in result.content


@pytest.mark.asyncio
async def test_desktop_screenshot_reports_unsupported_backend(
    project_root, monkeypatch
):
    monkeypatch.setattr("forktex.agent.tools.desktop.shutil.which", lambda cmd: None)

    result = await _tool_by_name("desktop_screenshot", project_root).execute()

    assert result.is_error is True
    assert "No supported screenshot backend found" in result.content
