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

from collections.abc import Callable
from collections.abc import Iterator
import json
import logging

import pytest

from forktex.log import JsonFormatter, get_logger, set_trace_id


@pytest.fixture(autouse=True)
def reset_trace_id() -> Iterator[None]:
    set_trace_id(None)
    yield
    set_trace_id(None)


@pytest.fixture
def capture_json() -> Callable[..., tuple[logging.Logger, list[dict]]]:

    def _factory(service: str = "test") -> tuple[logging.Logger, list[dict]]:
        from forktex.log import ContextFilter

        captured: list[dict] = []

        class CaptureHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(json.loads(self.format(record)))

        handler = CaptureHandler()
        handler.setFormatter(JsonFormatter())
        handler.addFilter(ContextFilter(service=service))

        log = get_logger(f"test.module.{service}")
        log.handlers.clear()
        log.addHandler(handler)
        log.propagate = False
        log.setLevel(logging.DEBUG)
        return log, captured

    return _factory
