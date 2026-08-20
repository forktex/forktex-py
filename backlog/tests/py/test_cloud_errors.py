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

"""Tests for the cloud error translation decorator."""

import asyncclick as click
import httpx
import pytest
from forktex_cloud.client import CloudAPIError

from forktex.agent.cloud.errors import translate_cloud_errors


def test_translate_cloud_errors_passes_through_normal_return():
    @translate_cloud_errors
    def ok():
        return 42

    assert ok() == 42


def test_translate_cloud_errors_translates_api_error():
    @translate_cloud_errors
    def boom():
        raise CloudAPIError(404, "no such project")

    with pytest.raises(click.ClickException) as exc_info:
        boom()
    assert "404" in str(exc_info.value.message)
    assert "no such project" in str(exc_info.value.message)


def test_translate_cloud_errors_special_message_for_401():
    @translate_cloud_errors
    def boom():
        raise CloudAPIError(401, "token expired")

    with pytest.raises(click.ClickException) as exc_info:
        boom()
    assert "forktex cloud connect" in exc_info.value.message


def test_translate_cloud_errors_translates_network_error():
    @translate_cloud_errors
    def boom():
        raise httpx.ConnectError("could not bind")

    with pytest.raises(click.ClickException) as exc_info:
        boom()
    assert "Cannot reach" in exc_info.value.message


def test_translate_cloud_errors_passes_through_click_exception():
    """Pre-translated ClickExceptions must not be re-wrapped."""

    @translate_cloud_errors
    def boom():
        raise click.ClickException("already friendly")

    with pytest.raises(click.ClickException) as exc_info:
        boom()
    assert exc_info.value.message == "already friendly"


def test_translate_cloud_errors_passes_through_other_exceptions():
    """Real bugs (KeyError, ValueError, etc.) must surface unchanged."""

    @translate_cloud_errors
    def boom():
        raise KeyError("internal-bug")

    with pytest.raises(KeyError):
        boom()


async def test_translate_cloud_errors_async_path():
    @translate_cloud_errors
    async def boom():
        raise CloudAPIError(503, "scheduled maintenance")

    with pytest.raises(click.ClickException) as exc_info:
        await boom()
    assert "503" in exc_info.value.message
    assert "scheduled maintenance" in exc_info.value.message


async def test_translate_cloud_errors_async_passthrough():
    @translate_cloud_errors
    async def ok():
        return "done"

    assert await ok() == "done"
