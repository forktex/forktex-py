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

"""Assemble a :class:`Graph` from disk for a project or the host OS.

Project-scope walk:

* ``project_root`` ─contains→ ``forktex_dir``
* ``project_root`` ─contains→ ``manifest`` ; ``manifest`` ─manifest_of→ ``project_root``
* ``project_root`` ─contains→ ``package`` (one per ``forktex.json``)
* ``package`` ─contains→ ``domain`` (one per ``src/{domain}/`` or ``app/{domain}/``)
* ``domain`` ─contains→ ``module`` (every ``*.py`` under it, recursively;
  nested subpackages keep their full dotted name like ``ai.chat.orchestrator``)
* ``package`` ─depends_on→ ``library`` (parsed from ``pyproject.toml``)

OS-scope walk:

* ``forktex_dir`` (global) ─contains→ ``registered_project`` (one per registry entry)
* ``registered_project`` ─registered_in→ ``forktex_dir`` (global)
* ``forktex_dir`` ─writes_to→ ``file`` (per recorded touch in registry)
"""

from __future__ import annotations

import ast
import json
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from forktex.core.paths import FORKTEX_MANIFEST
from forktex.graph.models import Graph, GraphMeta, GraphNode, NodeKind
from forktex.graph.scopes import OSScope, ProjectScope


SKIP_DIRS = {
    ".git",
    ".venv",
    ".forktex",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".expo",
    ".pytest_cache",
}


# ── Helpers ───────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # fmt: skip
        return {}


def _load_pyproject(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):  # fmt: skip
        return {}


def _node_id(kind: NodeKind, scope_label: str, key: str) -> str:
    return f"{kind}:{scope_label}:{key}"


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


# ── Source layout discovery ───────────────────────────────────────────────


def _resolve_src_dir(package_root: Path, package_name: str) -> Path | None:
    """Return the directory holding a package's domains.

    The contract is *src first, app fallback*: the canonical layout is
    ``<pkg>/src/{importable}/...`` (matches network/api, intelligence/api).
    The importable name often differs from the manifest's ``name`` (e.g.
    ``forktex-py`` vs ``forktex``), so when ``src/{package_name}`` is
    absent we look for a single Python package directly under ``src/``.
    Only when ``src/`` is absent altogether do we fall back to ``app/``.
    """
    src = package_root / "src"
    if src.is_dir():
        explicit = src / package_name
        if explicit.is_dir():
            return explicit
        py_children = [
            child
            for child in src.iterdir()
            if child.is_dir()
            and (child / "__init__.py").is_file()
            and not child.name.startswith((".", "_"))
        ]
        if len(py_children) == 1:
            return py_children[0]
        # Mixed/empty src — walk it directly so callers still see something.
        return src
    app = package_root / "app"
    if app.is_dir():
        return app
    return None


def _domains_under(src_dir: Path) -> list[Path]:
    return sorted(
        child
        for child in src_dir.iterdir()
        if child.is_dir()
        and not child.name.startswith(("_", "."))
        and child.name not in SKIP_DIRS
    )


def _modules_under(domain: Path) -> list[Path]:
    """Find every ``.py`` file under a domain directory, recursively.

    Walks subpackages too — modern Python projects nest meaningful
    structure (e.g. ``api/src/ai/chat/orchestrator.py``). Honours
    ``SKIP_DIRS`` so caches and build outputs don't pollute the graph.
    """

    def _allowed(path: Path) -> bool:
        return not any(part in SKIP_DIRS for part in path.relative_to(domain).parts)

    return sorted(f for f in domain.rglob("*.py") if f.is_file() and _allowed(f))


_MAKE_TARGET_RE = None


def _scan_makefile_targets(makefile_path: Path) -> set[str]:
    """Parse a Makefile cheaply for target names, no `make` invocation.

    Mirrors what FSD's ``_find_makefile_targets`` extracts but without
    spawning a subprocess. Misses dynamically-generated targets, which is
    fine — the FSD evaluator falls back to ``make -pRrq`` when needed.
    """
    if not makefile_path.is_file():
        return set()
    targets: set[str] = set()
    try:
        for raw in makefile_path.read_text(
            encoding="utf-8", errors="ignore"
        ).splitlines():
            line = raw.rstrip()
            if not line or line.startswith(("\t", "#", " ")):
                continue
            if ":" not in line:
                continue
            head, _, tail = line.partition(":")
            head = head.strip()
            if not head or head.startswith((".", "%", "-")):
                continue
            # Skip variable assignments: `FOO := bar`, `FOO ::= bar`, `FOO?=bar`.
            if tail.lstrip().startswith("="):
                continue
            if "=" in head:  # `FOO?=bar`, `FOO+=bar`
                continue
            # ``foo bar:`` declares both targets.
            for part in head.split():
                if part and not part.startswith(("$", "(", "-")):
                    targets.add(part)
    except OSError:
        pass
    return targets


# ── Project-scope build ───────────────────────────────────────────────────


def _add_package(
    g: Graph,
    *,
    project_root: Path,
    package_root: Path,
    manifest_path: Path,
    manifest_data: dict,
) -> str:
    """Add a package + its manifest, domains, modules, and library deps."""

    rel_pkg = _rel(package_root, project_root) or "."
    pkg_id = _node_id("package", "project", rel_pkg)
    pkg_name = manifest_data.get("name") or (
        package_root.name if package_root != project_root else project_root.name
    )
    makefile_targets = _scan_makefile_targets(package_root / "Makefile")
    g.add_node(
        GraphNode(
            id=pkg_id,
            kind="package",
            name=pkg_name,
            scope="project",
            attrs={
                "rel_path": rel_pkg,
                "version": manifest_data.get("version", ""),
                "language": manifest_data.get("language", "python"),
                "publishable": bool(manifest_data.get("publishable", True)),
                "has_makefile": (package_root / "Makefile").is_file(),
                "makefile_targets": sorted(makefile_targets),
            },
        )
    )

    manifest_id = _node_id("manifest", "project", _rel(manifest_path, project_root))
    g.add_node(
        GraphNode(
            id=manifest_id,
            kind="manifest",
            name=manifest_path.name,
            scope="project",
            attrs={"rel_path": _rel(manifest_path, project_root)},
        )
    )
    g.add_edge("contains", pkg_id, manifest_id)
    g.add_edge("manifest_of", manifest_id, pkg_id)

    src_dir = _resolve_src_dir(package_root, pkg_name)
    if src_dir is not None and src_dir.is_dir():
        importable = src_dir.name if src_dir.name != "src" else pkg_name
        for domain_dir in _domains_under(src_dir):
            dom_rel = _rel(domain_dir, project_root)
            dom_id = _node_id("domain", "project", dom_rel)
            g.add_node(
                GraphNode(
                    id=dom_id,
                    kind="domain",
                    name=domain_dir.name,
                    scope="project",
                    attrs={"rel_path": dom_rel},
                )
            )
            g.add_edge("contains", pkg_id, dom_id)

            for module_path in _modules_under(domain_dir):
                mod_rel = _rel(module_path, project_root)
                mod_id = _node_id("module", "project", mod_rel)
                # Dotted name from src_dir-relative path, dot-separated.
                # `__init__.py` collapses to its package's dotted name (drop
                # the last segment). Supports nested subpackages, e.g.
                # ``api/src/ai/chat/orchestrator.py`` →
                # ``forktex-intelligence-api.ai.chat.orchestrator``.
                rel_to_src = module_path.relative_to(src_dir)
                parts = list(rel_to_src.with_suffix("").parts)
                if module_path.stem == "__init__":
                    parts = parts[:-1]
                dotted = ".".join([importable, *parts]) if parts else importable
                g.add_node(
                    GraphNode(
                        id=mod_id,
                        kind="module",
                        name=module_path.stem,
                        scope="project",
                        attrs={
                            "rel_path": mod_rel,
                            "dotted_name": dotted,
                            "abs_path": str(module_path),
                            "importable": importable,
                        },
                    )
                )
                g.add_edge("contains", dom_id, mod_id)

    pyproject_path = package_root / "pyproject.toml"
    if pyproject_path.is_file():
        deps = _parse_dependencies(pyproject_path)
        for dep_name, dep_version in deps.items():
            lib_id = _node_id("library", "project", dep_name)
            g.add_node(
                GraphNode(
                    id=lib_id,
                    kind="library",
                    name=dep_name,
                    scope="project",
                    attrs={"version_constraint": dep_version},
                )
            )
            g.add_edge(
                "depends_on",
                pkg_id,
                lib_id,
                {"version_constraint": dep_version},
            )

    return pkg_id


_IMPORT_FILE_MAX_BYTES = 256 * 1024


def _scan_module_imports(file_path: Path) -> list[tuple[str, int]]:
    """Return ``(absolute_module_name, level)`` per import in *file_path*.

    ``level`` is 0 for absolute imports and >0 for relative imports
    (``from . import x`` is level 1, ``from .. import y`` is level 2).
    Returns ``[]`` on parse error or oversize file.
    """
    try:
        if file_path.stat().st_size > _IMPORT_FILE_MAX_BYTES:
            return []
        source = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, 0))
        elif isinstance(node, ast.ImportFrom):
            if node.module is None and node.level == 0:
                continue
            base = node.module or ""
            level = node.level or 0
            # Record the base module AND each `base.alias` form so the
            # resolver can prefer a sub-module match when it exists
            # (e.g., `from proj.auth import session` where session.py
            # lives in proj/auth/).
            out.append((base, level))
            for alias in node.names:
                if alias.name in {"*"}:
                    continue
                joined = f"{base}.{alias.name}" if base else alias.name
                out.append((joined, level))
    return out


def _resolve_relative_import(module_dotted: str, target: str, level: int) -> str:
    """Resolve a relative import target into its absolute dotted name.

    ``module_dotted`` is the dotted name of the module *doing* the import.
    """
    if level == 0:
        return target
    parts = module_dotted.split(".")
    # ``from . import x`` inside ``a.b.c`` (a regular module) drops the
    # last segment and is equivalent to importing from ``a.b``. For an
    # ``__init__`` module (whose dotted name already ends at the package
    # itself), level 1 means importing from its own package — no drop.
    drop = level
    if not module_dotted.endswith(".__init__"):
        drop = max(0, level - 1) if level >= 1 else 0
        # Standard semantics: level=1 means "this module's package".
        # For a regular module ``a.b.c`` that's ``a.b`` (drop 1 from end).
        drop = level
    base = parts[: max(0, len(parts) - drop)]
    return ".".join([*base, target] if target else base)


def _populate_imports(graph: Graph) -> None:
    """Second pass over the graph: add ``imports`` edges for every module.

    Resolution order for each import target:
    1. If a project ``module`` has dotted_name == target → connect to it.
    2. Else if a project ``module`` has a dotted_name that is a prefix of
       target (a sub-import like ``forktex.graph.io_proxy.tracked_write``
       resolves to the ``forktex.graph.io_proxy`` module) → connect.
    3. Else if the top-level package of the target matches a project
       ``library`` name → connect to library.
    4. Else create / reuse an ``external_dep`` node and connect.
    """
    modules = graph.by_kind("module")
    libraries_by_name = {n.name: n for n in graph.by_kind("library")}
    modules_by_dotted: dict[str, GraphNode] = {}
    for m in modules:
        dotted = m.attrs.get("dotted_name", "")
        if dotted:
            modules_by_dotted[dotted] = m

    sorted_module_dotteds = sorted(modules_by_dotted.keys(), key=lambda s: -len(s))

    def _resolve_target(target: str) -> tuple[str, str]:
        """Return (target_id, target_kind) creating external_dep if needed."""
        if not target:
            return "", ""
        # Exact module match.
        if target in modules_by_dotted:
            return modules_by_dotted[target].id, "module"
        # Prefix match (longest first).
        for d in sorted_module_dotteds:
            if target == d or target.startswith(d + "."):
                return modules_by_dotted[d].id, "module"
        # Library by top-level name. PyPI names use hyphens; Python
        # imports use underscores — so we compare both forms.
        head = target.split(".", 1)[0]
        head_normalised = head.replace("_", "-").lower()
        for lib_name, lib_node in libraries_by_name.items():
            if lib_name.lower() in {head.lower(), head_normalised}:
                return lib_node.id, "library"
        # Otherwise: an external_dep keyed by the import head segment
        # (preserved verbatim — `__future__` stays `__future__`).
        ext_id = _node_id("external_dep", "project", head)
        if graph.node(ext_id) is None:
            graph.add_node(
                GraphNode(
                    id=ext_id,
                    kind="external_dep",
                    name=head,
                    scope="project",
                    attrs={"dotted_name": head},
                )
            )
        return ext_id, "external_dep"

    for module in modules:
        abs_path_str = module.attrs.get("abs_path")
        if not abs_path_str:
            continue
        abs_path = Path(abs_path_str)
        dotted_self = module.attrs.get("dotted_name", "")
        try:
            imports = _scan_module_imports(abs_path)
        except (OSError, ValueError):  # fmt: skip
            continue
        seen: set[tuple[str, str]] = set()
        for target_name, level in imports:
            absolute = _resolve_relative_import(dotted_self, target_name, level)
            if not absolute:
                continue
            target_id, target_kind = _resolve_target(absolute)
            if not target_id or target_id == module.id:
                continue
            key = (target_id, target_kind)
            if key in seen:
                continue
            seen.add(key)
            graph.add_edge(
                "imports",
                module.id,
                target_id,
                {"target_dotted": absolute, "target_kind": target_kind},
            )


def _parse_dependencies(pyproject_path: Path) -> dict[str, str]:
    data = _load_pyproject(pyproject_path)
    deps: dict[str, str] = {}
    for raw in data.get("project", {}).get("dependencies", []) or []:
        name, _, rest = str(raw).partition(" ")
        deps[name.strip().lower()] = rest.strip("() ")
    return deps


def _discover_child_manifests(project_root: Path) -> list[Path]:
    return sorted(
        m
        for m in project_root.rglob(FORKTEX_MANIFEST)
        if not any(part in SKIP_DIRS for part in m.parts)
        and m != project_root / FORKTEX_MANIFEST
    )


def _add_forktex_dir_node(
    g: Graph,
    *,
    project_root: Path,
    location: Path,
) -> str | None:
    """Add a ``forktex_dir`` node for *location*'s ``.forktex`` if it exists."""
    fdir = location / ".forktex"
    if not fdir.is_dir():
        return None
    rel = _rel(fdir, project_root)
    fdir_id = _node_id("forktex_dir", "project", rel)
    g.add_node(
        GraphNode(
            id=fdir_id,
            kind="forktex_dir",
            name=".forktex",
            scope="project",
            attrs={"rel_path": rel, "abs_path": str(fdir)},
        )
    )
    return fdir_id


def _build_project(scope: ProjectScope, *, with_imports: bool = True) -> Graph:
    project_root = scope.root.resolve()
    meta = GraphMeta(
        generated_at=_now_iso(),
        scope="project",
        root=str(project_root),
    )
    g = Graph.empty(meta)

    root_id = _node_id("project_root", "project", project_root.name)
    g.add_node(
        GraphNode(
            id=root_id,
            kind="project_root",
            name=project_root.name,
            scope="project",
            attrs={"abs_path": str(project_root)},
        )
    )

    # Root-level .forktex/.
    root_fdir_id = _add_forktex_dir_node(
        g, project_root=project_root, location=project_root
    )
    if root_fdir_id is not None:
        g.add_edge("contains", root_id, root_fdir_id)

    # Collect all manifests (root + nested) sorted parent-first by path depth
    # so each package can attach to its nearest ancestor package.
    manifests: list[tuple[Path, Path]] = []
    root_manifest = project_root / FORKTEX_MANIFEST
    if root_manifest.is_file():
        manifests.append((root_manifest, project_root))
    for child_manifest in _discover_child_manifests(project_root):
        manifests.append((child_manifest, child_manifest.parent))
    manifests.sort(
        key=lambda item: (
            len(_rel(item[1], project_root).split("/"))
            if _rel(item[1], project_root) != "."
            else 0
        )
    )

    # Map rel_path → package node id, used to pick the nearest ancestor.
    package_by_relpath: dict[str, str] = {}

    for manifest_path, package_root in manifests:
        rel_pkg = _rel(package_root, project_root) or "."
        manifest_data = _load_json(manifest_path)
        pkg_id = _add_package(
            g,
            project_root=project_root,
            package_root=package_root,
            manifest_path=manifest_path,
            manifest_data=manifest_data,
        )
        package_by_relpath[rel_pkg] = pkg_id

        # Attach to nearest ancestor package, falling back to project_root.
        parent_id = root_id
        if rel_pkg != ".":
            segments = rel_pkg.split("/")
            for depth in range(len(segments) - 1, -1, -1):
                ancestor_rel = "/".join(segments[:depth]) or "."
                if ancestor_rel == rel_pkg:
                    continue
                if ancestor_rel in package_by_relpath:
                    parent_id = package_by_relpath[ancestor_rel]
                    break
        g.add_edge("contains", parent_id, pkg_id)

        # Attach a nested ``.forktex/`` directory if this package owns one
        # (only for non-root packages — root's .forktex is already attached).
        if package_root != project_root:
            nested_fdir_id = _add_forktex_dir_node(
                g, project_root=project_root, location=package_root
            )
            if nested_fdir_id is not None:
                g.add_edge("contains", pkg_id, nested_fdir_id)

    # Second pass: AST-extracted imports across every module. Skippable
    # for huge monorepos via ``with_imports=False``; the graph is still
    # complete in every other dimension.
    if with_imports:
        _populate_imports(g)

    return g


# ── OS-scope build ────────────────────────────────────────────────────────


def _build_os(scope: OSScope) -> Graph:
    base = scope.forktex_dir
    meta = GraphMeta(
        generated_at=_now_iso(),
        scope="os",
        root=str(base),
    )
    g = Graph.empty(meta)

    fdir_id = _node_id("forktex_dir", "os", str(base))
    g.add_node(
        GraphNode(
            id=fdir_id,
            kind="forktex_dir",
            name=base.name or "forktex",
            scope="os",
            attrs={"abs_path": str(base)},
        )
    )

    # Lazy import to avoid a circular dependency: registry imports nothing
    # from build, but build pulls registry only when running.
    from forktex.graph import registry as _registry

    # Build registered_project nodes parent-first so we can detect nesting
    # (a monorepo's outer registry entry contains its inner package entries).
    entries = sorted(_registry.iter_registered_projects(), key=lambda e: e.root)
    proj_id_by_root: dict[str, str] = {}

    for entry in entries:
        proj_id = _node_id("registered_project", "os", entry.root)
        g.add_node(
            GraphNode(
                id=proj_id,
                kind="registered_project",
                name=Path(entry.root).name,
                scope="os",
                attrs={
                    "abs_path": entry.root,
                    "first_seen_at": entry.first_seen_at,
                    "last_touched_at": entry.last_touched_at,
                    "exists": Path(entry.root).is_dir(),
                },
            )
        )
        proj_id_by_root[entry.root] = proj_id

        # Attach to nearest registered ancestor, falling back to ``forktex_dir``.
        parent_id = fdir_id
        try:
            entry_path = Path(entry.root)
            for ancestor in entry_path.parents:
                ancestor_str = str(ancestor)
                if ancestor_str in proj_id_by_root:
                    parent_id = proj_id_by_root[ancestor_str]
                    break
        except (OSError, ValueError):  # fmt: skip
            pass
        g.add_edge("contains", parent_id, proj_id)
        g.add_edge("registered_in", proj_id, fdir_id)

        for touch in entry.touches:
            file_id = _node_id("file", "os", f"{entry.root}::{touch.rel_path}")
            g.add_node(
                GraphNode(
                    id=file_id,
                    kind="file",
                    name=touch.rel_path,
                    scope="os",
                    attrs={
                        "rel_path": touch.rel_path,
                        "kind": touch.kind,
                        "writer": touch.writer or "",
                        "last_touched_at": touch.last_touched_at,
                    },
                )
            )
            g.add_edge(
                "writes_to",
                proj_id,
                file_id,
                {"writer": touch.writer or "", "kind": touch.kind},
            )

    return g


# ── Public API ────────────────────────────────────────────────────────────


def build_graph(scope: ProjectScope | OSScope, *, with_imports: bool = True) -> Graph:
    """Build a :class:`Graph` for the requested scope and return it sorted.

    The result is deterministically sorted so that committing
    ``graph.json`` to git produces stable diffs. Pass
    ``with_imports=False`` to skip the AST imports pass — useful for
    huge monorepos where the per-file AST cost is the dominant factor.
    OS scope ignores this flag (no module nodes to scan).
    """
    if isinstance(scope, ProjectScope):
        graph = _build_project(scope, with_imports=with_imports)
    else:
        graph = _build_os(scope)
    return graph.sorted()
