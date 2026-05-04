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

"""Tests for forktex.agent.tools (filesystem, bash, git against tmp dirs)."""

import pytest
from pathlib import Path

from forktex.agent.tools.base import Tool, ToolResult, ToolRegistry
from forktex.agent.tools.filesystem import create_filesystem_tools
from forktex.agent.tools.bash import create_bash_tools
from forktex.agent.tools.git import create_git_tools
from forktex.agent.tools.server import ToolServer


class TestToolResult:
    def test_basic(self):
        r = ToolResult(content="ok")
        assert r.content == "ok"
        assert r.is_error is False

    def test_error(self):
        r = ToolResult(content="fail", is_error=True)
        assert r.is_error is True

    def test_to_dict(self):
        r = ToolResult(content="ok", data={"key": "val"})
        d = r.to_dict()
        assert d["content"] == "ok"
        assert d["data"]["key"] == "val"


class TestToolRegistry:
    @pytest.mark.asyncio
    async def test_register_and_call(self):
        registry = ToolRegistry()

        async def echo_handler(text: str) -> ToolResult:
            return ToolResult(content=text)

        tool = Tool(
            name="echo",
            description="Echo text",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            handler=echo_handler,
        )
        registry.register(tool)

        assert "echo" in registry
        assert len(registry) == 1

        result = await registry.call("echo", text="hello")
        assert result.content == "hello"

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        registry = ToolRegistry()
        result = await registry.call("nonexistent")
        assert result.is_error

    def test_list_schemas(self):
        registry = ToolRegistry()

        async def noop() -> ToolResult:
            return ToolResult(content="")

        registry.register(
            Tool(name="t1", description="Test 1", parameters={}, handler=noop)
        )
        registry.register(
            Tool(name="t2", description="Test 2", parameters={}, handler=noop)
        )

        schemas = registry.list_schemas()
        assert len(schemas) == 2
        assert schemas[0]["name"] == "t1"


class TestFilesystemTools:
    @pytest.mark.asyncio
    async def test_read_file(self, temp_dir_with_files):
        tools = {t.name: t for t in create_filesystem_tools(temp_dir_with_files)}
        result = await tools["read_file"].execute(path="main.py")
        assert not result.is_error
        assert "hello" in result.content

    @pytest.mark.asyncio
    async def test_read_nonexistent(self, temp_dir):
        tools = {t.name: t for t in create_filesystem_tools(temp_dir)}
        result = await tools["read_file"].execute(path="nope.py")
        assert result.is_error

    @pytest.mark.asyncio
    async def test_write_file(self, temp_dir):
        tools = {t.name: t for t in create_filesystem_tools(temp_dir)}
        result = await tools["write_file"].execute(path="new.py", content="print(1)")
        assert not result.is_error
        assert (Path(temp_dir) / "new.py").read_text() == "print(1)"

    @pytest.mark.asyncio
    async def test_patch_file(self, temp_dir_with_files):
        tools = {t.name: t for t in create_filesystem_tools(temp_dir_with_files)}
        result = await tools["patch_file"].execute(
            path="main.py", old_str="hello", new_str="world"
        )
        assert not result.is_error
        content = (Path(temp_dir_with_files) / "main.py").read_text()
        assert "world" in content

    @pytest.mark.asyncio
    async def test_delete_file(self, temp_dir_with_files):
        tools = {t.name: t for t in create_filesystem_tools(temp_dir_with_files)}
        result = await tools["delete_file"].execute(path="main.py")
        assert not result.is_error
        assert not (Path(temp_dir_with_files) / "main.py").exists()

    @pytest.mark.asyncio
    async def test_list_directory(self, temp_dir_with_files):
        tools = {t.name: t for t in create_filesystem_tools(temp_dir_with_files)}
        result = await tools["list_directory"].execute()
        assert not result.is_error
        assert result.data is not None
        names = [e["name"] for e in result.data["entries"]]
        assert any("main.py" in n for n in names)

    @pytest.mark.asyncio
    async def test_glob_search(self, temp_dir_with_files):
        tools = {t.name: t for t in create_filesystem_tools(temp_dir_with_files)}
        result = await tools["glob_search"].execute(pattern="*.py")
        assert not result.is_error
        assert len(result.data["matches"]) >= 2

    @pytest.mark.asyncio
    async def test_grep_search(self, temp_dir_with_files):
        tools = {t.name: t for t in create_filesystem_tools(temp_dir_with_files)}
        result = await tools["grep_search"].execute(pattern="def add")
        assert not result.is_error
        assert len(result.data["matches"]) >= 1


class TestBashTools:
    @pytest.mark.asyncio
    async def test_execute(self, temp_dir):
        tools = {t.name: t for t in create_bash_tools(temp_dir)}
        result = await tools["bash_execute"].execute(command="echo hello")
        assert not result.is_error
        assert "hello" in result.content

    @pytest.mark.asyncio
    async def test_execute_error(self, temp_dir):
        tools = {t.name: t for t in create_bash_tools(temp_dir)}
        result = await tools["bash_execute"].execute(command="exit 1")
        assert result.is_error
        assert result.data["exit_code"] == 1


class TestGitTools:
    @pytest.mark.asyncio
    async def test_status(self, temp_git_repo):
        tools = {t.name: t for t in create_git_tools(temp_git_repo)}
        result = await tools["git_status"].execute()
        assert not result.is_error
        assert "branch" in result.data

    @pytest.mark.asyncio
    async def test_diff(self, temp_git_repo):
        # Make a change
        (Path(temp_git_repo) / "file.txt").write_text("changed\n")
        tools = {t.name: t for t in create_git_tools(temp_git_repo)}
        result = await tools["git_diff"].execute()
        assert not result.is_error

    @pytest.mark.asyncio
    async def test_log(self, temp_git_repo):
        tools = {t.name: t for t in create_git_tools(temp_git_repo)}
        result = await tools["git_log"].execute(n=5)
        assert not result.is_error
        assert len(result.data["commits"]) >= 1


class TestToolServer:
    def test_creation(self, temp_dir_with_files):
        server = ToolServer(temp_dir_with_files, enable_web=False)
        names = server.list_tools()
        assert "read_file" in names
        assert "bash_execute" in names
        assert "git_status" in names

    def test_schemas(self, temp_dir_with_files):
        server = ToolServer(temp_dir_with_files, enable_web=False)
        schemas = server.get_schemas()
        assert len(schemas) > 0
        assert all("name" in s for s in schemas)

    @pytest.mark.asyncio
    async def test_call(self, temp_dir_with_files):
        server = ToolServer(temp_dir_with_files, enable_web=False)
        result = await server.call("read_file", path="main.py")
        assert not result.is_error
