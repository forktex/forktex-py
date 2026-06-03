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
  ``<project>/.forktex/cache/manual/manual_bundle.json`` (if `forktex arch
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
_KNOWLEDGE_LIMIT = 40


def _workspace_section(root: Path) -> str | None:
    """State the working root + its top-level entries.

    Without this, agents guess at paths — e.g. calling ``list_directory("docs")``
    when the root *is* the docs project, then failing and never recovering. Tool
    paths are relative to the root, so naming the layout up front anchors them.
    """
    try:
        entries = sorted(
            p.name + ("/" if p.is_dir() else "")
            for p in root.iterdir()
            if not p.name.startswith(".")
        )
    except OSError:
        return None
    if not entries:
        return None
    listing = ", ".join(entries[:50])
    if len(entries) > 50:
        listing += ", …"
    return (
        "\n\n## Workspace\n"
        f"You are operating in the project rooted at `{root.name}/`. "
        "All tool file paths are relative to this root — use `.` for the root "
        "itself (there is no nested directory named after the project).\n"
        f"Top-level entries: {listing}"
    )


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

    workspace = _workspace_section(root)
    if workspace:
        parts.append(workspace)

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
            "\n\n[hint] Run `forktex arch build` to enrich this "
            "context with rules + concepts derived from the project graph."
        )

    knowledge = _knowledge_section(root)
    if knowledge:
        parts.append(knowledge)

    composed = "\n".join(parts)
    return _truncate(composed, max_chars)


# ── private helpers ───────────────────────────────────────────────────────


#: Tag convention: nodes carrying this tag are *always* injected (the must-obey
#: standards), with their summary, ahead of the pull-on-demand index. No core
#: ``Node`` field — pinning is runtime policy expressed as a tag.
PINNED_TAG = "pinned"

#: Char budget for the whole knowledge section, so pinned + index stay bounded
#: (mirrors the prompt-level ``max_chars`` discipline at the section level).
_KNOWLEDGE_CHAR_BUDGET = 4_000

#: Statuses filtered from the grounded view at the read seam. Rolled-up nodes
#: are folded into their parent's summary; retired nodes are superseded but
#: kept on disk for audit. Both remain resolvable by ``knowledge show <id>``.
_HIDDEN_STATUSES: frozenset[str] = frozenset({"rolled-up", "retired"})


def _overlay_node_ids(query: Any, layer_names: list[str]) -> set[str]:
    """Node ids from the overlay layers — everything composed on top of the base
    layer (the first; ``docs`` by default). The grounding index ranks these
    ahead of the base corpus so a growing global catalog can't starve the
    agent's own project knowledge out of a bounded prompt.
    """
    ids: set[str] = set()
    for namespace in layer_names[1:]:
        try:
            ids.update(node.id for node in query.list_nodes(namespace).nodes)
        except Exception:
            continue
    return ids


def _knowledge_section(root: Path) -> str | None:
    """The always-inject pinned standards + a bounded index of the live graph.

    Best-effort: returns ``None`` if ``forktex-core[fractal]`` isn't installed or
    no knowledge source resolves — never crashes the chat boot. Two tiers, mirroring
    how context is actually managed: **pinned** nodes (tag convention) are injected
    in full-summary with freshness — the always-loaded layer — while everything else
    is a cheap id/title *index* the agent pulls from on demand via the knowledge
    tools / ``forktex knowledge``. Bounded by :data:`_KNOWLEDGE_CHAR_BUDGET`.
    """
    try:
        from forktex_core.fractal import FractalQuery

        from forktex.agent.knowledge.config import load_knowledge_config
        from forktex.agent.knowledge.sources import (
            COMPOSED_NAMESPACE,
            build_knowledge_resolver,
            project_doc_space,
        )
    except Exception:
        return None
    try:
        cfg = load_knowledge_config(root)
        # Honour project-declared layers (target-agnostic mode) when present;
        # otherwise fall back to the default global-docs + project-overlay.
        if cfg.layers:
            resolver = build_knowledge_resolver(config=cfg)
        else:
            resolver = build_knowledge_resolver(project_path=project_doc_space(root))
        if COMPOSED_NAMESPACE not in resolver.namespaces():
            return None
        query = FractalQuery(resolver)
        nodes = query.list_nodes(COMPOSED_NAMESPACE).nodes
    except Exception:
        return None
    if not nodes:
        return None

    layer_names = [ns for ns in resolver.namespaces() if ns != COMPOSED_NAMESPACE]
    overlay_ids = _overlay_node_ids(query, layer_names)

    # All runtime policy reads from KnowledgeConfig — see manifest/models.py.
    # Defaults preserve the module-level constants below (PINNED_TAG, …).
    pinned_tag = cfg.pinned_tag
    hidden = frozenset(cfg.retired_statuses)
    char_budget = cfg.grounding_char_budget
    index_limit = cfg.knowledge_limit

    visible = [n for n in nodes if n.status not in hidden]
    pinned = [n for n in visible if pinned_tag in n.tags]
    others = [n for n in visible if pinned_tag not in n.tags]

    lines = [
        "\n\n## Knowledge graph (forktex)\n",
        "A live knowledge graph of engineering principles + project knowledge is "
        "available. **Before implementing, search it** for the relevant standard / "
        "archetype / blueprint and follow it. Query via the `knowledge_search` / "
        '`knowledge_show` tools, or `forktex knowledge search "<query>"`. When you reach '
        "a non-obvious decision, `knowledge_recycle` it so it compounds across sessions.\n",
    ]

    if pinned:
        lines.append("**Always follow these (pinned):**")
        for node in sorted(pinned, key=lambda s: s.id):
            fresh = f" _(updated {node.updated_at})_" if node.updated_at else ""
            detail = f" — {node.summary}" if node.summary else f" — {node.title}"
            lines.append(f"- `{node.id}` [{node.kind}]{detail}{fresh}")
        lines.append("")

    lines.append("Indexed nodes (pull bodies on demand):")
    overlay_first = sorted(others, key=lambda s: (s.id not in overlay_ids, s.id))
    for node in overlay_first[:index_limit]:
        lines.append(f"- `{node.id}` [{node.kind}] — {node.title}")

    section = "\n".join(lines)
    if len(section) > char_budget:
        section = section[:char_budget].rstrip() + "\n- … _(truncated; search for more)_"
    return section


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
    """Load ``<root>/.forktex/cache/manual/manual_bundle.json`` if present."""
    from forktex.substrate import paths as _sub

    bundle_path = _sub.manual_dir(root) / "manual_bundle.json"
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
