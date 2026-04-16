"""
forktex.agent.tools.filesystem - File system tools for LLM tool calling.

Tools: read_file, write_file, patch_file, delete_file, list_directory,
       glob_search, grep_search
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from forktex.agent.tools.base import Tool, ToolResult


def _resolve(project_root: str, path: str) -> Path:
    """Resolve a path relative to project root, with safety check."""
    root = Path(project_root).resolve()
    resolved = (root / path).resolve()
    if not str(resolved).startswith(str(root)):
        raise ValueError(f"Path escapes project root: {path}")
    return resolved


async def _read_file(project_root: str, path: str) -> ToolResult:
    full = _resolve(project_root, path)
    if not full.exists():
        return ToolResult(content=f"File not found: {path}", is_error=True)
    if not full.is_file():
        return ToolResult(content=f"Not a file: {path}", is_error=True)
    try:
        content = await asyncio.to_thread(full.read_text)
        lines = content.count("\n") + 1
        size = full.stat().st_size
        return ToolResult(
            content=content,
            data={"content": content, "lines": lines, "size": size},
        )
    except UnicodeDecodeError:
        return ToolResult(content=f"Binary file, cannot read as text: {path}", is_error=True)
    except Exception as exc:
        return ToolResult(content=f"Error reading {path}: {exc}", is_error=True)


async def _write_file(project_root: str, path: str, content: str) -> ToolResult:
    full = _resolve(project_root, path)
    try:
        await asyncio.to_thread(full.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(full.write_text, content)
        return ToolResult(
            content=f"Written {len(content)} bytes to {path}",
            data={"success": True, "path": path, "bytes_written": len(content)},
        )
    except Exception as exc:
        return ToolResult(content=f"Error writing {path}: {exc}", is_error=True)


async def _patch_file(
    project_root: str, path: str, old_str: str, new_str: str
) -> ToolResult:
    full = _resolve(project_root, path)
    if not full.exists():
        return ToolResult(content=f"File not found: {path}", is_error=True)
    try:
        content = await asyncio.to_thread(full.read_text)
        if old_str not in content:
            return ToolResult(content="Old string not found in file", is_error=True)
        updated = content.replace(old_str, new_str, 1)
        await asyncio.to_thread(full.write_text, updated)
        return ToolResult(
            content=f"Patched {path}",
            data={"success": True, "path": path},
        )
    except Exception as exc:
        return ToolResult(content=f"Error patching {path}: {exc}", is_error=True)


async def _delete_file(project_root: str, path: str) -> ToolResult:
    full = _resolve(project_root, path)
    if not full.exists():
        return ToolResult(
            content=f"File already deleted: {path}",
            data={"success": True, "path": path},
        )
    try:
        await asyncio.to_thread(full.unlink)
        return ToolResult(
            content=f"Deleted {path}",
            data={"success": True, "path": path},
        )
    except Exception as exc:
        return ToolResult(content=f"Error deleting {path}: {exc}", is_error=True)


async def _list_directory(
    project_root: str,
    path: str = ".",
    recursive: bool = False,
    max_depth: int = 3,
) -> ToolResult:
    full = _resolve(project_root, path)
    if not full.exists():
        return ToolResult(content=f"Directory not found: {path}", is_error=True)
    if not full.is_dir():
        return ToolResult(content=f"Not a directory: {path}", is_error=True)

    entries: List[Dict[str, Any]] = []

    def _scan(dir_path: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            for entry in sorted(dir_path.iterdir()):
                rel = str(entry.relative_to(Path(project_root).resolve()))
                entry_type = "dir" if entry.is_dir() else "file"
                size = entry.stat().st_size if entry.is_file() else 0
                entries.append({"name": rel, "type": entry_type, "size": size})
                if recursive and entry.is_dir() and not entry.name.startswith("."):
                    _scan(entry, depth + 1)
        except PermissionError:
            pass

    await asyncio.to_thread(_scan, full, 0)
    return ToolResult(
        content=json.dumps(entries, indent=2),
        data={"entries": entries},
    )


async def _glob_search(
    project_root: str, pattern: str, path: str = "."
) -> ToolResult:
    full = _resolve(project_root, path)
    try:
        matches = await asyncio.to_thread(
            lambda: [
                str(p.relative_to(Path(project_root).resolve()))
                for p in full.rglob(pattern)
            ]
        )
        return ToolResult(
            content=json.dumps(matches),
            data={"matches": matches},
        )
    except Exception as exc:
        return ToolResult(content=f"Glob error: {exc}", is_error=True)


async def _grep_search(
    project_root: str,
    pattern: str,
    path: str = ".",
    glob: Optional[str] = None,
) -> ToolResult:
    root = Path(project_root).resolve()
    search_root = _resolve(project_root, path)

    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return ToolResult(content=f"Invalid regex: {exc}", is_error=True)

    def _search() -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        if search_root.is_file():
            files = [search_root]
        else:
            files = list(search_root.rglob(glob or "*"))

        for file_path in files:
            if not file_path.is_file():
                continue
            if file_path.name.startswith("."):
                continue
            try:
                content = file_path.read_text(errors="replace")
                for i, line in enumerate(content.splitlines(), 1):
                    if regex.search(line):
                        results.append({
                            "file": str(file_path.relative_to(root)),
                            "line": i,
                            "content": line.strip(),
                        })
                        if len(results) >= 100:
                            return results
            except (PermissionError, OSError):
                continue
        return results

    matches = await asyncio.to_thread(_search)
    return ToolResult(
        content=json.dumps(matches, indent=2),
        data={"matches": matches},
    )


def create_filesystem_tools(project_root: str) -> List[Tool]:
    """Create all filesystem tools bound to a project root."""
    return [
        Tool(
            name="read_file",
            description="Read the contents of a file",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path"},
                },
                "required": ["path"],
            },
            handler=lambda path: _read_file(project_root, path),
        ),
        Tool(
            name="write_file",
            description="Write content to a file (creates parent directories)",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path"},
                    "content": {"type": "string", "description": "File content to write"},
                },
                "required": ["path", "content"],
            },
            handler=lambda path, content: _write_file(project_root, path, content),
        ),
        Tool(
            name="patch_file",
            description="Replace a string in a file (first occurrence)",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path"},
                    "old_str": {"type": "string", "description": "String to find and replace"},
                    "new_str": {"type": "string", "description": "Replacement string"},
                },
                "required": ["path", "old_str", "new_str"],
            },
            handler=lambda path, old_str, new_str: _patch_file(
                project_root, path, old_str, new_str
            ),
        ),
        Tool(
            name="delete_file",
            description="Delete a file",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path"},
                },
                "required": ["path"],
            },
            handler=lambda path: _delete_file(project_root, path),
        ),
        Tool(
            name="list_directory",
            description="List files and directories",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path", "default": "."},
                    "recursive": {"type": "boolean", "description": "List recursively", "default": False},
                    "max_depth": {"type": "integer", "description": "Max recursion depth", "default": 3},
                },
            },
            handler=lambda path=".", recursive=False, max_depth=3: _list_directory(
                project_root, path, recursive, max_depth
            ),
        ),
        Tool(
            name="glob_search",
            description="Search for files matching a glob pattern",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern (e.g. '*.py')"},
                    "path": {"type": "string", "description": "Starting directory", "default": "."},
                },
                "required": ["pattern"],
            },
            handler=lambda pattern, path=".": _glob_search(project_root, pattern, path),
        ),
        Tool(
            name="grep_search",
            description="Search file contents with regex",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search for"},
                    "path": {"type": "string", "description": "Starting path", "default": "."},
                    "glob": {"type": "string", "description": "File glob filter (e.g. '*.py')"},
                },
                "required": ["pattern"],
            },
            handler=lambda pattern, path=".", glob=None: _grep_search(
                project_root, pattern, path, glob
            ),
        ),
    ]
