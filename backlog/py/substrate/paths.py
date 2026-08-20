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

"""Canonical filesystem layout for the forktex workspace.

forktex-py is the **sole filesystem authority** — every subsystem that reads or
writes under ``.forktex/`` (project scope) or ``~/.forktex/`` (user/OS scope)
goes through this module. The libraries (forktex_core, forktex_cloud, …) deal in
pure data and never name ``.forktex``. See ``standard.forktex-architecture``.

The layout is bucketed by **lifecycle**, identical at both scopes:

* ``knowledge/`` — committed source of truth (recycled lessons + notes).
* ``secrets/``   — credentials, vault, keys, env — never committed, never shared.
* ``cache/``     — generated + reproducible artefacts (delete = rebuild).
* ``state/``     — ephemeral runtime + server state.

Root markers ``.version`` / ``.gitignore`` / ``config.json`` sit at the
``.forktex/`` root. Cross-platform: returns ``Path`` always; project scope is
``.forktex`` (lowercase); user scope is ``~/.forktex`` on POSIX and
``%APPDATA%/forktex`` on Windows.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Bump when the on-disk layout changes incompatibly. ``2`` introduced the
#: bucketed layout (knowledge/secrets/cache/state). Written to ``.forktex/.version``.
SCHEMA_VERSION = 2

#: Directory name at project scope.
PROJECT_DIRNAME = ".forktex"

#: Directory name at user/OS scope (stripped of leading dot on Windows).
_USER_DIRNAME_POSIX = ".forktex"
_USER_DIRNAME_WINDOWS = "forktex"

#: Lifecycle buckets (subdirectories under the ``.forktex/`` root).
KNOWLEDGE = "knowledge"
SECRETS = "secrets"
CACHE = "cache"
STATE = "state"

#: Marker comment used to idempotently detect the canonical ``.gitignore`` block.
#: Everything under ``.forktex/`` is ignored except the committed ``knowledge/``
#: bucket and the ``.version`` marker.
_GITIGNORE_MARKER = "# forktex — only .forktex/knowledge and .version are committed"
_GITIGNORE_BLOCK = f"""
{_GITIGNORE_MARKER}
.forktex/**
!.forktex/.version
!.forktex/knowledge/
!.forktex/knowledge/**
"""


# ── Project-scope roots + buckets ────────────────────────────────────────────


def project_dir(root: Path) -> Path:
    return root / PROJECT_DIRNAME


def version_file(root: Path) -> Path:
    return project_dir(root) / ".version"


def project_config_file(root: Path) -> Path:
    return project_dir(root) / "config.json"


def knowledge_dir(root: Path) -> Path:
    return project_dir(root) / KNOWLEDGE


def secrets_dir(root: Path) -> Path:
    return project_dir(root) / SECRETS


def cache_dir(root: Path) -> Path:
    return project_dir(root) / CACHE


def state_dir(root: Path) -> Path:
    return project_dir(root) / STATE


# ── knowledge/ (committed) ───────────────────────────────────────────────────


def knowledge_nodes_dir(root: Path) -> Path:
    return knowledge_dir(root) / "nodes"


def knowledge_patches_dir(root: Path) -> Path:
    return knowledge_dir(root) / "patches"


def knowledge_readme(root: Path) -> Path:
    return knowledge_dir(root) / "README.md"


# ── secrets/ (never committed) ───────────────────────────────────────────────


def project_intelligence_file(root: Path) -> Path:
    return secrets_dir(root) / "intelligence.json"


def project_network_file(root: Path) -> Path:
    return secrets_dir(root) / "network.json"


def project_cloud_file(root: Path) -> Path:
    return secrets_dir(root) / "cloud" / "config.json"


def vault_dir(root: Path, env: str) -> Path:
    return secrets_dir(root) / "vault" / env


def vault_secrets_file(root: Path, env: str) -> Path:
    return vault_dir(root, env) / "secrets.enc"


def server_keys_dir(root: Path) -> Path:
    return secrets_dir(root) / "keys"


def env_file(root: Path) -> Path:
    return secrets_dir(root) / ".env"


def custom_ssl_dir(root: Path) -> Path:
    return secrets_dir(root) / "ssl" / "custom"


# ── cache/ (regenerable) ─────────────────────────────────────────────────────


def compose_path(root: Path, env: str) -> Path:
    return cache_dir(root) / f"docker-compose.{env}.yml"


def observability_dir(root: Path) -> Path:
    return cache_dir(root) / "observability"


def generated_dir(root: Path) -> Path:
    return cache_dir(root) / "generated"


def data_dir(root: Path, service_id: str) -> Path:
    return cache_dir(root) / "data" / service_id


def db_build_dir(root: Path) -> Path:
    return cache_dir(root) / "db"


def redis_build_dir(root: Path) -> Path:
    return cache_dir(root) / "redis"


def backups_dir(root: Path) -> Path:
    return cache_dir(root) / "backups"


def bootstrap_file(root: Path) -> Path:
    return cache_dir(root) / "bootstrap.json"


def fsd_evidence_dir(root: Path) -> Path:
    return cache_dir(root) / "fsd" / "evidence"


def graph_json(root: Path) -> Path:
    return cache_dir(root) / "graph.json"


def graph_dsl(root: Path) -> Path:
    return cache_dir(root) / "graph.dsl"


def graph_html(root: Path) -> Path:
    return cache_dir(root) / "graph.html"


def c4_html(root: Path) -> Path:
    return cache_dir(root) / "c4.html"


def manual_dir(root: Path) -> Path:
    return cache_dir(root) / "manual"


def scraper_truths_dir(root: Path) -> Path:
    return cache_dir(root) / "scraper" / "truths"


def scraper_truths_file(root: Path, domain: str) -> Path:
    return scraper_truths_dir(root) / f"{domain}.json"


def scraper_output_dir(root: Path) -> Path:
    return cache_dir(root) / "scraper" / "output"


# ── state/ (ephemeral) ───────────────────────────────────────────────────────


def instances_dir(root: Path) -> Path:
    return state_dir(root) / "instances"


def servers_json(root: Path) -> Path:
    return state_dir(root) / "servers.json"


def agents_history_dir(root: Path) -> Path:
    return state_dir(root) / "agents" / "history"


def agents_history_file(root: Path, agent_id: str) -> Path:
    return agents_history_dir(root) / f"{agent_id}.jsonl"


def agents_types_file(root: Path) -> Path:
    return state_dir(root) / "agents" / "types.json"


def agent_memory_dir(root: Path) -> Path:
    """Working-memory doc-space (5.2) — ephemeral agent notes under ``state/``."""
    return state_dir(root) / "agents" / "memory"


# ── User/OS-scope paths (same buckets, host-wide) ────────────────────────────


def global_dir() -> Path:
    """The global forktex directory, cross-platform.

    POSIX: ``~/.forktex/``. Windows: ``%APPDATA%/forktex/`` (roaming profile).
    """
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home()
        return base / _USER_DIRNAME_WINDOWS
    return Path.home() / _USER_DIRNAME_POSIX


def global_config_file() -> Path:
    return global_dir() / "config.toml"


def global_secrets_dir() -> Path:
    return global_dir() / SECRETS


def global_cache_dir() -> Path:
    return global_dir() / CACHE


def global_state_dir() -> Path:
    return global_dir() / STATE


def global_knowledge_dir() -> Path:
    return global_dir() / KNOWLEDGE


def global_knowledge_nodes_dir() -> Path:
    return global_knowledge_dir() / "nodes"


def global_knowledge_patches_dir() -> Path:
    return global_knowledge_dir() / "patches"


def global_cloud_file() -> Path:
    return global_secrets_dir() / "cloud.json"


def global_intelligence_file() -> Path:
    return global_secrets_dir() / "intelligence.json"


def global_network_file() -> Path:
    return global_secrets_dir() / "network.json"


def global_registry_file() -> Path:
    return global_state_dir() / "registry.json"


def global_repl_history() -> Path:
    return global_state_dir() / "repl_history"


def global_instances_dir() -> Path:
    return global_state_dir() / "instances"


def global_graph_json() -> Path:
    return global_cache_dir() / "graph.json"


def global_graph_dsl() -> Path:
    return global_cache_dir() / "graph.dsl"


def global_graph_html() -> Path:
    return global_cache_dir() / "graph.html"


def global_c4_html() -> Path:
    return global_cache_dir() / "c4.html"


# ── Lifecycle helpers ────────────────────────────────────────────────────────


def ensure_project_dirs(root: Path) -> None:
    """Create ``.forktex/`` under *root*, write the schema marker, and ensure the
    project ``.gitignore`` carries the canonical forktex block. Idempotent.
    """
    project_dir(root).mkdir(parents=True, exist_ok=True)
    write_schema_version(root)
    _ensure_gitignore_block(root)


def ensure_global_dir() -> None:
    """Create the user/OS-scope forktex dir with secure permissions on POSIX."""
    gdir = global_dir()
    gdir.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        try:
            gdir.chmod(0o700)
        except OSError:
            pass


def read_schema_version(root: Path) -> int | None:
    """Return the on-disk ``.forktex/.version`` as int, or ``None`` if missing."""
    vf = version_file(root)
    if not vf.is_file():
        return None
    try:
        return int(vf.read_text().strip())
    except (ValueError, OSError):
        return None


def write_schema_version(root: Path) -> None:
    """Write ``SCHEMA_VERSION`` to ``.forktex/.version`` if not already correct."""
    vf = version_file(root)
    if read_schema_version(root) == SCHEMA_VERSION:
        return
    vf.parent.mkdir(parents=True, exist_ok=True)
    vf.write_text(f"{SCHEMA_VERSION}\n")


def _ensure_gitignore_block(root: Path) -> None:
    gi = root / ".gitignore"
    if gi.is_file():
        existing = gi.read_text()
        if _GITIGNORE_MARKER in existing:
            return
        if not existing.endswith("\n"):
            existing += "\n"
        gi.write_text(existing + _GITIGNORE_BLOCK)
    else:
        gi.write_text(_GITIGNORE_BLOCK.lstrip("\n"))


__all__ = [
    "SCHEMA_VERSION",
    "PROJECT_DIRNAME",
    "KNOWLEDGE",
    "SECRETS",
    "CACHE",
    "STATE",
    # roots + buckets
    "project_dir",
    "version_file",
    "project_config_file",
    "knowledge_dir",
    "secrets_dir",
    "cache_dir",
    "state_dir",
    # knowledge/
    "knowledge_nodes_dir",
    "knowledge_patches_dir",
    "knowledge_readme",
    # secrets/
    "project_intelligence_file",
    "project_network_file",
    "project_cloud_file",
    "vault_dir",
    "vault_secrets_file",
    "server_keys_dir",
    "env_file",
    "custom_ssl_dir",
    # cache/
    "compose_path",
    "observability_dir",
    "generated_dir",
    "data_dir",
    "db_build_dir",
    "redis_build_dir",
    "backups_dir",
    "bootstrap_file",
    "fsd_evidence_dir",
    "graph_json",
    "graph_dsl",
    "graph_html",
    "c4_html",
    "manual_dir",
    "scraper_truths_dir",
    "scraper_truths_file",
    "scraper_output_dir",
    # state/
    "instances_dir",
    "servers_json",
    "agent_memory_dir",
    "agents_history_dir",
    "agents_history_file",
    "agents_types_file",
    # global
    "global_dir",
    "global_config_file",
    "global_secrets_dir",
    "global_cache_dir",
    "global_state_dir",
    "global_knowledge_dir",
    "global_knowledge_nodes_dir",
    "global_knowledge_patches_dir",
    "global_cloud_file",
    "global_intelligence_file",
    "global_network_file",
    "global_registry_file",
    "global_repl_history",
    "global_instances_dir",
    "global_graph_json",
    "global_graph_dsl",
    "global_graph_html",
    "global_c4_html",
    # lifecycle
    "ensure_project_dirs",
    "ensure_global_dir",
    "read_schema_version",
    "write_schema_version",
]
