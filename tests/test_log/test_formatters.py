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

"""Tests for forktex.log's JsonFormatter and HumanFormatter."""

from __future__ import annotations

import logging

from forktex.log import HumanFormatter, log_context, set_trace_id, trace_context


def test_json_basic_fields(capture_json):
    log, captured = capture_json(service="svc1")
    log.info("hello world")
    assert len(captured) == 1
    rec = captured[0]
    assert rec["message"] == "hello world"
    assert rec["level"] == "INFO"
    assert rec["service"] == "svc1"
    assert "timestamp" in rec
    assert "logger" in rec


def test_json_trace_id_injected(capture_json):
    log, captured = capture_json()
    set_trace_id("req-abc-123")
    log.info("with trace")
    assert captured[0]["trace_id"] == "req-abc-123"


def test_json_no_trace_id_when_unset(capture_json):
    log, captured = capture_json()
    log.info("no trace")
    assert "trace_id" not in captured[0] or captured[0].get("trace_id") is None


def test_json_exception_formatting(capture_json):
    log, captured = capture_json()
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception("caught error")
    rec = captured[0]
    assert "exception" in rec
    assert "ValueError" in rec["exception"]


def test_json_formatter_includes_root_trace_id_when_set(capture_json):
    log, captured = capture_json()
    with trace_context("outer"):
        with trace_context("inner"):
            log.info("nested")
    rec = captured[0]
    assert rec["root_trace_id"] == "outer"
    assert rec["trace_id"] != "outer"


def test_json_formatter_omits_root_trace_id_when_unset(capture_json):
    log, captured = capture_json()
    log.info("no trace")
    assert "root_trace_id" not in captured[0]


def test_json_extra_field_collision_core_wins(capture_json):
    log, captured = capture_json()
    with log_context(level="SPOOFED", logger="spoofed-logger"):
        log.info("hello")
    rec = captured[0]
    assert rec["level"] == "INFO"
    assert rec["logger"] != "spoofed-logger"


def test_human_formatter_fmt_override():
    formatter = HumanFormatter(fmt="%(message)s", datefmt="%H:%M")
    record = logging.LogRecord("x", logging.INFO, "path", 1, "hi", None, None)
    assert formatter.format(record) == "hi"


def test_human_formatter_prefixes_trace_id():
    formatter = HumanFormatter(fmt="%(message)s")
    record = logging.LogRecord("x", logging.INFO, "path", 1, "hi", None, None)
    record.trace_id = "req-abc"
    assert formatter.format(record) == "[req-abc] hi"


def test_human_formatter_no_prefix_without_trace_id():
    formatter = HumanFormatter(fmt="%(message)s")
    record = logging.LogRecord("x", logging.INFO, "path", 1, "hi", None, None)
    assert formatter.format(record) == "hi"


def test_human_formatter_does_not_show_root_trace_id():
    """root_trace_id is a JSON/machine-correlation field only — the dev-mode
    line stays [trace_id]-only, never [trace_id/root_trace_id]."""
    formatter = HumanFormatter(fmt="%(message)s")
    record = logging.LogRecord("x", logging.INFO, "path", 1, "hi", None, None)
    record.trace_id = "req-abc"
    record.root_trace_id = "req-root"
    assert formatter.format(record) == "[req-abc] hi"


def test_human_formatter_does_not_mutate_shared_record():
    formatter = HumanFormatter(fmt="%(message)s")
    record = logging.LogRecord("x", logging.INFO, "path", 1, "hi", None, None)
    record.trace_id = "req-abc"
    formatter.format(record)
    assert record.msg == "hi"  # not permanently mutated to "[req-abc] hi"


def test_human_formatter_escapes_control_characters_in_the_trace_id():
    """`HumanFormatter` writes trace_id into a raw single-line record, so a newline in
    it splices a forged log line into the stream. `TraceIDMiddleware` screens inbound
    headers, but a trace id can also arrive from `trace_context()`, a CLI argument, or a
    queue job payload — none of which it sees — so the sink has to defend itself."""
    formatter = HumanFormatter()
    record = logging.LogRecord("d", logging.INFO, __file__, 1, "real message", None, None)
    record.trace_id = "x\n2026-01-01 00:00:00 | CRITICAL | audit | payment approved"
    record.root_trace_id = None
    record.service = None
    record._forktex_extra = {}

    line = formatter.format(record)

    assert "\n" not in line, "a forged newline reached the output stream"
    assert "CRITICAL" in line, "the text is kept, only the control character is neutralised"
    assert "real message" in line


def test_human_formatter_leaves_a_legitimate_trace_id_intact():
    formatter = HumanFormatter()
    record = logging.LogRecord("d", logging.INFO, __file__, 1, "msg", None, None)
    record.trace_id = "req-abc_123.4"
    record.root_trace_id = None
    record.service = None
    record._forktex_extra = {}

    assert "[req-abc_123.4]" in formatter.format(record)


def test_json_always_carries_run_id_even_with_no_trace(capture_json):
    """`run_id` is the attributability field: 100% of records have it, so every line
    can be tied to a process invocation even when no trace scope was open."""
    log, captured = capture_json()
    log.info("unscoped")

    assert captured[0]["run_id"]
    assert "trace_id" not in captured[0], "an unscoped line must not claim a trace"


def test_json_run_id_appears_alongside_a_trace_not_instead_of_it(capture_json):
    log, captured = capture_json()
    with trace_context("R-1"):
        log.info("scoped")

    assert captured[0]["trace_id"] == "R-1"
    assert captured[0]["run_id"]
    assert captured[0]["run_id"] != "R-1", "run_id must be a separate identity"
