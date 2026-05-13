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

"""Grounding helpers for the chat agent's system prompt.

Today the bare ``forktex`` REPL boots the agent with a hardcoded persona
string. This module composes a richer system prompt by injecting:

- the project's ``AGENTS.md`` (root or ``docs/AGENTS.md``) — verbatim
- the cached ``manual@agents`` bundle from
  ``<project>/.forktex/manual/manual_bundle.json`` (if `forktex manual
  build` has been run): rules, top concepts, a small set of few-shots.

The output is a single string, length-capped, that callers append to
or replace their base system prompt with.

Pure-ish: reads files, no network, no graph build at the boot path
(the bundle is read from disk if present; not generated here).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_BASE = (
    "You are Forktex, a development assistant. You have access to local "
    "tools for reading and writing files, running bash commands, git "
    "operations, and the project graph. Use them to help the user with "
    "their development tasks."
)

# Total cap on the composed prompt. Keeps token use bounded; truncation
# is appended with a ``[truncated]`` marker so the caller knows it
# happened.
DEFAULT_MAX_CHARS = 20_000

# Per-section caps so a long AGENTS.md doesn't crowd out the bundle.
_AGENTS_MD_CAP = 8_000
_RULES_LIMIT = 30
_CONCEPTS_LIMIT = 20
_FEW_SHOTS_LIMIT = 8


def build_system_prompt(
    project_root: str | Path,
    *,
    base_prompt: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """Compose the chat agent's system prompt with project grounding.

    *project_root* is the directory the user is running ``forktex`` from
    (or whatever the chat command resolved). *base_prompt* overrides
    :data:`DEFAULT_BASE`. *max_chars* caps the final string.

    Returns a non-empty string; falls back to *base_prompt* alone when
    no grounding sources are available.
    """
    root = Path(project_root)
    parts: list[str] = [base_prompt or DEFAULT_BASE]

    agents_md = _load_agents_md(root)
    if agents_md:
        parts.append("\n\n## Project Conventions (from AGENTS.md)\n")
        parts.append(_truncate(agents_md, _AGENTS_MD_CAP))

    bundle = _load_cached_manual_bundle(root)
    if bundle:
        rules = _as_list(bundle.get("rules"))
        if rules:
            parts.append("\n\n## Project Rules\n")
            parts.extend(f"- {r}" for r in rules[:_RULES_LIMIT])

        concepts = _as_list(bundle.get("concepts"))
        if concepts:
            parts.append("\n\n## Key Concepts (top by graph degree)\n")
            for c in concepts[:_CONCEPTS_LIMIT]:
                if not isinstance(c, dict):
                    continue
                name = c.get("name", "?")
                kind = c.get("kind", "")
                summary = c.get("summary", "")
                parts.append(f"- **{name}** ({kind}): {summary}")

        few_shots = _as_list(bundle.get("few_shots"))
        if few_shots:
            parts.append("\n\n## Common Tasks\n")
            for f in few_shots[:_FEW_SHOTS_LIMIT]:
                if not isinstance(f, dict):
                    continue
                task = f.get("task", "")
                cmd = f.get("command", "")
                if cmd:
                    parts.append(f"- {task}: `{cmd}`")
                else:
                    parts.append(f"- {task}")
    else:
        # Hint without forcing a heavy build at boot — let the user
        # opt-in to the richer grounding when ready.
        parts.append(
            "\n\n[hint] Run `forktex manual build` to enrich this "
            "context with rules + concepts derived from the project graph."
        )

    composed = "\n".join(parts)
    return _truncate(composed, max_chars)


# ── private helpers ───────────────────────────────────────────────────────


def _load_agents_md(root: Path) -> str | None:
    """Load AGENTS.md from project root or ``docs/AGENTS.md``."""
    for candidate in (root / "AGENTS.md", root / "docs" / "AGENTS.md"):
        if candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8")
            except OSError:
                return None
    return None


def _load_cached_manual_bundle(root: Path) -> dict[str, Any] | None:
    """Load ``<root>/.forktex/manual/manual_bundle.json`` if present."""
    bundle_path = root / ".forktex" / "manual" / "manual_bundle.json"
    if not bundle_path.is_file():
        return None
    try:
        data = json.loads(bundle_path.read_text(encoding="utf-8"))
    except Exception:
        # Any read or parse failure → no bundle. Don't crash the chat
        # boot just because the cached file is corrupt.
        return None
    if not isinstance(data, dict):
        return None
    return data


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    marker = "\n\n[truncated]"
    return text[: max(0, limit - len(marker))] + marker


__all__ = ["DEFAULT_BASE", "DEFAULT_MAX_CHARS", "build_system_prompt"]
