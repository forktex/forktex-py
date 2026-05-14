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

"""Comprehensive battle tests for forktex.

Covers:
- All tool types (filesystem, bash, git)
- ToolServer facade
- Config loading
- CLI import
- Core library imports
"""

import subprocess
from pathlib import Path

import pytest

# ============================================================================
# Tool Battle Tests
# ============================================================================


class TestFilesystemToolsBattle:
    """Battle tests for every filesystem tool."""

    @pytest.fixture
    def fs_tools(self, temp_dir_with_files):
        from forktex.agent.tools.filesystem import create_filesystem_tools

        return {t.name: t for t in create_filesystem_tools(temp_dir_with_files)}

    @pytest.mark.asyncio
    async def test_read_file(self, fs_tools):
        r = await fs_tools["read_file"].execute(path="main.py")
        assert not r.is_error
        assert "hello" in r.content

    @pytest.mark.asyncio
    async def test_write_file(self, fs_tools, temp_dir_with_files):
        r = await fs_tools["write_file"].execute(path="new.txt", content="hello world")
        assert not r.is_error
        assert (Path(temp_dir_with_files) / "new.txt").read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_patch_file(self, fs_tools, temp_dir_with_files):
        r = await fs_tools["patch_file"].execute(
            path="main.py", old_str="hello", new_str="goodbye"
        )
        assert not r.is_error
        assert "goodbye" in (Path(temp_dir_with_files) / "main.py").read_text()

    @pytest.mark.asyncio
    async def test_delete_file(self, fs_tools, temp_dir_with_files):
        r = await fs_tools["delete_file"].execute(path="README.md")
        assert not r.is_error
        assert not (Path(temp_dir_with_files) / "README.md").exists()

    @pytest.mark.asyncio
    async def test_list_directory(self, fs_tools):
        r = await fs_tools["list_directory"].execute()
        assert not r.is_error
        names = [e["name"] for e in r.data["entries"]]
        assert "main.py" in names

    @pytest.mark.asyncio
    async def test_list_directory_recursive(self, fs_tools):
        r = await fs_tools["list_directory"].execute(recursive=True)
        assert not r.is_error
        names = [e["name"] for e in r.data["entries"]]
        assert "src" in names

    @pytest.mark.asyncio
    async def test_glob_search(self, fs_tools):
        r = await fs_tools["glob_search"].execute(pattern="**/*.py")
        assert not r.is_error
        assert len(r.data["matches"]) >= 2

    @pytest.mark.asyncio
    async def test_grep_search(self, fs_tools):
        r = await fs_tools["grep_search"].execute(pattern="def add")
        assert not r.is_error
        assert len(r.data["matches"]) >= 1
        assert "utils.py" in r.data["matches"][0]["file"]

    @pytest.mark.asyncio
    async def test_read_nonexistent(self, fs_tools):
        r = await fs_tools["read_file"].execute(path="does_not_exist.py")
        assert r.is_error

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, fs_tools):
        with pytest.raises(ValueError, match="escapes project root"):
            await fs_tools["read_file"].execute(path="../../../etc/passwd")


class TestBashToolsBattle:
    """Battle tests for bash tools."""

    @pytest.fixture
    def bash_tools(self, temp_dir):
        from forktex.agent.tools.bash import create_bash_tools

        return {t.name: t for t in create_bash_tools(temp_dir)}

    @pytest.mark.asyncio
    async def test_simple_command(self, bash_tools):
        r = await bash_tools["bash_execute"].execute(command="echo 'battle test'")
        assert not r.is_error
        assert "battle test" in r.content

    @pytest.mark.asyncio
    async def test_command_with_exit_code(self, bash_tools):
        r = await bash_tools["bash_execute"].execute(command="exit 42")
        assert r.is_error
        assert r.data["exit_code"] == 42

    @pytest.mark.asyncio
    async def test_multiline_output(self, bash_tools):
        r = await bash_tools["bash_execute"].execute(
            command="echo 'line1'; echo 'line2'; echo 'line3'"
        )
        assert not r.is_error
        assert "line1" in r.content
        assert "line3" in r.content

    @pytest.mark.asyncio
    async def test_stderr_capture(self, bash_tools):
        r = await bash_tools["bash_execute"].execute(command="echo 'err' >&2 && exit 1")
        assert r.is_error
        assert "err" in r.data.get("stderr", "")

    @pytest.mark.asyncio
    async def test_cwd_is_project_root(self, bash_tools, temp_dir):
        r = await bash_tools["bash_execute"].execute(command="pwd")
        assert not r.is_error
        assert temp_dir in r.content


class TestGitToolsBattle:
    """Battle tests for git tools."""

    @pytest.fixture
    def git_tools(self, temp_git_repo):
        from forktex.agent.tools.git import create_git_tools

        return {t.name: t for t in create_git_tools(temp_git_repo)}

    @pytest.mark.asyncio
    async def test_status(self, git_tools):
        r = await git_tools["git_status"].execute()
        assert not r.is_error
        assert "branch" in r.data

    @pytest.mark.asyncio
    async def test_diff_clean(self, git_tools):
        r = await git_tools["git_diff"].execute()
        assert not r.is_error

    @pytest.mark.asyncio
    async def test_diff_after_change(self, git_tools, temp_git_repo):
        (Path(temp_git_repo) / "file.txt").write_text("modified\n")
        r = await git_tools["git_diff"].execute()
        assert not r.is_error
        assert "modified" in r.data.get("diff", "")

    @pytest.mark.asyncio
    async def test_log(self, git_tools):
        r = await git_tools["git_log"].execute(n=10)
        assert not r.is_error
        assert len(r.data["commits"]) >= 1
        assert "initial" in r.data["commits"][0]["message"]

    @pytest.mark.asyncio
    async def test_commit(self, git_tools, temp_git_repo):
        (Path(temp_git_repo) / "new.txt").write_text("new file\n")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        r = await git_tools["git_commit"].execute(message="add new file")
        assert not r.is_error
        assert r.data["hash"]


# ============================================================================
# ToolServer Battle Tests
# ============================================================================


class TestToolServerBattle:
    """Battle tests for the ToolServer facade."""

    def test_creates_all_tool_groups(self, temp_dir_with_files):
        from forktex.agent.tools.server import ToolServer

        server = ToolServer(temp_dir_with_files, enable_web=False)
        names = server.list_tools()
        # filesystem
        assert "read_file" in names
        assert "write_file" in names
        assert "patch_file" in names
        assert "delete_file" in names
        assert "list_directory" in names
        assert "glob_search" in names
        assert "grep_search" in names
        # bash
        assert "bash_execute" in names
        # git
        assert "git_status" in names
        assert "git_diff" in names
        assert "git_commit" in names
        assert "git_log" in names

    def test_schemas_are_valid_json_schema(self, temp_dir_with_files):
        from forktex.agent.tools.server import ToolServer

        server = ToolServer(temp_dir_with_files, enable_web=False)
        schemas = server.get_schemas()
        for s in schemas:
            assert "name" in s
            assert "description" in s
            assert "parameters" in s
            assert isinstance(s["parameters"], dict)

    @pytest.mark.asyncio
    async def test_call_through_server(self, temp_dir_with_files):
        from forktex.agent.tools.server import ToolServer

        server = ToolServer(temp_dir_with_files, enable_web=False)
        r = await server.call("read_file", path="main.py")
        assert not r.is_error
        assert "hello" in r.content

    @pytest.mark.asyncio
    async def test_call_unknown_tool(self, temp_dir_with_files):
        from forktex.agent.tools.server import ToolServer

        server = ToolServer(temp_dir_with_files, enable_web=False)
        r = await server.call("nonexistent_tool")
        assert r.is_error


# ============================================================================
# Config Battle Tests
# ============================================================================


class TestConfigBattle:
    def test_default_settings(self):
        from forktex.config import Settings

        s = Settings()
        assert s.debug is False

    def test_env_loading(self, monkeypatch):
        from forktex.config import Settings, reset_settings

        reset_settings()
        monkeypatch.setenv("FORKTEX_DEBUG", "true")
        s = Settings.load()
        assert s.debug is True

    def test_override_kwargs(self):
        from forktex.config import Settings

        s = Settings.load(debug=True)
        assert s.debug is True

    def test_get_settings_singleton(self):
        from forktex.config import get_settings, reset_settings

        reset_settings()
        s1 = get_settings(debug=True)
        s2 = get_settings()
        assert s1 is s2


# ============================================================================
# CLI Battle Tests
# ============================================================================


class TestCLIBattle:
    def test_imports(self):
        from forktex.agent.cli import cli, main

        assert cli is not None
        assert main is not None

    def test_package_exports(self):
        from forktex import (
            StateManager,
            Settings,
        )

        assert StateManager is not None
        assert Settings is not None

    def test_version(self):
        import re

        from forktex import __version__

        assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


# ============================================================================
# Core Library Import Battle Tests
# ============================================================================


class TestCoreLibraryImports:
    """Verify that base install imports work without CLI deps."""

    def test_core_imports(self):
        from forktex.core.state import StateManager
        from forktex.core.utils import generate_id

        assert StateManager is not None
        assert generate_id is not None

    def test_config_import(self):
        from forktex.config import Settings

        assert Settings is not None

    def test_intelligence_library_imports(self):
        from forktex_intelligence import Intelligence
        from forktex_intelligence.config import IntelligenceSettings
        from forktex_intelligence.streams import SSEEvent

        assert IntelligenceSettings is not None
        assert Intelligence is not None
        assert SSEEvent is not None

    def test_intelligence_high_level_api_imports(self):
        from forktex.intelligence import (
            Intelligence,
            Response,
            StructuredResponse,
            StreamChunks,
            ChatMessage,
            ToolCallInfo,
        )

        assert Intelligence is not None
        assert Response is not None
        assert StructuredResponse is not None
        assert StreamChunks is not None
        assert ChatMessage is not None
        assert ToolCallInfo is not None

    def test_standalone_intelligence_imports(self):
        """Verify that forktex_intelligence standalone package imports work."""
        from forktex_intelligence import (
            Intelligence,
            Response,
            IntelligenceSettings,
        )

        assert Intelligence is not None
        assert Response is not None
        assert IntelligenceSettings is not None

    def test_standalone_cloud_imports(self):
        """Verify that forktex_cloud standalone package imports work."""
        from forktex_cloud import (
            Cloud,
            CloudContext,
            Manifest,
            ProjectRead,
        )

        assert Cloud is not None
        assert CloudContext is not None
        assert Manifest is not None
        assert ProjectRead is not None
