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

"""The canonical ``.forktex/`` spec — every file forktex writes is declared here.

Paired with :mod:`forktex.substrate.paths`: where ``paths`` builds the ``Path``,
this module classifies it. The two MUST agree — ``tests/test_structure_contract``
validates that every ``paths`` factory output matches an :class:`EntrySpec`.

The layout is bucketed by lifecycle (``knowledge`` / ``secrets`` / ``cache`` /
``state``); see :mod:`forktex.substrate.paths` and ``standard.forktex-architecture``.
Writes that don't match a spec entry are rejected by
:func:`forktex.substrate.write.tracked_write` (or surfaced as audit warnings in
lenient mode).
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

#: Substrate scope: a per-repo project tree or the host-wide OS layout. Owned
#: here (the substrate authority); graph + others import it from substrate.
Scope = Literal["project", "os"]

EntryKind = Literal["file", "dir"]
Sensitivity = Literal["public", "config", "secret"]


@dataclass(frozen=True)
class EntrySpec:
    """A single canonical entry inside ``.forktex/`` (project or global).

    ``pattern`` is a relative-to-``.forktex/`` path expression using ``fnmatch``
    semantics (``*`` matches one segment, ``**`` matches any). Variable segments
    (env, agent_id, service_id, domain) are matched as ``*`` glob wildcards.
    """

    pattern: str
    kind: EntryKind
    purpose: str
    sensitivity: Sensitivity = "public"
    required: bool = False
    writers: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""


# ── Project-scope spec (relative to ``<root>/.forktex/``) ────────────────────


PROJECT_SPEC: tuple[EntrySpec, ...] = (
    # Root markers.
    EntrySpec(
        pattern=".version",
        kind="file",
        purpose="Schema-version marker; the only non-knowledge file committed to "
        "git so the layout version travels with the repo.",
        required=True,
        writers=("forktex.substrate.paths.write_schema_version",),
    ),
    EntrySpec(
        pattern=".gitignore",
        kind="file",
        purpose="Defence-in-depth gitignore: ignores everything under .forktex/ "
        "except the committed knowledge/ bucket and .version.",
        required=True,
        writers=("forktex.runtime.lifecycle",),
    ),
    EntrySpec(
        pattern="config.json",
        kind="file",
        purpose="Project-level forktex settings.",
        sensitivity="config",
    ),
    # ── knowledge/ (committed source of truth) ──
    EntrySpec(
        pattern="knowledge/README.md",
        kind="file",
        purpose="Human orientation for the project doc-space (seeded by "
        "`forktex knowledge init`). Optional; never read by the runtime.",
        writers=("forktex.agent.knowledge.init",),
    ),
    EntrySpec(
        pattern="knowledge/nodes/*.md",
        kind="file",
        purpose="Project knowledge nodes — recycled lessons, conventions, rolled-up "
        "topic summaries. Composes with the global docs corpus to ground agents.",
        writers=(
            "forktex.agent.knowledge.recycle",
            "forktex.agent.knowledge.rollup",
            "forktex.agent.knowledge.retire",
        ),
    ),
    EntrySpec(
        pattern="knowledge/patches/*.md",
        kind="file",
        purpose="Provenance patches for the doc-space — one per recycle/rollup/retire.",
        writers=(
            "forktex.agent.knowledge.recycle",
            "forktex.agent.knowledge.rollup",
            "forktex.agent.knowledge.retire",
        ),
    ),
    # ── secrets/ (never committed) ──
    EntrySpec(
        pattern="secrets/intelligence.json",
        kind="file",
        purpose="Per-project LLM endpoint + key override.",
        sensitivity="secret",
        writers=("forktex.agent.intelligence.settings",),
    ),
    EntrySpec(
        pattern="secrets/network.json",
        kind="file",
        purpose="Per-project network JWT + endpoint.",
        sensitivity="secret",
        writers=("forktex.agent.network.settings",),
    ),
    EntrySpec(
        pattern="secrets/cloud/config.json",
        kind="file",
        purpose="Cloud workspace selection (org/project/env).",
        sensitivity="config",
        writers=("forktex.agent.cloud.settings",),
    ),
    EntrySpec(
        pattern="secrets/vault/*/secrets.enc",
        kind="file",
        purpose="Fernet-encrypted secrets blob for one environment.",
        sensitivity="secret",
        writers=("forktex.agent.cloud.vault",),
    ),
    EntrySpec(
        pattern="secrets/keys/*.key",
        kind="file",
        purpose="Per-server SSH private key.",
        sensitivity="secret",
        writers=("forktex.agent.cloud",),
    ),
    EntrySpec(
        pattern="secrets/.env",
        kind="file",
        purpose="Generated docker-compose environment file (ports, credentials, "
        "connection strings) consumed by the generated compose file.",
        sensitivity="secret",
        writers=("forktex.agent.cloud.up",),
    ),
    EntrySpec(
        pattern="secrets/ssl/custom/**",
        kind="dir",
        purpose="User-supplied SSL certificates.",
        sensitivity="secret",
    ),
    # ── cache/ (regenerable) ──
    EntrySpec(
        pattern="cache/docker-compose.*.yml",
        kind="file",
        purpose="Generated docker-compose for one of dev/staging/prod.",
        sensitivity="config",
        writers=("forktex.agent.cloud.up",),
    ),
    EntrySpec(
        pattern="cache/observability/**",
        kind="dir",
        purpose="Generated Loki/Promtail configs.",
        sensitivity="config",
        writers=("forktex.agent.cloud.up",),
    ),
    EntrySpec(
        pattern="cache/db/**",
        kind="dir",
        purpose="Database service build context (Dockerfile + tuned configs) "
        "referenced by the generated compose file.",
        sensitivity="config",
        writers=("forktex.agent.cloud.up",),
    ),
    EntrySpec(
        pattern="cache/redis/**",
        kind="dir",
        purpose="Redis service build context (Dockerfile + redis.conf).",
        sensitivity="config",
        writers=("forktex.agent.cloud.up",),
    ),
    EntrySpec(
        pattern="cache/generated/**",
        kind="dir",
        purpose="Generated gateway/balancer/compute configuration.",
        sensitivity="config",
        writers=("forktex.agent.cloud.up",),
    ),
    EntrySpec(
        pattern="cache/data/*/**",
        kind="dir",
        purpose="Per-service runtime data (bind-mounted into containers).",
        sensitivity="config",
    ),
    EntrySpec(
        pattern="cache/backups/**",
        kind="dir",
        purpose="Database snapshots produced by deploy hooks / `forktex cloud backup`.",
        sensitivity="secret",
        writers=("forktex.agent.cloud",),
    ),
    EntrySpec(
        pattern="cache/bootstrap.json",
        kind="file",
        purpose="One-shot bootstrap manifest written by `forktex cloud up`.",
        sensitivity="config",
        writers=("forktex.agent.cloud.up",),
    ),
    EntrySpec(
        pattern="cache/fsd/evidence/**",
        kind="dir",
        purpose="FSD check/report evidence outputs.",
        writers=("forktex.agent.fsd.check", "forktex.agent.fsd.report"),
    ),
    EntrySpec(
        pattern="cache/graph.json",
        kind="file",
        purpose="Source-of-truth multi-edge project graph (canonical body).",
        writers=("forktex.graph.export.json_writer",),
    ),
    EntrySpec(
        pattern="cache/graph.dsl",
        kind="file",
        purpose="Structurizr DSL projection of the project graph.",
        writers=("forktex.graph.export.dsl_writer",),
    ),
    EntrySpec(
        pattern="cache/graph.html",
        kind="file",
        purpose="Standalone HTML viewer with the graph payload embedded.",
        writers=("forktex.graph.export.html_writer",),
    ),
    EntrySpec(
        pattern="cache/c4.html",
        kind="file",
        purpose="Per-platform C4 view.",
        writers=("forktex.agent.graph.cli",),
    ),
    EntrySpec(
        pattern="cache/manual/**",
        kind="dir",
        purpose="Generated architecture + AI manual bundle. manual_bundle.json is "
        "the load-bearing reader (intelligence.grounding); others are advisory.",
        writers=("forktex.agent.graph.cli",),
    ),
    EntrySpec(
        pattern="cache/scraper/truths/*.json",
        kind="file",
        purpose="Per-domain scraping knowledge (regenerable by re-scraping).",
        writers=("forktex.agent.scraper.truths",),
    ),
    EntrySpec(
        pattern="cache/scraper/output/**",
        kind="dir",
        purpose="Structured scrape exports.",
        writers=("forktex.agent.scraper",),
    ),
    # ── state/ (ephemeral runtime + server state) ──
    EntrySpec(
        pattern="state/instances/*.json",
        kind="file",
        purpose="Live instance heartbeat + metadata for one running forktex "
        "invocation. Auto-GC'd when stale.",
        sensitivity="config",
        writers=("forktex.runtime.instance",),
    ),
    EntrySpec(
        pattern="state/servers.json",
        kind="file",
        purpose="Cloud server records (IPs, DNS, services).",
        sensitivity="config",
        writers=("forktex.agent.cloud",),
    ),
    EntrySpec(
        pattern="state/agents/history/*.jsonl",
        kind="file",
        purpose="Append-only agent process history (per-process metadata snapshots).",
        sensitivity="config",
        writers=("forktex.agent.engine.state",),
    ),
    EntrySpec(
        pattern="state/agents/memory/nodes/*.md",
        kind="file",
        purpose="Agent working memory (5.2) — observations/notes the agent writes "
        "mid-task, recalled via the knowledge query. Ephemeral (state/): survives a "
        "cache purge but is not committed; promote to knowledge/ to keep.",
        sensitivity="config",
        writers=("forktex.agent.knowledge.memory",),
    ),
    EntrySpec(
        pattern="state/agents/memory/patches/*.md",
        kind="file",
        purpose="Provenance patches for the working-memory doc-space.",
        sensitivity="config",
        writers=("forktex.agent.knowledge.memory",),
    ),
    EntrySpec(
        pattern="state/agents/types.json",
        kind="file",
        purpose="Custom agent type registry.",
        sensitivity="config",
        writers=("forktex.agent.manager",),
    ),
)


# ── Global-scope spec (relative to ``~/.forktex/`` or %APPDATA%/forktex) ─────


GLOBAL_SPEC: tuple[EntrySpec, ...] = (
    EntrySpec(
        pattern="config.toml",
        kind="file",
        purpose="Global CLI defaults (user-edited).",
        sensitivity="config",
    ),
    EntrySpec(
        pattern=".gitignore",
        kind="file",
        purpose="Belt-and-braces gitignore inside ~/.forktex/ against a stray "
        "`git init` at $HOME.",
        writers=("forktex.runtime.lifecycle",),
    ),
    # knowledge/ (host-wide personal lessons — the global layer that composes
    # under every project: docs ← global ← project)
    EntrySpec(
        pattern="knowledge/README.md",
        kind="file",
        purpose="Human orientation for the host-wide knowledge layer.",
        writers=("forktex.agent.knowledge.init",),
    ),
    EntrySpec(
        pattern="knowledge/nodes/*.md",
        kind="file",
        purpose="Host-wide personal knowledge nodes — cross-project lessons + "
        "workspace-governance constraints, queryable from any forktex project.",
        writers=(
            "forktex.agent.knowledge.recycle",
            "forktex.agent.knowledge.rollup",
            "forktex.agent.knowledge.retire",
        ),
    ),
    EntrySpec(
        pattern="knowledge/patches/*.md",
        kind="file",
        purpose="Provenance patches for the host-wide knowledge layer.",
        writers=(
            "forktex.agent.knowledge.recycle",
            "forktex.agent.knowledge.rollup",
            "forktex.agent.knowledge.retire",
        ),
    ),
    # secrets/
    EntrySpec(
        pattern="secrets/cloud.json",
        kind="file",
        purpose="Cloud login: account key, access token, default org/project.",
        sensitivity="secret",
        writers=("forktex.agent.auth.cli",),
    ),
    EntrySpec(
        pattern="secrets/intelligence.json",
        kind="file",
        purpose="Global LLM API key + endpoint.",
        sensitivity="secret",
        writers=("forktex.agent.intelligence.settings",),
    ),
    EntrySpec(
        pattern="secrets/network.json",
        kind="file",
        purpose="Global network JWT + principal email.",
        sensitivity="secret",
        writers=("forktex.agent.network.settings",),
    ),
    # cache/
    EntrySpec(
        pattern="cache/graph.json",
        kind="file",
        purpose="Host-wide source-of-truth graph (all registered projects).",
        writers=("forktex.graph.export.json_writer",),
    ),
    EntrySpec(
        pattern="cache/graph.dsl",
        kind="file",
        purpose="Host-wide Structurizr DSL projection.",
        writers=("forktex.graph.export.dsl_writer",),
    ),
    EntrySpec(
        pattern="cache/graph.html",
        kind="file",
        purpose="Host-wide standalone HTML viewer.",
        writers=("forktex.graph.export.html_writer",),
    ),
    EntrySpec(
        pattern="cache/c4.html",
        kind="file",
        purpose="Host-wide C4 view across registered projects.",
        writers=("forktex.agent.graph.cli",),
    ),
    # state/
    EntrySpec(
        pattern="state/registry.json",
        kind="file",
        purpose="Authoritative index of project roots whose .forktex/ forktex has "
        "touched. The answer to 'what would purge delete'.",
        sensitivity="config",
        writers=("forktex.graph.io_proxy",),
    ),
    EntrySpec(
        pattern="state/repl_history",
        kind="file",
        purpose="Persistent line history for the bare `forktex` REPL.",
        sensitivity="config",
        writers=("forktex.agent.root_loop.menu",),
    ),
    EntrySpec(
        pattern="state/instances/*.json",
        kind="file",
        purpose="Host-wide live instance registry mirror.",
        sensitivity="config",
        writers=("forktex.runtime.instance",),
    ),
)


# ── Public API ────────────────────────────────────────────────────────────


def spec_for(scope: Scope) -> tuple[EntrySpec, ...]:
    return PROJECT_SPEC if scope == "project" else GLOBAL_SPEC


def _normalise(rel: str) -> str:
    return rel.replace("\\", "/").lstrip("/")


def _matches(pattern: str, rel: str) -> bool:
    """Match ``rel`` against ``pattern`` with path-segment semantics.

    ``*`` matches a single path segment (does not cross ``/``); ``**`` matches
    zero or more whole segments. Each segment uses :func:`fnmatch.fnmatchcase`.
    """
    rel = _normalise(rel)
    pat = pattern.replace("\\", "/")
    return _match_segments(pat.split("/"), rel.split("/"))


def _match_segments(pat: list[str], parts: list[str]) -> bool:
    if not pat:
        return not parts
    head, *rest = pat
    if head == "**":
        if not rest:
            return True
        for i in range(len(parts) + 1):
            if _match_segments(rest, parts[i:]):
                return True
        return False
    if not parts:
        return False
    if fnmatch.fnmatchcase(parts[0], head):
        return _match_segments(rest, parts[1:])
    return False


@dataclass(frozen=True)
class MatchResult:
    ok: bool
    spec: EntrySpec | None
    reason: str = ""


def validate_path(scope: Scope, rel_path: str | Path) -> MatchResult:
    """Match a path *relative to* the ``.forktex/`` root against the spec."""
    rel = _normalise(str(rel_path))
    if not rel or rel.startswith(".."):
        return MatchResult(False, None, "path escapes .forktex/ root")
    for spec in spec_for(scope):
        if _matches(spec.pattern, rel):
            return MatchResult(True, spec, "")
    return MatchResult(
        False,
        None,
        f"no spec entry matches {rel!r} under {scope}-scope structure",
    )


def required_entries(scope: Scope) -> tuple[EntrySpec, ...]:
    return tuple(s for s in spec_for(scope) if s.required)


def secret_entries(scope: Scope) -> tuple[EntrySpec, ...]:
    return tuple(s for s in spec_for(scope) if s.sensitivity == "secret")


@dataclass(frozen=True)
class AuditEntry:
    rel_path: str
    status: Literal["matched", "unknown", "missing_required"]
    spec: EntrySpec | None
    reason: str = ""


def audit(scope: Scope, root: Path) -> list[AuditEntry]:
    """Walk the ``.forktex/`` directory under *root* and classify every entry.

    For project scope, *root* is the project root (``.forktex`` is appended). For
    global scope, *root* is ``~/.forktex/`` directly.
    """
    base = root / ".forktex" if scope == "project" else root
    results: list[AuditEntry] = []
    if not base.is_dir():
        for req in required_entries(scope):
            results.append(
                AuditEntry(
                    req.pattern, "missing_required", req, f"{base} does not exist"
                )
            )
        return results

    seen_required: set[str] = set()
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(base).as_posix()
        match = validate_path(scope, rel)
        if match.ok and match.spec is not None:
            results.append(AuditEntry(rel, "matched", match.spec))
            if match.spec.required:
                seen_required.add(match.spec.pattern)
        else:
            results.append(AuditEntry(rel, "unknown", None, match.reason))

    for req in required_entries(scope):
        if req.pattern not in seen_required:
            results.append(
                AuditEntry(
                    req.pattern, "missing_required", req, "required entry absent"
                )
            )
    return results


def discover_nested_forktex_dirs(project_root: Path) -> list[Path]:
    """Return every ``.forktex/`` directory found under *project_root*."""
    skip = {
        ".git",
        ".venv",
        ".pytest_cache",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        ".next",
        ".expo",
    }
    found: list[Path] = []
    for fdir in project_root.rglob(".forktex"):
        if not fdir.is_dir():
            continue
        rel_parts = fdir.relative_to(project_root).parts
        if any(part in skip for part in rel_parts):
            continue
        if rel_parts.count(".forktex") > 1:
            continue
        found.append(fdir)
    return sorted(found)


@dataclass(frozen=True)
class NestedAuditReport:
    forktex_dir: Path
    project_root: Path
    entries: list[AuditEntry]


def audit_tree(project_root: Path) -> list[NestedAuditReport]:
    """Audit *every* ``.forktex/`` reachable under *project_root*."""
    reports: list[NestedAuditReport] = []
    for fdir in discover_nested_forktex_dirs(project_root):
        owner = fdir.parent
        reports.append(
            NestedAuditReport(
                forktex_dir=fdir,
                project_root=owner,
                entries=audit("project", owner),
            )
        )
    return reports
