"""forktex.agent.state — Agent state persistence to .forktex/agents/.

Stores agent process history as JSONL files for later inspection and resume.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class AgentStateStore:
    """Persists agent process metadata to .forktex/agents/history/.

    Each agent gets a JSONL file: {agent_id}.jsonl
    Each line is a state snapshot (status change, tool call, etc).
    """

    def __init__(self, project_root: str) -> None:
        self._root = Path(project_root) / ".forktex" / "agents" / "history"

    def _ensure_dir(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def _agent_path(self, agent_id: str) -> Path:
        return self._root / f"{agent_id}.jsonl"

    def append(self, agent_id: str, entry: Dict[str, Any]) -> None:
        """Append a state entry for an agent."""
        self._ensure_dir()
        path = self._agent_path(agent_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def save_snapshot(self, agent_data: Dict[str, Any]) -> None:
        """Save a full agent snapshot (usually on status change)."""
        agent_id = agent_data.get("id", "unknown")
        self.append(agent_id, agent_data)

    def load_history(self, agent_id: str) -> List[Dict[str, Any]]:
        """Load all state entries for an agent."""
        path = self._agent_path(agent_id)
        if not path.exists():
            return []

        entries: List[Dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries

    def load_latest(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Load the most recent state entry for an agent."""
        entries = self.load_history(agent_id)
        return entries[-1] if entries else None

    def list_agents(self) -> List[str]:
        """List all agent IDs with stored history."""
        if not self._root.exists():
            return []
        return [p.stem for p in self._root.glob("*.jsonl")]

    def delete(self, agent_id: str) -> None:
        """Delete history for an agent."""
        path = self._agent_path(agent_id)
        if path.exists():
            path.unlink()
