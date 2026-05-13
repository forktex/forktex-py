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

"""forktex.agent.state — Agent state persistence to .forktex/agents/.

Stores agent process history as JSONL files for later inspection and
resume. Hardened per ``SECURITY.md §G``:

* Each ``{agent_id}.jsonl`` is chmod'd to ``0o600`` after every append
  (POSIX). Tool-call records can contain code, prompts, and command
  output — keep them user-only.
* :class:`AgentStateStore` accepts ``redact_patterns``: a list of
  regexes whose matches are masked before the entry is serialised.
  Default redactions cover common credential shapes (``ftx-*`` API
  keys, JWT-shaped strings, ``Bearer …`` headers, ``-----BEGIN`` PEM
  blocks). Customers can extend the list when integrating with internal
  secret formats.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Pattern

from forktex_cloud import paths as _cloud_paths


# Default redactions — conservative and meant to be a safety net, not the
# primary control. Real secrets should never be in agent stdout in the
# first place; these patterns catch the cases where a tool surfaces one
# unexpectedly.
_DEFAULT_REDACTIONS: tuple[Pattern[str], ...] = (
    re.compile(r"ftx-[A-Za-z0-9_\-]{16,}"),  # ForkTex API keys
    re.compile(
        r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"
    ),  # JWTs
    re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.=+/]{16,}", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----", re.DOTALL),
    re.compile(r"\b(?:sk|pk|rk)[_-][A-Za-z0-9_\-]{16,}\b"),  # Stripe-shape keys
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"),  # GitHub tokens
)
_REDACTION_PLACEHOLDER = "***REDACTED***"


def _redact_string(text: str, patterns: Iterable[Pattern[str]]) -> str:
    redacted = text
    for pat in patterns:
        redacted = pat.sub(_REDACTION_PLACEHOLDER, redacted)
    return redacted


def _redact_obj(obj: Any, patterns: Iterable[Pattern[str]]) -> Any:
    """Recursively walk *obj*, redacting matches in every string leaf."""
    if isinstance(obj, str):
        return _redact_string(obj, patterns)
    if isinstance(obj, dict):
        return {k: _redact_obj(v, patterns) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_obj(v, patterns) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_redact_obj(v, patterns) for v in obj)
    return obj


class AgentStateStore:
    """Persists agent process metadata to ``.forktex/agents/history/``.

    Each agent gets a JSONL file: ``{agent_id}.jsonl``. Each line is a
    state snapshot (status change, tool call, etc). Files are written
    with ``0o600`` permissions on POSIX and run through the redaction
    patterns before serialisation.
    """

    def __init__(
        self,
        project_root: str,
        *,
        redact_patterns: Optional[Iterable[str | Pattern[str]]] = None,
        use_default_redactions: bool = True,
    ) -> None:
        self._root = _cloud_paths.agents_history_dir(Path(project_root))
        compiled: list[Pattern[str]] = (
            list(_DEFAULT_REDACTIONS) if use_default_redactions else []
        )
        for pat in redact_patterns or ():
            compiled.append(re.compile(pat) if isinstance(pat, str) else pat)
        self._redact_patterns: tuple[Pattern[str], ...] = tuple(compiled)

    def _ensure_dir(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def _agent_path(self, agent_id: str) -> Path:
        return self._root / f"{agent_id}.jsonl"

    def _harden_perms(self, path: Path) -> None:
        if sys.platform == "win32":  # pragma: no cover — POSIX only
            return
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def append(self, agent_id: str, entry: Dict[str, Any]) -> None:
        """Append a state entry for an agent (redacted + 0o600)."""
        from forktex.graph.io_proxy import tracked_append

        self._ensure_dir()
        path = self._agent_path(agent_id)
        redacted = _redact_obj(entry, self._redact_patterns)
        tracked_append(
            path,
            json.dumps(redacted, default=str),
            kind="agent_history",
            writer="forktex.agent.state",
        )
        self._harden_perms(path)

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
