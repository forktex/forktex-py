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

"""Tests for catalog-driven atom CLI dispatch (`forktex <atom>`)."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import asyncclick as click
import pytest

# Warm up: ensure the fsd loader is importable before pulling _overlay /
# manifest pieces. Mirrors the pattern in test_manifest_overlay.py.
import forktex.fsd  # noqa: F401

from forktex.agent.atoms.dispatcher import (
    AtomDispatchError,
    _build_parsed,
    _project_axes,
    register_atom_commands,
)
from forktex.fsd.loader import load_standard


# ── _build_parsed ─────────────────────────────────────────────────────────


def test_build_parsed_no_flags_returns_bare_atom():
    parsed = _build_parsed(
        "test",
        service=None,
        env=None,
        scope=(),
        services=set(),
        envs=set(),
    )
    assert parsed.base_id == "test"
    assert parsed.make_target == "test"


def test_build_parsed_routes_through_variant_parser_when_axes_given():
    parsed = _build_parsed(
        "apply",
        service="api",
        env="local",
        scope=("logs",),
        services={"api"},
        envs={"local"},
    )
    assert parsed.service == "api"
    assert parsed.env == "local"
    assert parsed.custom == ("logs",)
    assert parsed.make_target == "apply-api-local-logs"


def test_build_parsed_unknown_axis_value_falls_to_custom():
    """If the env value isn't in the manifest's recognised set, it cascades
    to the custom axis (variant parser semantics — first-match-wins,
    leftover qualifiers go to custom)."""
    parsed = _build_parsed(
        "acceptance",
        service=None,
        env="staging",
        scope=("battle",),
        services=set(),
        envs={"local"},  # 'staging' not declared
    )
    # 'staging' didn't match the canonical env axis, so it lands in custom.
    assert parsed.env is None
    assert "staging" in parsed.custom
    assert "battle" in parsed.custom


# ── _project_axes ─────────────────────────────────────────────────────────


def test_project_axes_extracts_packages_and_envs():
    class _Pkg:
        def __init__(self, name, path="."):
            self.name = name
            self.path = path

    class _Env:
        def __init__(self, name):
            self.name = name

    class _Cloud:
        def __init__(self, envs):
            self.environments = envs

    class _Manifest:
        def __init__(self):
            self.packages = [_Pkg("api"), _Pkg("web", path="web")]
            self.cloud = _Cloud([_Env("local"), _Env("prod")])

    services, envs = _project_axes(_Manifest())
    assert services == {"api", "web"}
    assert envs == {"local", "prod"}


def test_project_axes_handles_none_manifest():
    services, envs = _project_axes(None)
    assert services == set()
    assert envs == set()


# ── register_atom_commands ────────────────────────────────────────────────


def _fresh_group():
    @click.group()
    def cli():
        pass

    return cli


def test_register_atom_commands_registers_non_colliding_atoms():
    cli = _fresh_group()
    standard = load_standard()
    registered = register_atom_commands(cli, standard=standard, manifest=None)

    assert "test" in registered
    assert "test" in cli.commands
    assert "apply" in registered
    assert "format" in registered
    # Catalog has 21 atoms (post-v1.2.0); the only command-name collision in
    # a fresh group is none, so all 21 register.
    assert len(registered) == len(standard.atoms)


def test_register_atom_commands_skips_existing_command_collisions():
    """An existing plain @command keeps the name; the atom is not registered."""
    cli = _fresh_group()

    @cli.command("clean")
    def _existing_clean():
        """Existing clean command (not part of atom dispatch)."""

    standard = load_standard()
    registered = register_atom_commands(cli, standard=standard, manifest=None)

    assert "clean" not in registered  # skipped
    # ... but every other atom registers normally.
    assert "test" in registered
    # The existing command stays.
    assert cli.commands["clean"] is _existing_clean


def test_register_atom_commands_skips_invoke_without_command_groups():
    """Groups declared with invoke_without_command=True own the atom dispatch
    in their body; the registrar should not add a parallel top-level
    command shadowing them."""
    cli = _fresh_group()

    @cli.group("manual", invoke_without_command=True)
    @click.pass_context
    def _manual(ctx):
        """Group with subverbs."""

    standard = load_standard()
    registered = register_atom_commands(cli, standard=standard, manifest=None)

    assert "manual" not in registered  # skipped — group owns it
    assert isinstance(cli.commands["manual"], click.Group)


# ── dispatch_atom ─────────────────────────────────────────────────────────


def test_dispatch_atom_raises_when_make_missing(tmp_path):
    from forktex.agent.atoms.dispatcher import dispatch_atom

    with patch("forktex.agent.atoms.dispatcher.shutil.which", return_value=None):
        with pytest.raises(AtomDispatchError) as exc:
            dispatch_atom("test", project_root=tmp_path)
        assert "GNU Make" in str(exc.value.message)


def test_dispatch_atom_shells_out_with_correct_target(tmp_path):
    from forktex.agent.atoms.dispatcher import dispatch_atom

    with (
        patch(
            "forktex.agent.atoms.dispatcher.shutil.which", return_value="/usr/bin/make"
        ),
        patch("forktex.agent.atoms.dispatcher.subprocess.run") as mock_run,
    ):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["make", "apply-local"], returncode=0
        )
        rc = dispatch_atom(
            "apply",
            project_root=tmp_path,
            env="local",
            envs={"local"},
        )
        assert rc == 0
        mock_run.assert_called_once_with(["make", "apply-local"], cwd=tmp_path)


def test_dispatch_atom_propagates_nonzero_exit(tmp_path):
    from forktex.agent.atoms.dispatcher import dispatch_atom

    with (
        patch(
            "forktex.agent.atoms.dispatcher.shutil.which", return_value="/usr/bin/make"
        ),
        patch("forktex.agent.atoms.dispatcher.subprocess.run") as mock_run,
    ):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["make", "test"], returncode=2
        )
        rc = dispatch_atom("test", project_root=tmp_path)
        assert rc == 2
