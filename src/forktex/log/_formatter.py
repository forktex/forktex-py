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

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from forktex.iso import to_iso

_SKIP_FIELDS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "taskName",
        "trace_id",
        "root_trace_id",
        "run_id",
        "service",
        "_forktex_extra",
    }
)


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = to_iso(datetime.fromtimestamp(record.created, tz=UTC))
        doc: dict[str, Any] = {
            "timestamp": ts,
            "level": record.levelname,
            "logger": record.name,
        }
        service = getattr(record, "service", None)
        if service:
            doc["service"] = service

        doc["message"] = record.getMessage()

        run_id = getattr(record, "run_id", None)
        if run_id:
            doc["run_id"] = run_id

        trace_id = getattr(record, "trace_id", None)
        if trace_id:
            doc["trace_id"] = trace_id

        root_trace_id = getattr(record, "root_trace_id", None)
        if root_trace_id:
            doc["root_trace_id"] = root_trace_id

        extra = getattr(record, "_forktex_extra", {})
        for key, val in extra.items():
            doc.setdefault(key, val)

        for key, val in record.__dict__.items():
            if key not in _SKIP_FIELDS and not key.startswith("_"):
                doc.setdefault(key, val)

        if record.exc_info and record.exc_info[1]:
            doc["exception"] = self.formatException(record.exc_info)

        return json.dumps(doc, default=str)


class HumanFormatter(logging.Formatter):
    FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    DATEFMT = "%Y-%m-%d %H:%M:%S"

    def __init__(self, fmt: str | None = None, datefmt: str | None = None) -> None:
        super().__init__(fmt=fmt or self.FMT, datefmt=datefmt or self.DATEFMT)

    def format(self, record: logging.LogRecord) -> str:
        trace_id = getattr(record, "trace_id", None)
        if not trace_id:
            return super().format(record)
        trace_id = _CONTROL_CHARS.sub("?", str(trace_id))
        original = record.msg
        record.msg = f"[{trace_id}] {record.msg}"
        try:
            return super().format(record)
        finally:
            record.msg = original


__all__ = ["HumanFormatter", "JsonFormatter"]
