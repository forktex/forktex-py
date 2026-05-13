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

"""Canonical structure of ``~/.forktex/`` (global) and ``<root>/.forktex/``
(per-project).

This spec is the legal + tool-integrity contract for ForkTex's on-disk
footprint. Every file or directory ForkTex creates inside a ``.forktex``
directory must match an :class:`EntrySpec` registered here. Writes that
don't match are rejected by :func:`forktex.graph.io_proxy.tracked_write`
(or, in lenient mode, surfaced as audit warnings).

Why strict:

* **Auditability** — when an operator asks "what does this project
  store under `.forktex/`?" or "purge everything", we can answer
  authoritatively from this spec instead of scanning a free-for-all
  directory.
* **Tool integrity** — anything outside the spec is either a bug or an
  unauthorised side effect; both deserve to be loud.

The spec is paired with :mod:`forktex_cloud.paths` (the V1 path module).
Where ``paths.py`` provides ``Path`` factories, this module classifies them.
The two MUST agree; ``tests/test_structure_contract.py`` validates that
every ``paths.py`` factory output matches a spec entry.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from forktex.graph.models import Scope


EntryKind = Literal["file", "dir"]
Sensitivity = Literal["public", "config", "secret"]


@dataclass(frozen=True)
class EntrySpec:
    """A single canonical entry inside ``.forktex/`` (project or global).

    ``pattern`` is a relative-to-``.forktex/`` path expression using
    ``fnmatch`` semantics (``*`` matches one segment, ``**`` matches any).
    Variable segments (env, agent_id, service_id, domain) are matched as
    ``*`` glob wildcards.
    """

    pattern: str
    kind: EntryKind
    purpose: str
    sensitivity: Sensitivity = "public"
    required: bool = False
    writers: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""


# ── Project-scope spec (relative to ``<root>/.forktex/``) ────────────────


PROJECT_SPEC: tuple[EntrySpec, ...] = (
    # Schema marker — the only file committed to git.
    EntrySpec(
        pattern=".version",
        kind="file",
        purpose="Schema version marker; the only file inside .forktex/ "
        "committed to git so the layout version travels with the repo.",
        sensitivity="public",
        required=True,
        writers=("forktex_cloud.paths.write_schema_version",),
    ),
    # Defence-in-depth gitignore inside the .forktex/ directory itself.
    EntrySpec(
        pattern=".gitignore",
        kind="file",
        purpose="Belt-and-braces gitignore inside .forktex/ — protects "
        "secrets even if the project-root .gitignore loses the canonical "
        "block. Auto-generated; not user-editable.",
        sensitivity="public",
        required=True,
        writers=("forktex.runtime.lifecycle",),
    ),
    # Live-instance heartbeat records.
    EntrySpec(
        pattern="instances/*.json",
        kind="file",
        purpose="Live instance heartbeat + metadata for one running "
        "forktex invocation. Auto-GC'd when stale.",
        sensitivity="config",
        writers=("forktex.runtime.instance",),
    ),
    # Project-scope config files.
    EntrySpec(
        pattern="config.json",
        kind="file",
        purpose="Project-level forktex settings.",
        sensitivity="config",
    ),
    EntrySpec(
        pattern="intelligence.json",
        kind="file",
        purpose="Per-project LLM endpoint and key override.",
        sensitivity="secret",
        writers=("forktex.agent.intelligence.settings",),
    ),
    EntrySpec(
        pattern="network.json",
        kind="file",
        purpose="Per-project network JWT and endpoint.",
        sensitivity="secret",
        writers=("forktex.agent.network.settings",),
    ),
    EntrySpec(
        pattern="cloud/config.json",
        kind="file",
        purpose="Cloud workspace selection (org/project/env) — canonical V1 path.",
        sensitivity="config",
        writers=("forktex.agent.cloud.settings",),
    ),
    EntrySpec(
        pattern="cloud.json",
        kind="file",
        purpose="Cloud workspace selection (legacy top-level path; "
        "still written by forktex.agent.cloud.settings).",
        sensitivity="config",
        writers=("forktex.agent.cloud.settings",),
    ),
    # Compose + observability.
    EntrySpec(
        pattern="docker-compose.*.yml",
        kind="file",
        purpose="Generated docker-compose for one of dev/staging/prod.",
        sensitivity="config",
        writers=("forktex.agent.cloud.up",),
    ),
    EntrySpec(
        pattern="observability/**",
        kind="dir",
        purpose="Generated Loki/Promtail configs.",
        sensitivity="config",
        writers=("forktex.agent.cloud.up",),
    ),
    # Vault — encrypted secrets per environment.
    EntrySpec(
        pattern="vault/*/secrets.enc",
        kind="file",
        purpose="Fernet-encrypted secrets blob for one environment.",
        sensitivity="secret",
        writers=("forktex.agent.cloud",),
    ),
    # State.
    EntrySpec(
        pattern="state/servers.json",
        kind="file",
        purpose="Cloud server records (IPs, DNS, services).",
        sensitivity="config",
        writers=("forktex.agent.cloud",),
    ),
    EntrySpec(
        pattern="state/keys/*.key",
        kind="file",
        purpose="Per-server SSH private key.",
        sensitivity="secret",
        writers=("forktex.agent.cloud",),
    ),
    # Generated artifacts.
    EntrySpec(
        pattern="generated/**",
        kind="dir",
        purpose="Generated gateway/balancer/compute configuration.",
        sensitivity="config",
        writers=("forktex.agent.cloud.up",),
    ),
    EntrySpec(
        pattern="data/*/**",
        kind="dir",
        purpose="Per-service runtime data (mounted into containers).",
        sensitivity="config",
    ),
    EntrySpec(
        pattern="ssl/custom/**",
        kind="dir",
        purpose="User-supplied SSL certificates.",
        sensitivity="secret",
    ),
    EntrySpec(
        pattern="backups/**",
        kind="dir",
        purpose="Database snapshots (pg_dump etc.) produced by the cloud "
        "SDK's deploy hooks or `forktex cloud backup`. Layout: "
        "backups/<YYYYMMDD-HHMMSS>/<service>.sql.gz.",
        sensitivity="secret",
        writers=("forktex_cloud.bridge.local_compose", "forktex.agent.cloud"),
    ),
    EntrySpec(
        pattern="bootstrap.json",
        kind="file",
        purpose="One-shot bootstrap manifest written by `forktex cloud up` "
        "describing the local environment topology.",
        sensitivity="config",
        writers=("forktex_cloud.bridge.local_compose",),
    ),
    # FSD evidence (the canonical architecture artifacts now live at
    # ``.forktex/graph.{json,dsl,html}`` — see entries below).
    EntrySpec(
        pattern="fsd/evidence/**",
        kind="dir",
        purpose="FSD check/report evidence outputs.",
        sensitivity="public",
        writers=("forktex.agent.fsd.check", "forktex.agent.fsd.report"),
    ),
    # Agents.
    EntrySpec(
        pattern="agents/history/*.jsonl",
        kind="file",
        purpose="Append-only agent conversation history.",
        sensitivity="config",
        writers=("forktex.agent.session", "forktex.agent.state"),
    ),
    EntrySpec(
        pattern="agents/types.json",
        kind="file",
        purpose="Custom agent type registry.",
        sensitivity="config",
        writers=("forktex.agent.manager",),
    ),
    EntrySpec(
        pattern="conversation_*.json",
        kind="file",
        purpose="Per-session conversation history persisted by StateManager.",
        sensitivity="config",
        writers=("forktex.core.state",),
    ),
    # Scraper.
    EntrySpec(
        pattern="scraper/truths/*.json",
        kind="file",
        purpose="Per-domain scraping knowledge.",
        sensitivity="public",
        writers=("forktex.agent.scraper.truths",),
    ),
    EntrySpec(
        pattern="scraper/output/**",
        kind="dir",
        purpose="Structured scrape exports.",
        sensitivity="public",
        writers=("forktex.agent.scraper",),
    ),
    # Project-scope graph exports — NEW.
    EntrySpec(
        pattern="graph.json",
        kind="file",
        purpose="Source-of-truth multi-edge project graph (canonical body).",
        sensitivity="public",
        required=False,
        writers=("forktex.graph.export.json_writer",),
    ),
    EntrySpec(
        pattern="graph.dsl",
        kind="file",
        purpose="Structurizr DSL projection of the project graph.",
        sensitivity="public",
        writers=("forktex.graph.export.dsl_writer",),
    ),
    EntrySpec(
        pattern="graph.html",
        kind="file",
        purpose="Standalone HTML viewer with the graph payload embedded.",
        sensitivity="public",
        writers=("forktex.graph.export.html_writer",),
    ),
    EntrySpec(
        pattern="c4.html",
        kind="file",
        purpose="Per-platform C4 view (replaces legacy arch HTML reports).",
        sensitivity="public",
        writers=("forktex.agent.graph.cli",),
    ),
    # Manual atom outputs (`forktex manual build` / `make manual`).
    EntrySpec(
        pattern="manual/**",
        kind="dir",
        purpose="Generated architecture + AI manual bundle "
        "(manual_arch.html, manual_graph.html, manual_agents.json, "
        "manual_bundle.json).",
        sensitivity="public",
        required=False,
        writers=("forktex.agent.manual.cli",),
    ),
)


# ── Global-scope spec (relative to ``~/.forktex/`` or %APPDATA%/forktex) ─


GLOBAL_SPEC: tuple[EntrySpec, ...] = (
    EntrySpec(
        pattern="config.toml",
        kind="file",
        purpose="Global CLI defaults (user-edited).",
        sensitivity="config",
    ),
    EntrySpec(
        pattern="cloud.json",
        kind="file",
        purpose="Cloud login: account key, access token, default org/project.",
        sensitivity="secret",
        writers=("forktex.agent.auth.cli",),
    ),
    EntrySpec(
        pattern="intelligence.json",
        kind="file",
        purpose="Global LLM API key + endpoint.",
        sensitivity="secret",
        writers=("forktex.agent.intelligence.settings",),
    ),
    EntrySpec(
        pattern="network.json",
        kind="file",
        purpose="Global network JWT + principal email.",
        sensitivity="secret",
        writers=("forktex.agent.network.settings",),
    ),
    # Persistent REPL input history (prompt_toolkit FileHistory).
    EntrySpec(
        pattern="repl_history",
        kind="file",
        purpose="Persistent line history for the bare `forktex` REPL "
        "(menu PromptSession + chat input buffer).",
        sensitivity="config",
        required=False,
        writers=("forktex.agent.root_loop.menu",),
    ),
    # Registry — NEW. Maintained by io_proxy.tracked_write.
    EntrySpec(
        pattern="registry.json",
        kind="file",
        purpose="Authoritative index of project roots whose .forktex/ "
        "directories ForkTex has touched. Drives `forktex graph --scope os` "
        "and is the answer to 'what would purge delete'.",
        sensitivity="config",
        required=False,
        writers=("forktex.graph.io_proxy",),
    ),
    # Global-scope graph exports — NEW.
    EntrySpec(
        pattern="graph.json",
        kind="file",
        purpose="Host-wide source-of-truth graph (covers all registered projects).",
        sensitivity="public",
        writers=("forktex.graph.export.json_writer",),
    ),
    EntrySpec(
        pattern="graph.dsl",
        kind="file",
        purpose="Host-wide Structurizr DSL projection.",
        sensitivity="public",
        writers=("forktex.graph.export.dsl_writer",),
    ),
    EntrySpec(
        pattern="graph.html",
        kind="file",
        purpose="Host-wide standalone HTML viewer.",
        sensitivity="public",
        writers=("forktex.graph.export.html_writer",),
    ),
    EntrySpec(
        pattern="c4.html",
        kind="file",
        purpose="Host-wide C4 view across registered projects.",
        sensitivity="public",
        writers=("forktex.agent.graph.cli",),
    ),
    EntrySpec(
        pattern="instances/*.json",
        kind="file",
        purpose="Host-wide live instance registry mirror — one record "
        "per running forktex invocation across all projects.",
        sensitivity="config",
        writers=("forktex.runtime.instance",),
    ),
    EntrySpec(
        pattern=".gitignore",
        kind="file",
        purpose="Belt-and-braces gitignore inside ~/.forktex/. The global "
        "directory is generally outside any git tree, but a stray "
        "`git init` at $HOME shouldn't slurp our secrets.",
        sensitivity="public",
        writers=("forktex.runtime.lifecycle",),
    ),
)


# ── Public API ────────────────────────────────────────────────────────────


def spec_for(scope: Scope) -> tuple[EntrySpec, ...]:
    return PROJECT_SPEC if scope == "project" else GLOBAL_SPEC


def _normalise(rel: str) -> str:
    return rel.replace("\\", "/").lstrip("/")


def _matches(pattern: str, rel: str) -> bool:
    """Match ``rel`` against ``pattern`` with path-segment semantics.

    ``*`` matches a single path segment (does not cross ``/``). ``**``
    matches zero or more whole segments. Each segment is matched with
    :func:`fnmatch.fnmatchcase`, so ``*.json``, ``server-*.key`` etc. work.
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
    """Match a path *relative to* the ``.forktex/`` root against the spec.

    ``rel_path`` must be relative (no leading ``/`` or ``.forktex/`` prefix).
    Returns the first matching :class:`EntrySpec` or a structured failure.
    """

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

    For project scope, *root* is the project root (the function appends
    ``.forktex``). For global scope, *root* is ``~/.forktex/`` directly.
    """

    if scope == "project":
        base = root / ".forktex"
    else:
        base = root
    results: list[AuditEntry] = []
    if not base.is_dir():
        for req in required_entries(scope):
            results.append(
                AuditEntry(
                    rel_path=req.pattern,
                    status="missing_required",
                    spec=req,
                    reason=f"{base} does not exist",
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
                    rel_path=req.pattern,
                    status="missing_required",
                    spec=req,
                    reason="required entry absent",
                )
            )
    return results


def discover_nested_forktex_dirs(project_root: Path) -> list[Path]:
    """Return every ``.forktex/`` directory found under *project_root*.

    Skips ``.forktex`` directories that are themselves contained inside
    another ``.forktex`` (which the structure spec disallows anyway), and
    skips heavy/unrelated trees (.git, node_modules, etc.).
    """
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
        # Skip if a parent segment is itself a SKIP_DIRS member or a
        # nested .forktex (defence in depth).
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
    """Audit *every* ``.forktex/`` reachable under *project_root*.

    Each nested ``.forktex/`` is its own footprint and gets its own
    report, so a monorepo with N nested forktex projects yields N audits.
    """
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
