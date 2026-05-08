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

"""Tests for argv credential redaction in the live-instance registry
(SECURITY.md §F)."""

import pytest

from forktex.runtime import instance


pytestmark = pytest.mark.usefixtures("isolated_home")


# ── pure redact_argv ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "argv,expected",
    [
        # Equals form
        (
            ["forktex", "intelligence", "--api-key=ftx-abc123"],
            ["forktex", "intelligence", "--api-key=***REDACTED***"],
        ),
        (
            ["forktex", "cloud", "--token=jwt.x.y.z"],
            ["forktex", "cloud", "--token=***REDACTED***"],
        ),
        (
            ["forktex", "--password=hunter2"],
            ["forktex", "--password=***REDACTED***"],
        ),
        # Space form
        (
            ["forktex", "--api-key", "ftx-abc123", "--port", "4444"],
            ["forktex", "--api-key", "***REDACTED***", "--port", "4444"],
        ),
        (
            ["forktex", "cloud", "connect", "--api-key", "secret"],
            ["forktex", "cloud", "connect", "--api-key", "***REDACTED***"],
        ),
        # Underscore variant
        (
            ["forktex", "--access_token=xyz"],
            ["forktex", "--access_token=***REDACTED***"],
        ),
        # Case-insensitive
        (
            ["forktex", "--API-KEY=xyz"],
            ["forktex", "--API-KEY=***REDACTED***"],
        ),
        # Non-matching flags pass through
        (
            ["forktex", "graph", "build", "--scope=all"],
            ["forktex", "graph", "build", "--scope=all"],
        ),
        # Empty list
        ([], []),
        # No flags at all
        (
            ["forktex"],
            ["forktex"],
        ),
    ],
)
def test_redact_argv(argv, expected):
    assert instance.redact_argv(argv) == expected


def test_redact_argv_does_not_mutate_input():
    original = ["forktex", "--api-key=secret"]
    snapshot = list(original)
    instance.redact_argv(original)
    assert original == snapshot


def test_redact_argv_handles_dangling_flag_no_value():
    # `--api-key` at end of argv with no value following: don't crash,
    # just leave it — there's nothing to redact.
    out = instance.redact_argv(["forktex", "--api-key"])
    assert out == ["forktex", "--api-key"]


# ── integration with create_instance ─────────────────────────────────────


def test_create_instance_redacts_command_field(project_root):
    rec = instance.create_instance(
        kind="test",
        project_root=project_root,
        command=["forktex", "intelligence", "ask", "--api-key=ftx-supersecret"],
    )
    assert "***REDACTED***" in rec.command[3]
    assert "ftx-supersecret" not in " ".join(rec.command)


def test_create_instance_redacted_record_is_what_lands_on_disk(project_root):
    import json

    rec = instance.create_instance(
        kind="test",
        project_root=project_root,
        command=["forktex", "cloud", "connect", "--api-key", "ftx-leaktest"],
    )
    rec_path = instance.global_instances_dir() / f"{rec.run_id}.json"
    on_disk = json.loads(rec_path.read_text())
    assert "ftx-leaktest" not in json.dumps(on_disk)
    assert "***REDACTED***" in on_disk["command"]
