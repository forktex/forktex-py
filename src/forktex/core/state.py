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
forktex.core.state - .forktex/ hidden directory and JSON state persistence.

Ported from tools/state.py with additions for conversation history.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from forktex_cloud import paths as _cloud_paths

from forktex.core.paths import resolve_path


STATE_DIR = _cloud_paths.PROJECT_DIRNAME

_state_lock = asyncio.Lock()


class StateManager:
    """Manages .forktex/ hidden directory for state persistence."""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = resolve_path(project_root)
        self.state_dir = self.project_root / STATE_DIR

    async def ensure_dir(self) -> Path:
        """Ensure the canonical ``.forktex/`` dir, gitignore, and schema version."""
        _cloud_paths.ensure_project_dirs(self.project_root)
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
        from forktex.graph.io_proxy import tracked_write_async

        await self.ensure_dir()
        state_file = self.state_dir / filename
        async with _state_lock:
            await tracked_write_async(
                state_file,
                json.dumps(data, indent=2, default=str),
                kind="state",
                writer="forktex.core.state",
            )

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
