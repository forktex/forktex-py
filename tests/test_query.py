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

"""Tests for forktex.graph.query primitives."""

import pytest

from forktex.graph.build import build_graph
from forktex.graph.query import (
    bust_cache,
    find_modules,
    find_package_by_path,
    fsd_level_of_package,
    get_project_metadata,
    list_domains,
    list_modules_in_domain,
    list_packages,
    session_graph,
    validate_path,
)
from forktex.graph.scopes import ProjectScope


pytestmark = pytest.mark.usefixtures("isolated_home")


def _seed_simple_python_project(root):
    """Add a `src/proj/auth/{login,session}.py` tree so the graph has shape."""
    pkg = root / "src" / "proj" / "auth"
    pkg.mkdir(parents=True)
    (root / "src" / "proj" / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text("")
    (pkg / "login.py").write_text("import json\nfrom proj.auth import session\n")
    (pkg / "session.py").write_text("import os\n")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "proj"\nversion = "0.1.0"\n'
        'dependencies = ["httpx (>=0.27)", "pydantic (>=2)"]\n'
    )


# ── project.py ────────────────────────────────────────────────────────────


def test_get_project_metadata(project_root):
    _seed_simple_python_project(project_root)
    bust_cache()
    g = build_graph(ProjectScope(project_root))
    meta = get_project_metadata(g)
    assert meta.name == "proj"
    assert meta.package_count >= 1
    assert meta.domain_count >= 1
    # auth domain has __init__/login/session = 3 modules
    assert meta.module_count >= 3
    assert meta.library_count >= 2


def test_list_packages_and_domains(project_root):
    _seed_simple_python_project(project_root)
    bust_cache()
    g = build_graph(ProjectScope(project_root))
    pkgs = list_packages(g)
    assert len(pkgs) >= 1
    pkg = pkgs[0]
    assert pkg.has_makefile is False
    domains = list_domains(g, package_id=pkg.id)
    assert any(d.name == "auth" for d in domains)


def test_find_package_by_path(project_root):
    _seed_simple_python_project(project_root)
    bust_cache()
    g = build_graph(ProjectScope(project_root))
    match = find_package_by_path(g, "src/myapp/auth/login.py")
    assert match is not None


def test_list_modules_in_domain(project_root):
    _seed_simple_python_project(project_root)
    bust_cache()
    g = build_graph(ProjectScope(project_root))
    auth = next(d for d in list_domains(g) if d.name == "auth")
    modules = list_modules_in_domain(g, auth.id)
    names = {m.name for m in modules}
    assert {"login", "session"} <= names


def test_find_modules_glob(project_root):
    _seed_simple_python_project(project_root)
    bust_cache()
    g = build_graph(ProjectScope(project_root))
    matches = find_modules(g, "*login*")
    assert any(m.name == "login" for m in matches)
    matches_dotted = find_modules(g, "proj.auth.*")
    assert any(m.dotted_name == "proj.auth.session" for m in matches_dotted)


# ── deps.py ──────────────────────────────────────────────────────────────


def test_packages_depending_on_library(project_root):
    _seed_simple_python_project(project_root)
    bust_cache()
    from forktex.graph.query.deps import packages_depending_on

    g = build_graph(ProjectScope(project_root))
    matches = packages_depending_on(g, "pydantic")
    assert len(matches) >= 1


def test_imports_of_module(project_root):
    _seed_simple_python_project(project_root)
    bust_cache()
    from forktex.graph.query.deps import imports_of_module

    g = build_graph(ProjectScope(project_root))
    login = next(m for m in g.by_kind("module") if m.name == "login")
    edges = imports_of_module(g, login.id)
    target_names = {e.target_name for e in edges}
    # `import json` resolves to external_dep; the relative-import
    # path resolves to in-project session module.
    assert any("json" in n for n in target_names)


def test_importers_of_intra_project(project_root):
    _seed_simple_python_project(project_root)
    bust_cache()
    from forktex.graph.query.deps import importers_of

    g = build_graph(ProjectScope(project_root))
    edges = importers_of(g, "proj.auth.session")
    assert any(e.src_module == "proj.auth.login" for e in edges)


# ── fsd.py ───────────────────────────────────────────────────────────────


def test_fsd_level_default_l0(project_root):
    _seed_simple_python_project(project_root)
    bust_cache()
    g = build_graph(ProjectScope(project_root))
    statuses = fsd_level_of_package(g)
    assert all(s.fsd_level == "L0" for s in statuses)


# ── structure.py ─────────────────────────────────────────────────────────


def test_validate_path_known(project_root):
    m = validate_path("graph.json", scope="project")
    assert m.ok
    assert m.pattern == "graph.json"


def test_validate_path_rejects_unknown():
    m = validate_path("bogus.txt", scope="project")
    assert m.ok is False


# ── cache.py ─────────────────────────────────────────────────────────────


def test_session_graph_caches(project_root):
    _seed_simple_python_project(project_root)
    bust_cache()
    g1 = session_graph(project_root)
    g2 = session_graph(project_root)
    assert g1 is g2


def test_session_graph_busts_on_manifest_mtime(project_root):
    _seed_simple_python_project(project_root)
    bust_cache()
    import time

    g1 = session_graph(project_root)
    # bump mtime past second granularity
    time.sleep(1.1)
    (project_root / "forktex.json").write_text(
        '{"manifestVersion":"1.0.0","name":"proj","version":"0.0.2"}\n'
    )
    g2 = session_graph(project_root)
    assert g1 is not g2
