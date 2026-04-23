"""
forktex.agent.tools.bash - Command execution tools with streaming.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

from forktex.agent.tools.base import Tool, ToolResult


async def _bash_execute(
    project_root: str,
    command: str,
    timeout: int = 120,
    cwd: Optional[str] = None,
) -> ToolResult:
    """Execute a shell command and return stdout/stderr/exit_code."""
    work_dir = cwd or project_root

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            stdout = stdout_bytes.decode(errors="replace")
            stderr = stderr_bytes.decode(errors="replace")
            exit_code = proc.returncode or 0
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            await proc.communicate()
            return ToolResult(
                content=f"Command timed out after {timeout}s",
                is_error=True,
                data={"stdout": "", "stderr": "", "exit_code": -1, "timed_out": True},
            )

        output = stdout
        if stderr:
            output += f"\n[stderr]\n{stderr}"

        return ToolResult(
            content=output,
            is_error=exit_code != 0,
            data={
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
            },
        )
    except Exception as exc:
        return ToolResult(content=f"Execution error: {exc}", is_error=True)


def create_bash_tools(project_root: str) -> List[Tool]:
    """Create bash execution tools bound to a project root."""
    return [
        Tool(
            name="bash_execute",
            description="Execute a shell command and return stdout, stderr, and exit code",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds",
                        "default": 120,
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory (relative to project root)",
                    },
                },
                "required": ["command"],
            },
            handler=lambda command, timeout=120, cwd=None: _bash_execute(
                project_root, command, timeout, cwd
            ),
        ),
    ]
