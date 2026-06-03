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

"""``forktex knowledge doctor`` — drift detection for the project doc-space.

The maintenance command that surfaces problems *before* an agent reads
inconsistent knowledge. Each check is an independent function so adding the next
is one append:

  1. Filename ↔ id mismatch  (would silently shadow on a future load).
  2. Dangling ``reference`` edges (target node not in the workspace).
  3. Cycles among ``parent`` edges (the nesting axis must stay acyclic).
  4. Patch ``output_ids`` that don't resolve (broken provenance link).
  5. Retired nodes that still have inbound references (others point at a tomb).
  6. Ingested nodes whose source file changed since ingest (stale reference dump).
  7. ``KnowledgeConfig`` validates (manifest schema drift).

Output mirrors ``docs/scripts/render.py:cmd_validate`` — collect issues, print
them, return the count. The CLI maps non-zero to ``sys.exit(count)``. Issues
have a ``severity`` (``error`` blocks, ``warning`` is advisory); ``--strict``
treats warnings as exit-blocking.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from forktex_core.fractal import FractalQuery, load_node

from forktex.agent.knowledge.config import load_knowledge_config
from forktex.agent.knowledge.sources import (
    PROJECT_DOC_SPACE,
    build_knowledge_resolver,
    project_doc_space,
)

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Issue:
    """One actionable finding from a doctor check."""

    code: str
    severity: Severity
    target: str  # node id or file path
    message: str


def run_doctor(project_root: str | Path, *, composed: bool = False) -> list[Issue]:
    """Run every check against the project doc-space; return a flat issue list.

    No I/O beyond reading the doc-space (plus the composed corpus when
    ``composed=True``). Best-effort: a missing doc-space yields a single
    ``error`` (the caller can prompt the user to ``init``).

    ``composed=True`` resolves the full composed view (docs ← global ← project)
    so a reference that points at another layer (e.g. a project lesson citing a
    docs standard) is *not* flagged as dangling — only references missing from
    every layer are. This is the trustworthy mode for cross-layer doc-spaces.
    """
    root = Path(project_root)
    space = project_doc_space(root)
    if not (space / "nodes").is_dir():
        return [
            Issue(
                code="doc-space-missing",
                severity="error",
                target=str(space),
                message=(
                    f"No doc-space at {space} — run `forktex knowledge init` "
                    "to bootstrap."
                ),
            )
        ]

    composed_ids = _composed_node_ids(root) if composed else frozenset()

    issues: list[Issue] = []
    issues += _check_filename_id_match(space)
    issues += _check_dangling_references(space, extra_known=composed_ids)
    issues += _check_parent_cycles(space)
    issues += _check_patches_resolve(space)
    issues += _check_retired_inbound(space)
    issues += _check_ingested_staleness(space)
    issues += _check_config_valid(root)
    return issues


# ── individual checks ─────────────────────────────────────────────────────


def _check_filename_id_match(space: Path) -> list[Issue]:
    """A node file ``foo.md`` should hold a node whose ``id`` is ``foo`` —
    otherwise the next workspace reload silently overwrites whichever wins."""
    out: list[Issue] = []
    for path in sorted((space / "nodes").glob("*.md")):
        try:
            node = load_node(path)
        except Exception as exc:
            out.append(
                Issue(
                    code="node-unparseable",
                    severity="error",
                    target=str(path),
                    message=f"Failed to parse node: {exc!s}",
                )
            )
            continue
        if node.id != path.stem:
            out.append(
                Issue(
                    code="filename-id-mismatch",
                    severity="error",
                    target=node.id,
                    message=(
                        f"Filename '{path.stem}.md' doesn't match node id "
                        f"{node.id!r} — rename one to match the other."
                    ),
                )
            )
    return out


def _load_workspace_nodes(space: Path) -> dict[str, object]:
    """Return ``{id: Node}`` for every node in ``space`` (best-effort)."""
    nodes: dict[str, object] = {}
    for path in (space / "nodes").glob("*.md"):
        try:
            node = load_node(path)
            nodes[node.id] = node
        except Exception:
            continue
    return nodes


def _check_dangling_references(
    space: Path, *, extra_known: frozenset[str] | set[str] = frozenset()
) -> list[Issue]:
    """Flag ``reference`` edges whose target exists in no layer.

    ``extra_known`` carries ids from the composed view (docs/global) when
    running ``--composed`` — a reference that resolves there is a legitimate
    cross-layer link, not dangling.
    """
    out: list[Issue] = []
    nodes = _load_workspace_nodes(space)
    known = set(nodes) | set(extra_known)
    for node_id, node in nodes.items():
        for target in getattr(node, "references", []):
            if target not in known:
                out.append(
                    Issue(
                        code="reference-dangling",
                        severity="warning",
                        target=node_id,
                        message=(
                            f"references {target!r} which does not exist in any "
                            "layer (stale link? run without --composed to see "
                            "cross-layer refs)"
                        ),
                    )
                )
    return out


def _check_parent_cycles(space: Path) -> list[Issue]:
    """Detect cycles in the ``parent`` edge axis (must stay acyclic)."""
    out: list[Issue] = []
    nodes = _load_workspace_nodes(space)
    # Build adjacency by parent edge.
    parents: dict[str, list[str]] = {
        nid: list(getattr(n, "edges", {}).get("parent", [])) for nid, n in nodes.items()
    }
    visited: set[str] = set()
    in_path: set[str] = set()

    def _dfs(nid: str, stack: list[str]) -> None:
        if nid in in_path:
            cycle = stack[stack.index(nid) :] + [nid]
            out.append(
                Issue(
                    code="parent-cycle",
                    severity="error",
                    target=cycle[0],
                    message=f"parent-edge cycle: {' → '.join(cycle)}",
                )
            )
            return
        if nid in visited:
            return
        visited.add(nid)
        in_path.add(nid)
        for tgt in parents.get(nid, []):
            if tgt in parents:
                _dfs(tgt, stack + [nid])
        in_path.discard(nid)

    for root_id in parents:
        if root_id not in visited:
            _dfs(root_id, [])
    return out


def _check_patches_resolve(space: Path) -> list[Issue]:
    """Every patch's ``output_ids`` should resolve to existing nodes."""
    out: list[Issue] = []
    from forktex_core.fractal.io import load_patch

    nodes = set(_load_workspace_nodes(space))
    for path in (space / "patches").glob("*.md"):
        try:
            patch = load_patch(path)
        except Exception as exc:
            out.append(
                Issue(
                    code="patch-unparseable",
                    severity="error",
                    target=str(path),
                    message=f"Failed to parse patch: {exc!s}",
                )
            )
            continue
        missing = [oid for oid in patch.output_ids if oid not in nodes]
        if missing:
            out.append(
                Issue(
                    code="patch-output-missing",
                    severity="warning",
                    target=patch.id,
                    message=(
                        f"output_ids {missing} not in doc-space "
                        "(node retired then deleted, or stale provenance?)"
                    ),
                )
            )
    return out


def _check_retired_inbound(space: Path) -> list[Issue]:
    """A retired node with inbound references is silently broken for readers."""
    out: list[Issue] = []
    nodes = _load_workspace_nodes(space)
    retired_ids = {
        nid for nid, n in nodes.items() if getattr(n, "status", None) == "retired"
    }
    if not retired_ids:
        return out
    for nid, n in nodes.items():
        if nid in retired_ids:
            continue
        for target in getattr(n, "references", []):
            if target in retired_ids:
                out.append(
                    Issue(
                        code="retired-inbound",
                        severity="warning",
                        target=nid,
                        message=(
                            f"references retired node {target!r} — either "
                            "re-recycle to point elsewhere or unset --replace-refs."
                        ),
                    )
                )
    return out


def _check_ingested_staleness(space: Path) -> list[Issue]:
    """Flag ingested nodes whose source file changed since ingest.

    ``forktex knowledge ingest`` records each source's content hash (keyed by the
    same relpaths as ``source_ids``) plus the workspace root it resolved against on
    the provenance patch. Re-hash the source and warn on mismatch so a stale
    reference dump (e.g. an ``AGENTS.md`` edited after ingest) is surfaced — the fix
    is to re-run ``forktex knowledge ingest``. Best-effort: a moved/unreadable source
    is skipped (not every node is an ingest, and absence isn't staleness).
    """
    import hashlib

    from forktex_core.fractal.io import load_patch

    out: list[Issue] = []
    for path in (space / "patches").glob("*.md"):
        try:
            patch = load_patch(path)
        except Exception:
            continue  # unparseable patches are already reported by _check_patches_resolve
        hashes = getattr(patch, "source_hashes", None)
        source_root = getattr(patch, "source_root", None)
        if not hashes or not source_root:
            continue
        target = patch.output_ids[0] if patch.output_ids else patch.id
        for rel, expected in hashes.items():
            src = Path(source_root) / rel
            if not src.is_file():
                continue
            try:
                current = hashlib.sha256(
                    src.read_text(encoding="utf-8").encode("utf-8")
                ).hexdigest()
            except OSError, UnicodeDecodeError:
                continue
            if current != expected:
                out.append(
                    Issue(
                        code="reference-stale",
                        severity="warning",
                        target=target,
                        message=(
                            f"source {rel!r} changed since ingest — re-run "
                            "`forktex knowledge ingest` to refresh this node"
                        ),
                    )
                )
    return out


def _check_config_valid(root: Path) -> list[Issue]:
    """Manifest ``[knowledge]`` block validates and (if set) declares known adapters."""
    out: list[Issue] = []
    try:
        cfg = load_knowledge_config(root)
    except Exception as exc:  # extremely defensive — config loader catches most
        out.append(
            Issue(
                code="config-invalid",
                severity="error",
                target="forktex.json",
                message=f"Could not load KnowledgeConfig: {exc!s}",
            )
        )
        return out
    if cfg.layers:
        from forktex.agent.knowledge.sources import known_adapters

        known = known_adapters()
        for layer in cfg.layers:
            if layer.adapter not in known:
                out.append(
                    Issue(
                        code="config-unknown-adapter",
                        severity="error",
                        target=f"knowledge.layers[{layer.name}]",
                        message=(
                            f"adapter {layer.adapter!r} is not registered — "
                            f"valid: {sorted(known)}"
                        ),
                    )
                )
    return out


# ── presentation ──────────────────────────────────────────────────────────


def format_report(issues: list[Issue], *, project_root: Path | None = None) -> str:
    """Plain-text rendering — what the CLI prints. Stable for scripting."""
    if not issues:
        loc = f" ({project_root}/{PROJECT_DOC_SPACE})" if project_root else ""
        return f"knowledge doctor: 0 issues{loc}.\n"
    by_sev = {"error": [], "warning": []}
    for issue in issues:
        by_sev[issue.severity].append(issue)
    lines = [
        f"knowledge doctor: {len(by_sev['error'])} error(s), "
        f"{len(by_sev['warning'])} warning(s).",
        "",
    ]
    for sev in ("error", "warning"):
        for issue in by_sev[sev]:
            lines.append(f"  [{sev}] {issue.code}  {issue.target}")
            lines.append(f"        {issue.message}")
    return "\n".join(lines) + "\n"


def exit_code(issues: list[Issue], *, strict: bool) -> int:
    """Exit code from an issue list. Errors always block; ``--strict`` blocks on warnings too."""
    if any(i.severity == "error" for i in issues):
        return 1
    if strict and issues:
        return 1
    return 0


def _composed_node_ids(root: Path) -> frozenset[str]:
    """All node ids in the composed view (docs ← global ← project).

    Best-effort: returns ``frozenset()`` if the corpus can't be resolved (e.g.
    ``forktex-core[fractal]`` absent or no ``$FORKTEX_DOCS``) — composed mode
    then degrades to project-only, never crashing the doctor.
    """
    try:
        from forktex.agent.knowledge.sources import COMPOSED_NAMESPACE

        resolver = build_knowledge_resolver(project_path=project_doc_space(root))
        if COMPOSED_NAMESPACE not in resolver.namespaces():
            return frozenset()
        nodes = FractalQuery(resolver).list_nodes(COMPOSED_NAMESPACE).nodes
        return frozenset(n.id for n in nodes)
    except Exception:
        return frozenset()


__all__ = [
    "Issue",
    "exit_code",
    "format_report",
    "run_doctor",
]
