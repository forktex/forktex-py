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

"""
forktex.agent.tools.git - Git tools for LLM tool calling.
"""

from __future__ import annotations

import asyncio
import json
from typing import List, Optional

from forktex.agent.tools.base import Tool, ToolResult


class GitToolError(RuntimeError):
    """Raised when Git operations fail."""

    pass


async def _run_git(project_root: str, *args: str) -> str:
    """Run a git command and return stdout."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=project_root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        error = stderr.decode(errors="replace").strip()
        raise GitToolError(error or f"git {args[0]} failed")
    return stdout.decode(errors="replace").strip()


async def _git_status(project_root: str) -> ToolResult:
    try:
        branch = await _run_git(project_root, "rev-parse", "--abbrev-ref", "HEAD")
        porcelain = await _run_git(project_root, "status", "--porcelain")

        staged = []
        modified = []
        untracked = []
        for line in porcelain.splitlines():
            if not line or len(line) < 3:
                continue
            x, y = line[0], line[1]
            filepath = line[3:]
            if x in "MADRC":
                staged.append(filepath)
            if y in "MD":
                modified.append(filepath)
            if x == "?" and y == "?":
                untracked.append(filepath)

        data = {
            "branch": branch,
            "staged": staged,
            "modified": modified,
            "untracked": untracked,
        }
        return ToolResult(content=json.dumps(data, indent=2), data=data)
    except GitToolError as exc:
        return ToolResult(content=f"Git error: {exc}", is_error=True)
    except FileNotFoundError:
        return ToolResult(content="git is not installed", is_error=True)


async def _git_diff(project_root: str, staged: bool = False) -> ToolResult:
    try:
        args = ["diff"]
        if staged:
            args.append("--staged")
        diff = await _run_git(project_root, *args)
        return ToolResult(content=diff or "(no changes)", data={"diff": diff})
    except GitToolError as exc:
        return ToolResult(content=f"Git error: {exc}", is_error=True)


async def _git_commit(
    project_root: str, message: str, files: Optional[List[str]] = None
) -> ToolResult:
    try:
        if files:
            await _run_git(project_root, "add", *files)
        else:
            await _run_git(project_root, "add", "-A")
        await _run_git(project_root, "commit", "-m", message)
        commit_hash = await _run_git(project_root, "rev-parse", "HEAD")
        data = {"hash": commit_hash, "message": message}
        return ToolResult(
            content=f"Committed: {commit_hash[:8]} {message}",
            data=data,
        )
    except GitToolError as exc:
        return ToolResult(content=f"Git error: {exc}", is_error=True)


async def _git_log(project_root: str, n: int = 10) -> ToolResult:
    try:
        log_output = await _run_git(
            project_root,
            "log",
            f"-{n}",
            "--format=%H|%s|%an|%aI",
        )
        commits = []
        for line in log_output.splitlines():
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) >= 4:
                commits.append(
                    {
                        "hash": parts[0],
                        "message": parts[1],
                        "author": parts[2],
                        "date": parts[3],
                    }
                )
        data = {"commits": commits}
        return ToolResult(content=json.dumps(data, indent=2), data=data)
    except GitToolError as exc:
        return ToolResult(content=f"Git error: {exc}", is_error=True)


async def _git_branch(
    project_root: str, name: str, checkout: bool = True
) -> ToolResult:
    """Create a new branch and optionally check it out."""
    try:
        await _run_git(project_root, "branch", name)
        if checkout:
            await _run_git(project_root, "checkout", name)
        branch = await _run_git(project_root, "rev-parse", "--abbrev-ref", "HEAD")
        return ToolResult(
            content=f"Branch '{name}' created. On: {branch}",
            data={"branch": name, "checked_out": checkout, "current": branch},
        )
    except GitToolError as exc:
        return ToolResult(content=f"Git error: {exc}", is_error=True)


async def _git_checkout(project_root: str, ref: str) -> ToolResult:
    """Checkout a branch or ref."""
    try:
        await _run_git(project_root, "checkout", ref)
        branch = await _run_git(project_root, "rev-parse", "--abbrev-ref", "HEAD")
        return ToolResult(
            content=f"Checked out: {branch}",
            data={"branch": branch},
        )
    except GitToolError as exc:
        return ToolResult(content=f"Git error: {exc}", is_error=True)


async def _git_branch_list(project_root: str) -> ToolResult:
    """List all local branches."""
    try:
        output = await _run_git(project_root, "branch", "--list", "--no-color")
        branches = []
        current = None
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("* "):
                name = line[2:]
                current = name
                branches.append(name)
            else:
                branches.append(line)
        data = {"branches": branches, "current": current}
        return ToolResult(content=json.dumps(data, indent=2), data=data)
    except GitToolError as exc:
        return ToolResult(content=f"Git error: {exc}", is_error=True)


def create_git_tools(project_root: str) -> List[Tool]:
    """Create git tools bound to a project root."""
    return [
        Tool(
            name="git_status",
            description="Get git status (branch, staged, modified, untracked files)",
            parameters={"type": "object", "properties": {}},
            handler=lambda: _git_status(project_root),
        ),
        Tool(
            name="git_diff",
            description="Show git diff of working directory or staged changes",
            parameters={
                "type": "object",
                "properties": {
                    "staged": {
                        "type": "boolean",
                        "description": "Show staged changes only",
                        "default": False,
                    },
                },
            },
            handler=lambda staged=False: _git_diff(project_root, staged),
        ),
        Tool(
            name="git_commit",
            description="Stage and commit changes",
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Commit message"},
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific files to stage (defaults to all)",
                    },
                },
                "required": ["message"],
            },
            handler=lambda message, files=None: _git_commit(
                project_root, message, files
            ),
        ),
        Tool(
            name="git_log",
            description="Show recent git commits",
            parameters={
                "type": "object",
                "properties": {
                    "n": {
                        "type": "integer",
                        "description": "Number of commits",
                        "default": 10,
                    },
                },
            },
            handler=lambda n=10: _git_log(project_root, n),
        ),
        Tool(
            name="git_branch",
            description="Create a new branch and optionally check it out",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Branch name to create"},
                    "checkout": {
                        "type": "boolean",
                        "description": "Check out after creating",
                        "default": True,
                    },
                },
                "required": ["name"],
            },
            handler=lambda name, checkout=True: _git_branch(
                project_root, name, checkout
            ),
        ),
        Tool(
            name="git_checkout",
            description="Checkout a branch or ref",
            parameters={
                "type": "object",
                "properties": {
                    "ref": {
                        "type": "string",
                        "description": "Branch name or commit ref",
                    },
                },
                "required": ["ref"],
            },
            handler=lambda ref: _git_checkout(project_root, ref),
        ),
        Tool(
            name="git_branch_list",
            description="List all local branches",
            parameters={"type": "object", "properties": {}},
            handler=lambda: _git_branch_list(project_root),
        ),
    ]
