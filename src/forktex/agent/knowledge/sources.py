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

"""Knowledge sources — load corpora into a fractal Workspace + resolve namespaces.

Two consumer loaders:
  - ``load_docs_corpus`` — a docs repo (``engineering/manifest.json`` + markdown)
    → a fractal Workspace, read-only. Origin-tagged kinds (``docs.archetype`` …);
    manifest cross-refs become ``reference`` edges (never the ``parent`` axis, so
    docs cycles can't pollute the nesting DAG).
  - ``forktex_core.fractal.load_workspace`` — a native ``nodes/`` + ``patches/`` tree.

``KnowledgeResolver`` resolves a namespace to a Workspace, and composes the
configured layers (global docs + project overlay) under the ``knowledge`` namespace.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from forktex_core.fractal import (
    Layer,
    Node,
    Workspace,
    compose_workspaces,
    load_workspace,
    node_from_frontmatter,
)
from forktex_core.fractal.io import split_frontmatter

_log = logging.getLogger("forktex.knowledge")

ENGINEERING_DIR = "engineering"
MANIFEST_FILENAME = "manifest.json"
COMPOSED_NAMESPACE = "knowledge"

#: ForkTex docs are license-header-prefixed (every file opens with a trade-secret
#: HTML comment block before the YAML frontmatter). Core ``split_frontmatter``
#: requires the file to start on line 1 with ``---``; this loader strips the
#: leading HTML comment(s) + whitespace so the on-disk ``summary:`` / ``tags:`` /
#: ``updated:`` actually reach the workspace. The convention lives here, not core.
_LEADING_HTML_COMMENTS = re.compile(r"\A(?:\s*<!--.*?-->)+\s*", re.DOTALL)


def _strip_docs_header(text: str) -> str:
    """Remove leading HTML comment blocks (license headers) + whitespace."""
    m = _LEADING_HTML_COMMENTS.match(text)
    return text[m.end() :] if m else text


def default_docs_path() -> str | None:
    """Resolve the global docs repo: ``$FORKTEX_DOCS``, else ``<workspace-root>/docs``.

    Returns ``None`` when neither is set nor found — the resolver then composes the
    project doc-space alone (no global principles layer). Never hardcodes a path, so
    it travels across machines/CI (overridable via ``--docs`` / ``$FORKTEX_DOCS``).
    """
    env = os.environ.get("FORKTEX_DOCS")
    if env:
        return env
    try:
        from forktex.core.paths import find_workspace_root

        root = find_workspace_root()
    except Exception:
        return None
    if root is None:
        return None
    docs = Path(root) / "docs"
    return str(docs) if docs.is_dir() else None


#: Conventional per-project doc-space, under a repo root: the recycle write-target
#: and the overlay the global docs compose under. One per repo → memory is local
#: to the project but composes onto the shared principles.
PROJECT_DOC_SPACE = ".forktex/knowledge"


def project_doc_space(root: str | Path) -> Path:
    """The conventional project doc-space dir under ``root`` (``.forktex/knowledge``)."""
    return Path(root) / ".forktex" / "knowledge"


def resolve_doc_space(target: str | Path) -> Path:
    """Normalize a user-supplied ``--project`` value to a ``.forktex/knowledge`` doc-space.

    Accepts either a doc-space dir *or* a repo root and always lands inside
    ``.forktex/knowledge`` — so pointing ``-d`` at a repo root (``.``, a project
    dir) can never create stray top-level ``nodes/``/``patches/``. The three
    write-back commands (recycle/retire/rollup) route their ``project`` through
    this before handing it to :func:`ensure_doc_space`.
    """
    p = Path(target)
    if p.name == "knowledge" and p.parent.name == ".forktex":
        return p  # already a doc-space — use as-is
    if (p / ".forktex").exists() or (p / "forktex.json").exists():
        return project_doc_space(p)  # a repo root → derive its doc-space
    return p  # back-compat: an explicit doc-space dir that isn't under a repo


def ensure_doc_space(path: str | Path) -> Path:
    """Ensure a doc-space has ``nodes/`` + ``patches/`` (so it overlays); return it.

    Used by recycle-enabled surfaces so the project layer is present even on a
    fresh repo — recycled nodes then become queryable in the same session.
    """
    space = Path(path)
    (space / "nodes").mkdir(parents=True, exist_ok=True)
    (space / "patches").mkdir(parents=True, exist_ok=True)
    return space


# ── docs-corpus loader (read-only consumer adapter) ──────────────────────────


def load_docs_corpus(root: Path | str) -> Workspace:
    """Load a docs-shaped corpus (``engineering/manifest.json`` + markdown) read-only."""
    root = Path(root)
    manifest_path = root / ENGINEERING_DIR / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"docs manifest not found at {manifest_path} — is this a docs corpus?"
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items: list[dict[str, Any]] = manifest.get("items", [])

    ws = Workspace(root=str(root))
    for item in items:  # pass 1 — load every item with a resolvable file
        node = _try_load_item(root, item)
        if node is not None:
            ws.add(node)
    _project_references(ws, items)  # pass 2 — manifest cross-refs → reference edges
    return ws


def _try_load_item(root: Path, item: dict[str, Any]) -> Node | None:
    rel_path = item.get("path")
    if not rel_path:
        return None
    file_path = root / rel_path
    # Manifest paths are written relative to the repo root (e.g.
    # "docs/engineering/…"); when root *is* that docs dir, strip the prefix.
    if not file_path.is_file() and rel_path.startswith("docs/"):
        file_path = root / rel_path[len("docs/") :]
    if not file_path.is_file():
        return None
    try:
        fm, body = split_frontmatter(
            _strip_docs_header(file_path.read_text(encoding="utf-8"))
        )
        return _build_node(item, fm, body)
    except Exception as exc:
        _log.warning("skipped malformed docs node %s: %s", file_path, exc)
        return None


def _build_node(item: dict[str, Any], fm: dict[str, Any], body_md: str) -> Node:
    return node_from_frontmatter(
        {
            "id": item["id"],
            "kind": f"docs.{item.get('kind', 'node')}",
            "title": fm.get("title") or item.get("title", item["id"]),
            # Curated summary (on-disk) is the embedded + grounding-injected text;
            # the body is pulled on demand. Manifest has no summary today; on-disk wins.
            "summary": fm.get("summary") or item.get("summary"),
            "status": str(fm.get("status") or item.get("status", "active")),
            "version": str(fm.get("version") or item.get("version", "0.1.0")),
            "updated_at": str(fm.get("updated") or item.get("updated") or "") or None,
            "tags": _collect_tags(item, fm),
        },
        body_md,
    )


def _collect_tags(item: dict[str, Any], fm: dict[str, Any]) -> list[str]:
    seen: dict[str, None] = {}
    for source in (
        item.get("stack") or [],
        item.get("source_paths") or [],
        fm.get("stack") or [],
        fm.get("tags") or [],
    ):
        for tag in source:
            if isinstance(tag, str):
                seen.setdefault(tag, None)
    return list(seen)


def _project_references(ws: Workspace, items: list[dict[str, Any]]) -> None:
    """A manifest item's ``archetype`` / ``related_entry`` → a ``reference`` edge."""
    for item in items:
        node = ws.nodes.get(item["id"])
        if node is None:
            continue
        refs = node.edges.setdefault("reference", [])
        archetype = item.get("archetype")
        if isinstance(archetype, str):
            target = f"archetype.{archetype}"
            if target in ws.nodes and target not in refs:
                refs.append(target)
        related = item.get("related_entry")
        if isinstance(related, str) and related in ws.nodes and related not in refs:
            refs.append(related)
        if not refs:
            node.edges.pop("reference", None)


# ── generic adapters (point forktex at any markdown tree / codebase) ─────────

#: Directories never descended when indexing an arbitrary tree.
_IGNORE_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        ".forktex",
        "dist",
        "build",
        ".venv",
        "venv",
        "__pycache__",
        "vendor",
        ".next",
        ".cache",
        "target",
        ".idea",
        ".tox",
        "htmlcov",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)

#: Source extension → language label for ``code_index``.
_CODE_EXT_LANG: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sh": "shell",
    ".sql": "sql",
}
_CODE_MAX_BYTES = 256 * 1024
_CODE_MAX_FILES = 5000


def _slug(rel: str) -> str:
    # Preserve ``.`` / ``_`` / ``-`` so distinct paths stay distinct ids —
    # collapsing them would make ``cloud/__init__.py`` and ``cloud/init.py``
    # collide. Only path separators + odd chars become ``-``.
    return re.sub(r"[^a-z0-9._-]+", "-", rel.lower()).strip("-.") or "x"


def _first_h1(body: str) -> str | None:
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip() or None
    return None


def _excerpt(body: str, limit: int = 240) -> str | None:
    """First prose paragraph (skipping headings / blank lines), truncated.

    Becomes the node ``summary`` when the file has no frontmatter summary, so
    arbitrary markdown is searchable on its content (the cheap index reads the
    summary; the body is pulled on demand).
    """
    for line in body.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s[:limit]
    return None


def _walk_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    """Files under ``root`` ending in ``suffixes``, pruning vendored/hidden dirs."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in _IGNORE_DIRS and not d.startswith(".")
        ]
        for fn in filenames:
            if fn.lower().endswith(suffixes):
                out.append(Path(dirpath) / fn)
    return sorted(out)


def load_generic_markdown(root: Path | str) -> Workspace:
    """Load any directory of ``*.md`` into a read-only Workspace (one node per file).

    Frontmatter (``title``/``summary``/``tags``/``status``) is honoured when
    present; otherwise the title falls back to the first ``# H1`` or the filename.
    """
    root = Path(root)
    ws = Workspace(root=str(root))
    for fp in _walk_files(root, (".md",)):
        rel = fp.relative_to(root).as_posix()
        nid = f"md.{_slug(rel)}"
        if nid in ws.nodes:
            continue  # distinct path, same slug — keep the first, skip the dupe
        try:
            fm, body = split_frontmatter(
                fp.read_text(encoding="utf-8", errors="replace")
            )
            ws.add(
                node_from_frontmatter(
                    {
                        "id": nid,
                        "kind": "markdown",
                        "title": fm.get("title") or _first_h1(body) or fp.stem,
                        "summary": fm.get("summary") or _excerpt(body),
                        "status": str(fm.get("status") or "active"),
                        "version": str(fm.get("version") or "0.1.0"),
                        "updated_at": str(
                            fm.get("updated") or fm.get("updated_at") or ""
                        )
                        or None,
                        "tags": [
                            t for t in (fm.get("tags") or []) if isinstance(t, str)
                        ],
                    },
                    body,
                )
            )
        except Exception as exc:
            _log.warning("skipped malformed markdown %s: %s", fp, exc)
    return ws


def load_code_index(root: Path | str) -> Workspace:
    """Index any codebase's source files into a read-only Workspace (one node per file).

    A language-agnostic *file* index (the deep structural view stays ``arch`` /
    ``graph.build``): summary = ``<lang> · <relpath>``, body = file content
    (pulled on demand). Bounded by an extension allowlist, a per-file size cap,
    and a total-file cap (over-cap files are skipped with a logged warning).
    """
    root = Path(root)
    ws = Workspace(root=str(root))
    suffixes = tuple(_CODE_EXT_LANG)
    indexed = dropped = 0
    for fp in _walk_files(root, suffixes):
        if indexed >= _CODE_MAX_FILES:
            dropped += 1
            continue
        try:
            if fp.stat().st_size > _CODE_MAX_BYTES:
                dropped += 1
                continue
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = fp.relative_to(root).as_posix()
        nid = f"code.{_slug(rel)}"
        if nid in ws.nodes:
            continue  # distinct path, same slug — keep the first, skip the dupe
        lang = _CODE_EXT_LANG[fp.suffix.lower()]
        top = rel.split("/", 1)[0] if "/" in rel else "(root)"
        ws.add(
            Node(
                id=nid,
                kind=f"code.{lang}",
                title=rel,
                summary=f"{lang} · {rel}",
                body_md=text,
                tags=[lang, top],
            )
        )
        indexed += 1
    if dropped:
        import logging

        logging.getLogger("forktex.knowledge").warning(
            "code_index: skipped %d file(s) over the size/count cap under %s",
            dropped,
            root,
        )
    return ws


# ── resolver (read seam for the query core) ──────────────────────────────────


def _tree_mtime(path: Path, patterns: tuple[str, ...]) -> int:
    """Most-recent mtime (ns) among files matching ``patterns`` under ``path``.

    Patterns are ``Path.glob`` expressions relative to ``path`` (e.g.
    ``"nodes/*.md"``, ``"engineering/manifest.json"``). Restricting the walk
    to just the source files we actually load — instead of ``rglob("*")``
    across the entire tree — turns a 28-file mtime check from an 826-file
    walk into ~30 stats. Returns 0 if no file matches (a fresh / empty layer).
    """
    best = 0
    for pattern in patterns:
        for p in path.glob(pattern):
            if p.is_file():
                m = p.stat().st_mtime_ns
                if m > best:
                    best = m
    return best


#: Files the docs-corpus adapter actually reads — narrower than ``**/*``.
_DOCS_MTIME_PATTERNS: tuple[str, ...] = (
    "engineering/manifest.json",
    "engineering/archetypes/*.md",
    "engineering/blueprints/*.md",
    "engineering/standards/*.md",
)

#: Files the workspace adapter reads from a fractal doc-space.
_WORKSPACE_MTIME_PATTERNS: tuple[str, ...] = ("nodes/*.md", "patches/*.md")


@dataclass(frozen=True)
class _LayerSpec:
    """A lazily-(re)loaded layer: where to read it and how.

    ``mtime_patterns`` is the narrow set of glob patterns (relative to ``path``)
    that the loader actually consults. The resolver's mtime cache scans only
    these — not the whole tree — so reload detection scales with the source
    file count, not the directory total.
    """

    name: str
    path: Path
    loader: Callable[[Path], Workspace]
    mtime_patterns: tuple[str, ...]


class KnowledgeResolver:
    """A reload-aware ``forktex_core.fractal`` ``WorkspaceResolver`` over layers.

    Each layer is resolvable by its own name; the ``knowledge`` namespace returns
    the composed view (later layers overlay earlier — global docs ← project on top).

    Layers are (re)loaded from disk **lazily and cached by directory mtime**, so a
    node recycled into the project doc-space becomes queryable without rebuilding
    the resolver — the compounding loop, even inside a long-lived ``forktex mcp``
    process where the same resolver answers query after query.
    """

    def __init__(self, specs: list[_LayerSpec]) -> None:
        self._specs = list(specs)
        self._cache: dict[str, tuple[int, Workspace]] = {}
        self._composed: tuple[tuple[int, ...], Workspace] | None = None

    def namespaces(self) -> list[str]:
        names = [s.name for s in self._specs]
        return ([COMPOSED_NAMESPACE] if self._specs else []) + names

    def _layer(self, spec: _LayerSpec) -> Workspace:
        mtime = _tree_mtime(spec.path, spec.mtime_patterns)
        cached = self._cache.get(spec.name)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        ws = spec.loader(spec.path)
        self._cache[spec.name] = (mtime, ws)
        return ws

    def resolve(self, namespace: str) -> Workspace:
        if namespace == COMPOSED_NAMESPACE:
            if not self._specs:
                raise KeyError("no knowledge sources configured")
            loaded = [(s.name, self._layer(s)) for s in self._specs]
            if len(loaded) == 1:
                return loaded[0][1]
            sig = tuple(self._cache[s.name][0] for s in self._specs)
            if self._composed is not None and self._composed[0] == sig:
                return self._composed[1]  # nothing changed → reuse the composition
            view = compose_workspaces([Layer(n, w) for n, w in loaded])
            self._composed = (sig, view.workspace)
            return view.workspace
        for spec in self._specs:
            if spec.name == namespace:
                return self._layer(spec)
        raise KeyError(f"unknown namespace: {namespace!r}")


#: Files the generic adapters read.
_MARKDOWN_MTIME_PATTERNS: tuple[str, ...] = ("**/*.md",)
_CODE_MTIME_PATTERNS: tuple[str, ...] = tuple(f"**/*{ext}" for ext in _CODE_EXT_LANG)

#: Adapter name → (loader callable, mtime pattern tuple). Extending it is a
#: matter of writing a new ``load_<adapter>(path) -> Workspace`` and registering
#: it here; ``known_adapters()`` is the single source `doctor` validates against.
_ADAPTERS: dict[str, tuple[Callable[[Path], Workspace], tuple[str, ...]]] = {
    "docs_corpus": (load_docs_corpus, _DOCS_MTIME_PATTERNS),
    "workspace": (load_workspace, _WORKSPACE_MTIME_PATTERNS),
    "generic_markdown": (load_generic_markdown, _MARKDOWN_MTIME_PATTERNS),
    "code_index": (load_code_index, _CODE_MTIME_PATTERNS),
}


def known_adapters() -> frozenset[str]:
    """The registered adapter names — the single source `doctor` validates against."""
    return frozenset(_ADAPTERS)


def build_knowledge_resolver(
    *,
    docs_path: str | Path | None = None,
    project_path: str | Path | None = None,
    config: Any | None = None,
    extra_sources: list[tuple[str, str, str]] | None = None,
) -> KnowledgeResolver:
    """Build a resolver, either from explicit paths or from a ``KnowledgeConfig``.

    Two modes:

    - **Default (today's behaviour).** Without an explicit ``config.layers``,
      the resolver composes the global ``docs_path`` (or ``default_docs_path()``)
      via the ``docs_corpus`` adapter + the ``project_path`` (if it has a
      ``nodes/`` or ``patches/`` dir) via the ``workspace`` adapter.
    - **Target-agnostic mode.** When ``config.layers`` is set, each
      :class:`~forktex.manifest.models.KnowledgeLayerDef` declares ``path`` +
      ``adapter``, and the resolver composes them in order (later overlays
      earlier). ``docs_path`` / ``project_path`` are ignored. This lets the
      knowledge mechanism ground on any workspace structure — the substrate
      is agnostic, the adapter does the format-specific parsing.

    All layers are (re)loaded lazily and cached by file-pattern mtime, so a
    recycled node surfaces without rebuilding the resolver.
    """
    specs: list[_LayerSpec] = []

    if config is not None and getattr(config, "layers", None):
        for layer in config.layers:
            adapter = _ADAPTERS.get(layer.adapter)
            if adapter is None:
                # Unknown adapter — skip silently rather than crash the agent.
                # ``forktex knowledge doctor`` flags this as actionable drift.
                continue
            loader, patterns = adapter
            specs.append(_LayerSpec(layer.name, Path(layer.path), loader, patterns))
    else:
        # Default composition (later layers overlay earlier): docs ← global ← project.
        resolved_docs = docs_path or default_docs_path()
        if resolved_docs is not None:
            docs = Path(resolved_docs)
            if (docs / ENGINEERING_DIR / MANIFEST_FILENAME).is_file():
                specs.append(
                    _LayerSpec("docs", docs, load_docs_corpus, _DOCS_MTIME_PATTERNS)
                )

        # Host-wide personal layer (~/.forktex/knowledge) — cross-project lessons +
        # workspace-governance constraints, queryable from any project.
        from forktex.substrate import paths as _sub

        global_kn = _sub.global_knowledge_dir()
        if (global_kn / "nodes").is_dir() or (global_kn / "patches").is_dir():
            specs.append(
                _LayerSpec(
                    "global", global_kn, load_workspace, _WORKSPACE_MTIME_PATTERNS
                )
            )

        if project_path is not None:
            project = Path(project_path)
            if (project / "nodes").is_dir() or (project / "patches").is_dir():
                specs.append(
                    _LayerSpec(
                        "project", project, load_workspace, _WORKSPACE_MTIME_PATTERNS
                    )
                )

    # Ad-hoc sources (CLI ``--source ADAPTER:PATH``) overlay last — point the
    # composed view at any extra markdown tree / codebase without editing config.
    for name, path, adapter_key in extra_sources or []:
        adapter = _ADAPTERS.get(adapter_key)
        if adapter is None:
            continue
        loader, patterns = adapter
        specs.append(_LayerSpec(name, Path(path), loader, patterns))

    return KnowledgeResolver(specs)


__all__ = [
    "COMPOSED_NAMESPACE",
    "PROJECT_DOC_SPACE",
    "KnowledgeResolver",
    "build_knowledge_resolver",
    "default_docs_path",
    "ensure_doc_space",
    "known_adapters",
    "load_code_index",
    "load_docs_corpus",
    "load_generic_markdown",
    "project_doc_space",
]
