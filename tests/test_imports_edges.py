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

"""Tests for AST-based imports edge extraction (build.py)."""

import pytest

from forktex.graph.build import (
    _populate_imports,
    _resolve_relative_import,
    _scan_module_imports,
    build_graph,
)
from forktex.graph.scopes import ProjectScope


pytestmark = pytest.mark.usefixtures("isolated_home")


def test_scan_module_imports_returns_targets_and_levels(tmp_path):
    f = tmp_path / "m.py"
    f.write_text(
        "import json\n"
        "import os.path\n"
        "from pathlib import Path\n"
        "from . import sib\n"
        "from ..pkg import thing\n"
    )
    out = _scan_module_imports(f)
    targets = sorted(out)
    assert ("json", 0) in targets
    assert ("os.path", 0) in targets
    assert ("pathlib", 0) in targets
    assert ("", 1) in targets
    assert ("pkg", 2) in targets


def test_scan_module_imports_returns_empty_on_syntax_error(tmp_path):
    f = tmp_path / "broken.py"
    f.write_text("def f(:\n  pass\n")
    assert _scan_module_imports(f) == []


def test_scan_module_imports_skips_oversize(tmp_path):
    f = tmp_path / "huge.py"
    # 300 KB > 256 KB cap
    f.write_text("x = '" + "a" * (300 * 1024) + "'\n")
    assert _scan_module_imports(f) == []


def test_resolve_relative_import_level_1():
    # Inside `myapp.auth.login`, `from . import session` → `myapp.auth.session`
    out = _resolve_relative_import("myapp.auth.login", "session", 1)
    assert out == "myapp.auth.session"


def test_resolve_relative_import_level_2():
    # Inside `myapp.auth.login`, `from .. import core` → `myapp.core`
    out = _resolve_relative_import("myapp.auth.login", "core", 2)
    assert out == "myapp.core"


def test_build_graph_populates_imports(project_root):
    pkg = project_root / "src" / "proj" / "core"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "a.py").write_text("import json\nfrom proj.core import b\n")
    (pkg / "b.py").write_text("import os\n")

    g = build_graph(ProjectScope(project_root))
    edges = [e for e in g.edges if e.kind == "imports"]
    assert any(e.attrs.get("target_dotted") == "json" for e in edges)
    assert any(e.attrs.get("target_dotted") == "proj.core.b" for e in edges)


def test_build_graph_skips_node_modules(tmp_path):
    """Files under skip-listed trees must NOT contribute imports edges.

    This is the safety guarantee: even if a foreign tree contains .py
    files that LOOK like part of the project, they don't show up.
    """
    root = tmp_path / "proj_with_node_modules"
    root.mkdir()
    (root / "forktex.json").write_text(
        '{"manifestVersion":"1.0.0","name":"proj","version":"0.0.1"}\n'
    )
    (root / ".forktex").mkdir()
    (root / ".forktex" / ".version").write_text("1\n")
    pkg = root / "src" / "proj"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("import json\n")
    # The foreign tree.
    foreign = root / "node_modules" / "evil"
    foreign.mkdir(parents=True)
    (foreign / "garbage.py").write_text(
        "import suspicious_package_that_should_never_appear\n"
    )

    g = build_graph(ProjectScope(root))
    edge_targets = [
        e.attrs.get("target_dotted", "") for e in g.edges if e.kind == "imports"
    ]
    assert not any(
        "suspicious_package_that_should_never_appear" in t for t in edge_targets
    )


def test_populate_imports_creates_external_dep(project_root):
    pkg = project_root / "src" / "proj" / "core"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("import some_third_party_thing\n")
    g = build_graph(ProjectScope(project_root))
    ext_names = {n.name for n in g.by_kind("external_dep")}
    assert "some_third_party_thing" in ext_names


def test_populate_imports_idempotent(project_root):
    pkg = project_root / "src" / "proj" / "core"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("import json\n")
    g = build_graph(ProjectScope(project_root))
    n_before = sum(1 for e in g.edges if e.kind == "imports")
    _populate_imports(g)
    n_after = sum(1 for e in g.edges if e.kind == "imports")
    assert n_before == n_after  # add_edge dedupes by id
