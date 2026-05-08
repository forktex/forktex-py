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

"""Tests for the `forktex agents ground` AGENTS.md regenerator."""

import json
from pathlib import Path

from forktex.agent.commands.ground import (
    _AGENTS_HEADER,
    _is_autogen,
    _render_agents_md,
)


def _make_repo(workspace: Path, name: str, **manifest_extras) -> Path:
    repo = workspace / name
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / FAKE_GIT_FILE).write_text("fake repo for tests\n", encoding="utf-8")
    base = {
        "manifestVersion": "1.1.0",
        "name": name,
        "version": "0.1.0",
        "description": "Demo project",
        "fsd": {
            "version": "1.1.0",
            "profiles": ["workspace/python-monorepo"],
            "targetLevel": "L3",
            "atoms": {},
        },
        "packages": [
            {
                "name": name,
                "path": ".",
                "version": "0.1.0",
                "publishable": True,
                "language": "python",
            }
        ],
    }
    base.update(manifest_extras)
    (repo / "forktex.json").write_text(json.dumps(base), encoding="utf-8")
    return repo


FAKE_GIT_FILE = "HEAD"


def test_render_agents_md_minimal_repo(tmp_path):
    workspace = tmp_path
    _make_repo(workspace, "demo")
    repo_info = {
        "name": "demo",
        "has_forktex_json": True,
        "has_makefile": False,
        "services": [],
    }

    body = _render_agents_md(repo_info, workspace)

    assert body.startswith(_AGENTS_HEADER)
    assert "# demo" in body
    assert "Demo project" in body
    assert "target FSD level: L3" in body
    assert "profiles: workspace/python-monorepo" in body
    assert "## Packages" in body
    assert "demo (python)" in body


def test_render_agents_md_includes_make_targets(tmp_path):
    workspace = tmp_path
    repo = _make_repo(workspace, "demo")
    (repo / "Makefile").write_text(
        "format: ## Format the code\n"
        "\truff format src/\n"
        "lint: ## Lint the code\n"
        "\truff check src/\n"
        "test: ## Run tests\n"
        "\tpytest\n",
        encoding="utf-8",
    )
    repo_info = {
        "name": "demo",
        "has_forktex_json": True,
        "has_makefile": True,
        "services": [],
    }

    body = _render_agents_md(repo_info, workspace)

    assert "## Make targets" in body
    assert "format" in body
    assert "lint" in body
    assert "test" in body


def test_render_agents_md_includes_services(tmp_path):
    workspace = tmp_path
    _make_repo(workspace, "demo")
    repo_info = {
        "name": "demo",
        "has_forktex_json": True,
        "has_makefile": False,
        "services": ["api", "db", "redis"],
    }

    body = _render_agents_md(repo_info, workspace)

    assert "cloud services: api, db, redis" in body


def test_is_autogen_recognises_marker(tmp_path):
    p = tmp_path / "AGENTS.md"
    p.write_text(f"{_AGENTS_HEADER}\n\n# demo\n", encoding="utf-8")
    assert _is_autogen(p) is True


def test_is_autogen_rejects_handauthored(tmp_path):
    p = tmp_path / "AGENTS.md"
    p.write_text("# demo\n\nHand-authored briefing.\n", encoding="utf-8")
    assert _is_autogen(p) is False


def test_is_autogen_handles_blank_lines_before_marker(tmp_path):
    p = tmp_path / "AGENTS.md"
    p.write_text(
        f"\n\n{_AGENTS_HEADER}\n\n# demo\n",
        encoding="utf-8",
    )
    assert _is_autogen(p) is True


def test_is_autogen_handles_missing_file(tmp_path):
    p = tmp_path / "missing.md"
    assert _is_autogen(p) is False


def test_render_agents_md_without_manifest_data(tmp_path):
    """A repo with `has_forktex_json=True` but the file missing should still
    render a non-empty body without crashing."""
    workspace = tmp_path
    repo_dir = workspace / "demo"
    repo_dir.mkdir()
    repo_info = {
        "name": "demo",
        "has_forktex_json": False,
        "has_makefile": False,
        "services": [],
    }

    body = _render_agents_md(repo_info, workspace)

    assert _AGENTS_HEADER in body
    assert "# demo" in body
    assert "(no FSD or cloud manifest declared)" in body


def test_render_agents_md_caps_atom_list(tmp_path):
    """When more than 15 atoms are declared, the rendering shows only the
    first 15 and notes how many more were truncated."""
    workspace = tmp_path
    atoms = {f"atom-{i:02d}": {"commands": [f"echo atom-{i:02d}"]} for i in range(20)}
    _make_repo(
        workspace,
        "demo",
        fsd={
            "version": "1.1.0",
            "profiles": ["workspace/python-monorepo"],
            "targetLevel": "L3",
            "atoms": atoms,
        },
    )
    repo_info = {
        "name": "demo",
        "has_forktex_json": True,
        "has_makefile": False,
        "services": [],
    }

    body = _render_agents_md(repo_info, workspace)

    assert "## FSD atom overrides" in body
    assert "atom-00" in body
    assert "_…and 5 more_" in body
