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

"""CLI-level tests for the new ``forktex graph`` subcommands:
diff, importers, modules, package, recent."""

import json

import pytest
from asyncclick.testing import CliRunner

from forktex.agent.graph.cli import graph as graph_group


pytestmark = [pytest.mark.usefixtures("isolated_home"), pytest.mark.asyncio]


@pytest.fixture
def seeded_project(project_root):
    pkg = project_root / "src" / "proj" / "auth"
    pkg.mkdir(parents=True)
    (project_root / "src" / "proj" / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text("")
    (pkg / "login.py").write_text("import json\nfrom proj.auth import session\n")
    (pkg / "session.py").write_text("import os\n")
    (project_root / "pyproject.toml").write_text(
        '[project]\nname = "proj"\nversion = "0.1.0"\n'
        'dependencies = ["pydantic (>=2)"]\n'
    )
    return project_root


def _runner(monkeypatch, project_root):
    monkeypatch.chdir(project_root)
    return CliRunner()


# ── diff ─────────────────────────────────────────────────────────────────


async def test_diff_two_snapshots(seeded_project, tmp_path, monkeypatch):
    runner = _runner(monkeypatch, seeded_project)
    # Build a "before" snapshot.
    from forktex.graph.build import build_graph
    from forktex.graph.export.json_writer import render_json
    from forktex.graph.scopes import ProjectScope

    before_path = tmp_path / "before.json"
    before_path.write_text(render_json(build_graph(ProjectScope(seeded_project))))

    # Mutate the project — add a new module.
    (seeded_project / "src" / "proj" / "auth" / "permissions.py").write_text(
        "import os\n"
    )

    after_path = tmp_path / "after.json"
    after_path.write_text(render_json(build_graph(ProjectScope(seeded_project))))

    result = await runner.invoke(
        graph_group, ["diff", str(before_path), str(after_path), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    added_names = {n.get("name") for n in data["nodes"]["added"]}
    assert "permissions" in added_names


async def test_diff_against_live_graph(seeded_project, tmp_path, monkeypatch):
    runner = _runner(monkeypatch, seeded_project)
    from forktex.graph.build import build_graph
    from forktex.graph.export.json_writer import render_json
    from forktex.graph.scopes import ProjectScope

    before_path = tmp_path / "before.json"
    before_path.write_text(render_json(build_graph(ProjectScope(seeded_project))))

    # Mutate live tree.
    (seeded_project / "src" / "proj" / "auth" / "fresh.py").write_text("\n")

    result = await runner.invoke(graph_group, ["diff", str(before_path)])
    assert result.exit_code == 0, result.output
    assert "+" in result.output  # tree-rendered diff


async def test_diff_missing_file(monkeypatch, project_root):
    runner = _runner(monkeypatch, project_root)
    result = await runner.invoke(graph_group, ["diff", "/no/such/file.json"])
    assert result.exit_code != 0


# ── importers / modules / package / recent ───────────────────────────────


async def test_importers_intra_project(seeded_project, monkeypatch):
    runner = _runner(monkeypatch, seeded_project)
    result = await runner.invoke(graph_group, ["importers", "proj.auth.session"])
    assert result.exit_code == 0, result.output
    assert "proj.auth.login" in result.output


async def test_importers_no_match(seeded_project, monkeypatch):
    runner = _runner(monkeypatch, seeded_project)
    result = await runner.invoke(graph_group, ["importers", "nonexistent.module"])
    assert result.exit_code == 0
    assert "no modules import" in result.output


async def test_package_locates_path(seeded_project, monkeypatch):
    runner = _runner(monkeypatch, seeded_project)
    result = await runner.invoke(graph_group, ["package", "src/proj/auth/login.py"])
    assert result.exit_code == 0, result.output
    assert "proj" in result.output


async def test_modules_glob(seeded_project, monkeypatch):
    runner = _runner(monkeypatch, seeded_project)
    result = await runner.invoke(graph_group, ["modules", "*login*"])
    assert result.exit_code == 0, result.output
    assert "login" in result.output


async def test_modules_no_match(seeded_project, monkeypatch):
    runner = _runner(monkeypatch, seeded_project)
    result = await runner.invoke(graph_group, ["modules", "*completely_absent*"])
    assert result.exit_code == 0
    assert "no modules" in result.output


async def test_recent_empty_window(seeded_project, monkeypatch):
    runner = _runner(monkeypatch, seeded_project)
    # 0-hour window → nothing recorded yet at this very second.
    result = await runner.invoke(graph_group, ["recent", "--hours", "0"])
    assert result.exit_code == 0
