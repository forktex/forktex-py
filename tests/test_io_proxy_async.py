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

"""Tests for tracked_write_async parity with the sync variant."""

import pytest

from forktex.graph import io_proxy, registry


pytestmark = [pytest.mark.usefixtures("isolated_home"), pytest.mark.asyncio]


async def test_tracked_write_async_writes_and_records(project_root):
    target = project_root / ".forktex" / "config.json"
    await io_proxy.tracked_write_async(
        target,
        '{"a":1}\n',
        kind="settings",
        writer="test.case",
    )
    assert target.read_text() == '{"a":1}\n'
    reg = registry.load()
    assert str(project_root) in reg.projects


async def test_tracked_write_async_rejects_unspec_path(project_root):
    target = project_root / ".forktex" / "rogue.bin"
    with pytest.raises(io_proxy.StructureViolation):
        await io_proxy.tracked_write_async(target, b"x", kind="rogue")


async def test_tracked_write_async_atomic_no_leftovers(project_root):
    target = project_root / ".forktex" / "config.json"
    await io_proxy.tracked_write_async(target, "x", kind="settings")
    leftovers = [p for p in target.parent.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


async def test_tracked_write_async_handles_bytes(project_root):
    target = project_root / ".forktex" / "config.json"
    await io_proxy.tracked_write_async(
        target,
        b"\x00\x01raw",
        kind="settings",
    )
    assert target.read_bytes() == b"\x00\x01raw"
