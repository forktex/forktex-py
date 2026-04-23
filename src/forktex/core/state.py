"""
forktex.core.state - .forktex/ hidden directory and JSON state persistence.

Ported from tools/state.py with additions for conversation history.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from forktex.core.paths import FORKTEX_DIRNAME, resolve_path


STATE_DIR = FORKTEX_DIRNAME

_state_lock = asyncio.Lock()


class StateManager:
    """Manages .forktex/ hidden directory for state persistence."""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = resolve_path(project_root)
        self.state_dir = self.project_root / STATE_DIR

    async def ensure_dir(self) -> Path:
        """Ensure .forktex/ exists and is in .gitignore."""
        self.state_dir.mkdir(parents=True, exist_ok=True)

        gitignore_path = self.project_root / ".gitignore"
        ignore_entry = f"{STATE_DIR}/"

        if gitignore_path.exists():
            async with aiofiles.open(gitignore_path, "r", encoding="utf-8") as f:
                content = await f.read()
            if ignore_entry not in content:
                async with aiofiles.open(gitignore_path, "a", encoding="utf-8") as f:
                    await f.write(f"\n# Forktex state\n{ignore_entry}\n")
        else:
            async with aiofiles.open(gitignore_path, "w", encoding="utf-8") as f:
                await f.write(f"# Forktex state\n{ignore_entry}\n")

        return self.state_dir

    async def read_json(self, filename: str) -> Optional[Dict[str, Any]]:
        """Read a JSON state file."""
        await self.ensure_dir()
        state_file = self.state_dir / filename

        if not state_file.exists():
            return None

        async with aiofiles.open(state_file, "r", encoding="utf-8") as f:
            content = await f.read()
        return json.loads(content)

    async def write_json(self, filename: str, data: Any) -> None:
        """Atomic write of JSON data to state file."""
        await self.ensure_dir()
        state_file = self.state_dir / filename
        temp_file = state_file.with_suffix(".tmp")

        async with _state_lock:
            async with aiofiles.open(temp_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, indent=2, default=str))
            await asyncio.to_thread(temp_file.replace, state_file)

    async def save_conversation(
        self, session_id: str, history: List[Dict[str, str]]
    ) -> None:
        """Save conversation history for a session."""
        await self.write_json(
            f"conversation_{session_id}.json",
            {
                "session_id": session_id,
                "history": history,
            },
        )

    async def load_conversation(
        self, session_id: str
    ) -> Optional[List[Dict[str, str]]]:
        """Load conversation history for a session."""
        data = await self.read_json(f"conversation_{session_id}.json")
        if data:
            return data.get("history", [])
        return None

    # ── Project-level config (.forktex/config.json) ──

    CONFIG_FILENAME = "config.json"

    async def read_config(self) -> Dict[str, Any]:
        """Read .forktex/config.json, returning {} if it doesn't exist."""
        data = await self.read_json(self.CONFIG_FILENAME)
        return data if isinstance(data, dict) else {}

    async def write_config(self, data: Dict[str, Any]) -> None:
        """Atomically write .forktex/config.json."""
        await self.write_json(self.CONFIG_FILENAME, data)

    async def get_config_value(self, key: str) -> Optional[str]:
        """Get a single value from project config."""
        cfg = await self.read_config()
        return cfg.get(key)

    async def set_config_value(self, key: str, value: str) -> None:
        """Set a single value in project config."""
        cfg = await self.read_config()
        cfg[key] = value
        await self.write_config(cfg)
