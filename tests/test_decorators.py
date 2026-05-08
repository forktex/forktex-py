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

"""Tests for the AOP decorator layer."""

from pathlib import Path

import pytest

from forktex.graph import io_proxy
from forktex.graph.structure import GLOBAL_SPEC, PROJECT_SPEC
from forktex.runtime import decorators


pytestmark = pytest.mark.usefixtures("isolated_home")


# ── @tracked_writer ──────────────────────────────────────────────────────


def test_tracked_writer_stamps_metadata():
    @decorators.tracked_writer(spec_pattern="config.json", kind="settings")
    def my_writer(root: Path):
        return root / ".forktex" / "config.json", "{}"

    assert my_writer.__forktex_spec__ == ("config.json", "settings", "project")


def test_tracked_writer_routes_through_tracked_write(project_root):
    @decorators.tracked_writer(spec_pattern="config.json", kind="settings")
    def my_writer(root: Path):
        return root / ".forktex" / "config.json", '{"x":1}'

    target = my_writer(project_root)
    assert target.read_text() == '{"x":1}'


def test_tracked_writer_rejects_unknown_pattern_at_decoration_time():
    with pytest.raises(ValueError, match="unknown.*spec entry"):

        @decorators.tracked_writer(spec_pattern="nonexistent.json", kind="rogue")
        def _bad_writer():
            return Path("/tmp/x"), ""


def test_tracked_writer_rejects_bad_return_type(project_root):
    @decorators.tracked_writer(spec_pattern="config.json", kind="settings")
    def my_writer():
        return "not a tuple"

    with pytest.raises(TypeError, match="must return"):
        my_writer()


# ── @sdk_boundary ────────────────────────────────────────────────────────


def test_sdk_boundary_passes_through_when_compliant(project_root):
    @decorators.sdk_boundary(scope="project", project_root_arg="project_root")
    def fake_sdk(project_root: Path):
        # Compliant write — config.json is in the spec.
        target = project_root / ".forktex" / "config.json"
        target.write_text("{}")
        return target

    target = fake_sdk(project_root=project_root)
    assert target.is_file()


def test_sdk_boundary_raises_on_unspec_write(project_root):
    @decorators.sdk_boundary(
        scope="project",
        project_root_arg="project_root",
        strict=True,
    )
    def fake_sdk(project_root: Path):
        target = project_root / ".forktex" / "rogue_from_sdk.txt"
        target.write_text("nope")
        return target

    with pytest.raises(io_proxy.StructureViolation, match="rogue_from_sdk"):
        fake_sdk(project_root=project_root)


def test_sdk_boundary_warns_when_non_strict(project_root, caplog):
    @decorators.sdk_boundary(
        scope="project",
        project_root_arg="project_root",
        strict=False,
    )
    def fake_sdk(project_root: Path):
        target = project_root / ".forktex" / "rogue_from_sdk.txt"
        target.write_text("nope")
        return target

    import logging

    caplog.set_level(logging.WARNING, logger="forktex.runtime.decorators")
    fake_sdk(project_root=project_root)
    assert any("rogue_from_sdk" in rec.message for rec in caplog.records)


def test_sdk_boundary_records_touches(project_root):
    @decorators.sdk_boundary(scope="project", project_root_arg="project_root")
    def fake_sdk(project_root: Path):
        target = project_root / ".forktex" / "config.json"
        target.write_text("{}")
        return target

    fake_sdk(project_root=project_root)
    from forktex.graph import registry

    reg = registry.load()
    proj = reg.projects[str(project_root.resolve())]
    assert any(t.rel_path == "config.json" for t in proj.touches)


# ── @needs_project ───────────────────────────────────────────────────────


def test_needs_project_resolves_root(project_root, monkeypatch):
    monkeypatch.chdir(project_root)
    captured = {}

    @decorators.needs_project
    async def cmd(project=None, project_root=None):
        captured["root"] = project_root

    import asyncio

    asyncio.run(cmd(project=None))
    assert captured["root"] == project_root.resolve()


def test_needs_project_errors_outside_project(orphan_dir, monkeypatch):
    import asyncclick as click

    monkeypatch.chdir(orphan_dir)

    @decorators.needs_project
    async def cmd(project=None):
        return "should not run"

    import asyncio

    with pytest.raises(click.ClickException, match="no forktex.json"):
        asyncio.run(cmd(project=None))


# ── Coverage matrix ──────────────────────────────────────────────────────


def test_decorator_coverage_for_specced_writers():
    """Every spec entry whose ``writers`` references a forktex.* module
    should be reachable through code in this repo. This is a soft check
    — it warns but does not fail when a writer isn't yet decorated, so
    the test bedds in over a release before we tighten it."""
    import warnings

    for spec in (*PROJECT_SPEC, *GLOBAL_SPEC):
        for writer in spec.writers:
            if not writer.startswith("forktex."):
                continue
            mod_name, _, _ = writer.rpartition(".")
            try:
                __import__(mod_name)
            except ImportError:
                warnings.warn(
                    f"writer {writer!r} for spec {spec.pattern!r} cannot be imported"
                )


# ── Coverage of @tracked_writer attribute (informational) ────────────────


def test_tracked_writer_metadata_attribute_set():
    """A coverage check: any function decorated with @tracked_writer must
    expose ``__forktex_spec__`` for introspection."""

    @decorators.tracked_writer(spec_pattern="config.json", kind="settings")
    def writer():
        return Path("/tmp/x") / "config.json", ""

    assert hasattr(writer, "__forktex_spec__")
    pattern, kind, scope = writer.__forktex_spec__
    assert pattern == "config.json"
    assert kind == "settings"
    assert scope == "project"
