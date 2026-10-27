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


from __future__ import annotations

import logging
from collections.abc import Callable
import pytest

from forktex.log import async_log_context, get_extra_fields, log_context


def test_log_context_merges_fields(capture_json: Callable[..., tuple[logging.Logger, list[dict]]]) -> None:
    log, captured = capture_json()
    with log_context(org_id="org-xyz", user_id="usr-1"):
        log.info("inside context")
    rec = captured[0]
    assert rec["org_id"] == "org-xyz"
    assert rec["user_id"] == "usr-1"


def test_log_context_does_not_leak(capture_json: Callable[..., tuple[logging.Logger, list[dict]]]) -> None:
    log, captured = capture_json()
    with log_context(org_id="org-xyz"):
        pass
    log.info("outside context")
    assert "org_id" not in captured[0]


def test_log_context_nested_merge(capture_json: Callable[..., tuple[logging.Logger, list[dict]]]) -> None:
    log, captured = capture_json()
    with log_context(a="1"):
        with log_context(b="2"):
            log.info("nested")
    rec = captured[0]
    assert rec["a"] == "1"
    assert rec["b"] == "2"


@pytest.mark.asyncio
async def test_async_log_context(capture_json: Callable[..., tuple[logging.Logger, list[dict]]]) -> None:
    log, captured = capture_json()
    async with async_log_context(request_id="req-99"):
        log.info("async context")
    assert captured[0]["request_id"] == "req-99"
    log.info("after async context")
    assert "request_id" not in captured[1]


def test_get_extra_fields_snapshots_current_context() -> None:
    assert get_extra_fields() == {}
    with log_context(org_id="org-xyz"):
        assert get_extra_fields() == {"org_id": "org-xyz"}
        with log_context(user_id="usr-1"):
            assert get_extra_fields() == {"org_id": "org-xyz", "user_id": "usr-1"}
    assert get_extra_fields() == {}
