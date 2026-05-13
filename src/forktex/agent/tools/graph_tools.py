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

"""Graph-aware tools the LLM agent can call.

Each tool is a thin shim over :mod:`forktex.graph.query` primitives and
shares an in-process :class:`forktex.graph.models.Graph` cache via
``session_graph`` so a single agent session pays the build cost once.

The 12 tools here are declared as data — :class:`_ToolSpec` records —
and assembled into Click-style ``Tool`` objects by a single
:func:`create_graph_tools` factory. Adding a tool means adding a row to
``_TOOL_SPECS``; no more 30-line handler closure per query.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from forktex.agent.tools.base import Tool, ToolResult
from forktex.graph.models import Graph
from forktex.graph.query import (
    ecosystem_fsd_matrix,
    files_touched_recently,
    find_modules,
    find_package_by_path,
    fsd_level_of_package,
    get_project_metadata,
    importers_of,
    imports_of_module,
    list_domains,
    list_modules_in_domain,
    list_packages,
    session_graph,
    validate_path,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _root(project_root: str | Path) -> Path:
    return Path(project_root).resolve()


def _summarise(records: list[Any], cap: int = 20) -> str:
    if not records:
        return "(empty)"
    head = records[:cap]
    extra = "" if len(records) <= cap else f"\n… +{len(records) - cap} more"
    lines = [
        getattr(r, "rel_path", None) or getattr(r, "name", None) or str(r) for r in head
    ]
    return "\n".join(f"- {ln}" for ln in lines if ln) + extra


def _schema(properties: dict[str, dict], required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
    }


_NO_ARGS = _schema({})


# ── Per-query bodies (graph + kwargs → ToolResult) ───────────────────────
#
# Each body returns ``ToolResult`` directly so we can keep the special
# formatting per tool (banner for ``graph_summary``, "no package" hint
# for ``find_package``, etc.) without forcing a generic shape.

ToolBody = Callable[..., Awaitable[ToolResult]]


def _summary_body(project_root: Path) -> ToolBody:
    async def _h() -> ToolResult:
        meta = get_project_metadata(session_graph(project_root))
        body = (
            f"{meta.name} @ {meta.root}\n"
            f"  packages={meta.package_count} domains={meta.domain_count} "
            f"modules={meta.module_count} libraries={meta.library_count}\n"
            f"  fsd_level={meta.fsd_level} has_makefile={meta.has_makefile}"
        )
        return ToolResult(content=body, data=meta.model_dump(mode="json"))

    return _h


def _list_packages_body(project_root: Path) -> ToolBody:
    async def _h() -> ToolResult:
        pkgs = list_packages(session_graph(project_root))
        lines = [
            f"- {p.name} ({p.rel_path})  fsd={p.fsd_level}  domains={p.domain_count}"
            for p in pkgs
        ]
        return ToolResult(
            content="\n".join(lines) if lines else "(no packages)",
            data={"packages": [p.model_dump(mode="json") for p in pkgs]},
        )

    return _h


def _find_package_body(project_root: Path) -> ToolBody:
    async def _h(rel_path: str = ".") -> ToolResult:
        match = find_package_by_path(session_graph(project_root), rel_path)
        if match is None:
            return ToolResult(content=f"no package contains {rel_path!r}")
        return ToolResult(
            content=f"{rel_path!r} → package {match.name} ({match.rel_path})",
            data=match.model_dump(mode="json"),
        )

    return _h


def _list_domains_body(project_root: Path) -> ToolBody:
    async def _h(package_id: str | None = None) -> ToolResult:
        domains = list_domains(session_graph(project_root), package_id=package_id)
        lines = [
            f"- {d.name} ({d.rel_path})  modules={d.module_count}" for d in domains
        ]
        return ToolResult(
            content="\n".join(lines) if lines else "(no domains)",
            data={"domains": [d.model_dump(mode="json") for d in domains]},
        )

    return _h


def _list_modules_body(project_root: Path) -> ToolBody:
    async def _h(domain_id: str) -> ToolResult:
        modules = list_modules_in_domain(session_graph(project_root), domain_id)
        return ToolResult(
            content=_summarise(modules),
            data={"modules": [m.model_dump(mode="json") for m in modules]},
        )

    return _h


def _find_modules_body(project_root: Path) -> ToolBody:
    async def _h(name_pattern: str) -> ToolResult:
        matches = find_modules(session_graph(project_root), name_pattern)
        return ToolResult(
            content=_summarise(matches),
            data={"matches": [m.model_dump(mode="json") for m in matches]},
        )

    return _h


def _modules_in_package(graph: Graph, package_id: str) -> list[str]:
    """Walk domain → module under *package_id*; return module ids."""
    out: list[str] = []
    for n in graph.by_kind("module"):
        for e in graph.in_edges(n.id, kind="contains"):
            domain = graph.node(e.src_id)
            if domain is None or domain.kind != "domain":
                continue
            for ee in graph.in_edges(domain.id, kind="contains"):
                pkg = graph.node(ee.src_id)
                if pkg is not None and pkg.id == package_id:
                    out.append(n.id)
                    break
    return out


def _package_imports_body(project_root: Path) -> ToolBody:
    async def _h(package_id: str) -> ToolResult:
        graph = session_graph(project_root)
        seen: dict[str, str] = {}
        for mid in _modules_in_package(graph, package_id):
            for ie in imports_of_module(graph, mid):
                seen[ie.target_name] = ie.target_kind
        rows = sorted(seen.items())
        lines = [f"- {name} ({kind})" for name, kind in rows]
        return ToolResult(
            content="\n".join(lines) if lines else "(no imports)",
            data={"imports": [{"target": n, "kind": k} for n, k in rows]},
        )

    return _h


def _find_importers_body(project_root: Path) -> ToolBody:
    async def _h(target: str) -> ToolResult:
        edges = importers_of(session_graph(project_root), target)
        return ToolResult(
            content=_summarise(
                [type("R", (), {"name": e.src_module})() for e in edges]
            ),
            data={
                "importers": [
                    {"src": e.src_module, "kind": e.target_kind} for e in edges
                ]
            },
        )

    return _h


def _fsd_status_body(project_root: Path) -> ToolBody:
    async def _h(package_id: str | None = None) -> ToolResult:
        statuses = fsd_level_of_package(
            session_graph(project_root), package_id=package_id
        )
        lines = [
            f"- {s.package_name} ({s.rel_path})  fsd={s.fsd_level}  "
            f"makefile={s.has_makefile}  targets={s.target_count}"
            for s in statuses
        ]
        return ToolResult(
            content="\n".join(lines) if lines else "(no packages)",
            data={"statuses": [s.model_dump(mode="json") for s in statuses]},
        )

    return _h


def _recent_writes_body(project_root: Path) -> ToolBody:
    async def _h(hours: int = 24) -> ToolResult:
        touches = files_touched_recently(project_root, hours=hours)
        lines = [
            f"- {t.last_touched_at}  {t.rel_path}  ({t.kind} via {t.writer or '?'})"
            for t in touches[:50]
        ]
        return ToolResult(
            content="\n".join(lines) if lines else "(no writes in window)",
            data={"touches": [t.model_dump(mode="json") for t in touches]},
        )

    return _h


def _validate_path_body(_project_root: Path) -> ToolBody:
    async def _h(rel_path: str, scope: str = "project") -> ToolResult:
        match = validate_path(rel_path, scope=scope)
        verdict = "✓ allowed" if match.ok else "✗ rejected"
        body = (
            f"{verdict}: {rel_path}\n"
            f"  pattern={match.pattern}\n"
            f"  purpose={match.purpose}\n"
            f"  sensitivity={match.sensitivity}\n"
            f"  reason={match.reason}"
        )
        return ToolResult(content=body, data=match.model_dump(mode="json"))

    return _h


def _ecosystem_matrix_body(project_root: Path) -> ToolBody:
    async def _h(
        base_dir: str | None = None, include_nested: bool = False
    ) -> ToolResult:
        base = Path(base_dir).resolve() if base_dir else project_root.parent
        rows = ecosystem_fsd_matrix(base, include_nested=include_nested)
        lines = [
            f"- {r.project_name:20s} fsd={r.fsd_level}  "
            f"pkgs={r.package_count} domains={r.domain_count} "
            f"modules={r.module_count}"
            for r in rows
        ]
        return ToolResult(
            content="\n".join(lines) if lines else "(no projects)",
            data={"rows": [r.model_dump(mode="json") for r in rows]},
        )

    return _h


# ── Tool catalogue ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _ToolSpec:
    """Declarative shape of one graph-aware tool.

    ``body_factory`` takes the resolved project root and returns the
    async handler. Keeping this as a factory lets us bind the root once
    per ``ToolServer`` instance.
    """

    name: str
    description: str
    parameters: dict
    body_factory: Callable[[Path], ToolBody]


_TOOL_SPECS: tuple[_ToolSpec, ...] = (
    _ToolSpec(
        name="graph_summary",
        description=(
            "Overview of this project's graph: package, domain, module, "
            "library counts plus the recorded FSD level. Cheap; safe to call first."
        ),
        parameters=_NO_ARGS,
        body_factory=_summary_body,
    ),
    _ToolSpec(
        name="list_packages",
        description=(
            "Names, rel_paths, and FSD levels for every forktex package "
            "in this project. Use to learn the project shape."
        ),
        parameters=_NO_ARGS,
        body_factory=_list_packages_body,
    ),
    _ToolSpec(
        name="find_package",
        description=(
            "Given a relative path, return the package whose tree contains it. "
            "Use when you need to know which package a file belongs to."
        ),
        parameters=_schema(
            {
                "rel_path": {
                    "type": "string",
                    "description": "Path relative to project root.",
                }
            },
            required=["rel_path"],
        ),
        body_factory=_find_package_body,
    ),
    _ToolSpec(
        name="list_domains",
        description=(
            "Domains under a package (or every package). Domains are the "
            "top-level src/{domain}/ folders that group related modules."
        ),
        parameters=_schema(
            {
                "package_id": {
                    "type": "string",
                    "description": "Optional graph node id; defaults to all packages.",
                }
            }
        ),
        body_factory=_list_domains_body,
    ),
    _ToolSpec(
        name="list_modules",
        description=(
            "Top-level modules inside a domain. Use after `list_domains` "
            "to drill into a specific domain's files."
        ),
        parameters=_schema({"domain_id": {"type": "string"}}, required=["domain_id"]),
        body_factory=_list_modules_body,
    ),
    _ToolSpec(
        name="find_modules",
        description=(
            "Search modules by glob pattern over their bare or dotted name "
            "(e.g. `*build*`, `forktex.graph.*`). Use to locate code by name."
        ),
        parameters=_schema(
            {"name_pattern": {"type": "string"}}, required=["name_pattern"]
        ),
        body_factory=_find_modules_body,
    ),
    _ToolSpec(
        name="package_imports",
        description=(
            "Every external library, sibling package, or in-project module "
            "that the given package imports. Use to map dependencies."
        ),
        parameters=_schema({"package_id": {"type": "string"}}, required=["package_id"]),
        body_factory=_package_imports_body,
    ),
    _ToolSpec(
        name="find_importers",
        description=(
            "Modules in this project that import a given target (a library "
            "name, a sibling package name, or an in-project dotted name like "
            "`forktex.graph.io_proxy`). Use for impact analysis."
        ),
        parameters=_schema({"target": {"type": "string"}}, required=["target"]),
        body_factory=_find_importers_body,
    ),
    _ToolSpec(
        name="fsd_status",
        description=(
            "Current FSD level (L0..L4) plus available Makefile targets for "
            "one package or every package. Use before recommending make targets."
        ),
        parameters=_schema(
            {
                "package_id": {
                    "type": "string",
                    "description": "Optional; defaults to all packages.",
                }
            }
        ),
        body_factory=_fsd_status_body,
    ),
    _ToolSpec(
        name="recent_writes",
        description=(
            "Files inside the project's `.forktex/` directory touched by "
            "ForkTex tooling in the last N hours, with writer attribution. "
            "Use to understand what just changed on disk."
        ),
        parameters=_schema({"hours": {"type": "integer", "default": 24}}),
        body_factory=_recent_writes_body,
    ),
    _ToolSpec(
        name="validate_path",
        description=(
            "Is this path inside `.forktex/` sanctioned by the canonical "
            "structure spec? Returns the matching EntrySpec or rejection reason."
        ),
        parameters=_schema(
            {
                "rel_path": {
                    "type": "string",
                    "description": "Path relative to .forktex/.",
                },
                "scope": {
                    "type": "string",
                    "enum": ["project", "os"],
                    "default": "project",
                },
            },
            required=["rel_path"],
        ),
        body_factory=_validate_path_body,
    ),
    _ToolSpec(
        name="ecosystem_matrix",
        description=(
            "FSD level + package counts for every forktex.json project "
            "under a base directory. Defaults to the parent of the current "
            "project (the typical 'sibling projects' view)."
        ),
        parameters=_schema(
            {
                "base_dir": {
                    "type": "string",
                    "description": "Parent directory; defaults to the project's parent.",
                },
                "include_nested": {"type": "boolean", "default": False},
            }
        ),
        body_factory=_ecosystem_matrix_body,
    ),
)


def create_graph_tools(project_root: str | Path) -> list[Tool]:
    """Build the 12 graph-aware tools, bound to *project_root*."""
    pr = _root(project_root)
    return [
        Tool(
            name=spec.name,
            description=spec.description,
            parameters=spec.parameters,
            handler=spec.body_factory(pr),
        )
        for spec in _TOOL_SPECS
    ]


__all__ = ["create_graph_tools"]
